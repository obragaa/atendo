"""Cliente da API Anthropic Messages, com retry e escalonamento de modelo.

httpx direto, sem SDK e sem framework de orquestração: o contrato da API é
um POST com JSON, e mantê-lo explícito deixa retry, custo e erro visíveis
neste arquivo em vez de escondidos numa dependência.

Política de escalonamento: "vocês atendem convênio?" não precisa de
raciocínio — a esmagadora maioria do atendimento é recuperação de fato mais
boa redação, e o modelo pequeno resolve. Roteamento por classificador foi
descartado: exige mais uma chamada de modelo, erra, e precisa de manutenção.
A regra "escala quando falha de verdade" não erra porque não adivinha.
Métrica de validação: escalation_rate acima de 15% significa que o modelo
padrão está errado.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"

# Status transitórios do provedor: vale a pena tentar de novo.
STATUS_TRANSITORIOS = {429, 500, 502, 503, 529}

# USD por milhão de tokens (entrada, saída), por modelo.
# Esta tabela é a ÚNICA fonte de verdade do custo cobrado do cliente:
# usage_events.cost_usd é calculado daqui, e o preço da mensalidade é
# derivado de usage_events. Atualizou o preço do provedor, atualiza aqui.
PRICING: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-sonnet-5": (3.00, 15.00),
}
# Fallback deliberadamente no preço do modelo mais caro da tabela: diante de
# um modelo desconhecido, superestimar custo é mais seguro que subestimar.
PRICING_FALLBACK: tuple[float, float] = (3.00, 15.00)


class ProviderError(RuntimeError):
    """Falha transitória do provedor (429/5xx/529 ou resposta vazia)."""


@dataclass
class LLMResponse:
    """Resposta de uma chamada de modelo, já com custo e latência."""

    text: str
    tool_calls: list[dict[str, Any]]
    raw_content: list[dict[str, Any]]
    stop_reason: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    escalated: bool = False

    @property
    def cost_usd(self) -> float:
        entrada, saida = PRICING.get(self.model, PRICING_FALLBACK)
        return (self.input_tokens * entrada + self.output_tokens * saida) / 1_000_000


@dataclass
class LLMGateway:
    """Chama o modelo primário e escala para o maior apenas em falha real."""

    settings: Settings = field(default_factory=get_settings)

    async def complete(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        force_escalation: bool = False,
    ) -> LLMResponse:
        inicio = time.perf_counter()
        escalated = force_escalation
        modelo = self.settings.model_escalation if force_escalation else self.settings.model_primary
        try:
            data = await self._call(modelo, system, messages, tools)
        except (ProviderError, httpx.HTTPError) as erro:
            if force_escalation:
                raise
            logger.warning(
                "Modelo primário %s falhou (%s); escalando para %s",
                modelo,
                erro,
                self.settings.model_escalation,
            )
            data = await self._call(self.settings.model_escalation, system, messages, tools)
            escalated = True

        latency_ms = int((time.perf_counter() - inicio) * 1000)
        content = data.get("content", [])
        texto = "".join(b.get("text", "") for b in content if b.get("type") == "text")
        tool_calls = [b for b in content if b.get("type") == "tool_use"]
        uso = data.get("usage", {})
        return LLMResponse(
            text=texto,
            tool_calls=tool_calls,
            raw_content=content,
            stop_reason=data.get("stop_reason", ""),
            model=data.get("model", modelo),
            input_tokens=int(uso.get("input_tokens", 0)),
            output_tokens=int(uso.get("output_tokens", 0)),
            latency_ms=latency_ms,
            escalated=escalated,
        )

    @retry(
        retry=retry_if_exception_type((ProviderError, httpx.TransportError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, max=8),
        reraise=True,
    )
    async def _call(
        self,
        model: str,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": self.settings.model_max_tokens,
            "system": system,
            "messages": messages,
        }
        if tools:
            payload["tools"] = tools

        async with httpx.AsyncClient(timeout=60.0) as client:
            resposta = await client.post(
                API_URL,
                headers={
                    "x-api-key": self.settings.anthropic_api_key,
                    "anthropic-version": API_VERSION,
                    "content-type": "application/json",
                },
                json=payload,
            )

        if resposta.status_code in STATUS_TRANSITORIOS:
            raise ProviderError(f"provedor devolveu status {resposta.status_code}")
        resposta.raise_for_status()

        data: dict[str, Any] = resposta.json()
        content = data.get("content", [])
        tem_texto = any(b.get("type") == "text" and b.get("text") for b in content)
        tem_tool = any(b.get("type") == "tool_use" for b in content)
        if not tem_texto and not tem_tool:
            raise ProviderError("resposta vazia do modelo")
        return data
