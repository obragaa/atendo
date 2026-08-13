"""Loop do agente: orçamento → cache → ferramentas → resposta.

Sem framework de orquestração, por decisão de arquitetura: o loop é código
explícito e legível — cada passo (orçamento, cache, chamada, ferramenta,
corte) aparece aqui, na ordem em que acontece, e é depurável com um print.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.agent.tools import Tool, ToolError, tools_for
from app.config import Tenant
from app.gateway import cache, usage
from app.gateway.llm import LLMGateway
from app.gateway.usage import UsageRecord
from app.telemetry import span

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 5

# Respostas que dependem de escrita não podem ir ao cache semântico: a
# segunda pessoa receberia a confirmação de agendamento da primeira.
FERRAMENTAS_DE_ESCRITA = {"criar_agendamento", "registrar_lead"}


@dataclass
class AgentReply:
    text: str
    conversation_id: str
    cached: bool = False
    escalated: bool = False
    cost_usd: float = 0.0
    latency_ms: int = 0
    tools_used: list[str] = field(default_factory=list)
    iterations: int = 0


@dataclass
class Agent:
    gateway: LLMGateway

    async def respond(
        self,
        tenant: Tenant,
        conversation_id: str,
        history: list[dict[str, Any]],
        message: str,
    ) -> AgentReply:
        with span(
            "agent.respond",
            {"tenant.id": tenant.id, "conversation.id": conversation_id},
        ) as s:
            reply = await self._respond(tenant, conversation_id, history, message)
            if s is not None:
                s.set_attribute("agent.cost_usd", reply.cost_usd)
                s.set_attribute("agent.iterations", reply.iterations)
                s.set_attribute("agent.cached", reply.cached)
                s.set_attribute("agent.escalated", reply.escalated)
            return reply

    async def _respond(
        self,
        tenant: Tenant,
        conversation_id: str,
        history: list[dict[str, Any]],
        message: str,
    ) -> AgentReply:
        # 1. Orçamento: estourou o teto do mês, nem chama o modelo.
        if await usage.over_budget(tenant.id, tenant.monthly_budget_usd):
            logger.warning("Tenant %s acima do orçamento mensal; escalando.", tenant.id)
            return AgentReply(
                text=tenant.escalation_phrase,
                conversation_id=conversation_id,
                escalated=True,
            )

        # 2. Cache: só no primeiro turno — do segundo em diante a resposta
        #    depende do contexto da conversa.
        if not history:
            acerto = await cache.lookup(tenant.id, message)
            if acerto is not None:
                await usage.record(
                    UsageRecord(
                        tenant_id=tenant.id,
                        conversation_id=conversation_id,
                        model="cache",
                        cached=True,
                    )
                )
                return AgentReply(text=acerto.answer, conversation_id=conversation_id, cached=True)

        # 3. Loop de ferramentas.
        ferramentas = tools_for(tenant)
        liberadas = {t.name: t for t in ferramentas}
        tools_api = [t.to_api() for t in ferramentas]
        system = tenant.system_prompt()
        mensagens: list[dict[str, Any]] = [*history, {"role": "user", "content": message}]

        custo = 0.0
        latencia = 0
        usadas: list[str] = []
        escalated = False
        iteracoes = 0

        for _ in range(MAX_ITERATIONS):
            iteracoes += 1
            resposta = await self.gateway.complete(system, mensagens, tools_api)
            custo += resposta.cost_usd
            latencia += resposta.latency_ms
            escalated = escalated or resposta.escalated
            await usage.record(
                UsageRecord(
                    tenant_id=tenant.id,
                    conversation_id=conversation_id,
                    model=resposta.model,
                    input_tokens=resposta.input_tokens,
                    output_tokens=resposta.output_tokens,
                    cost_usd=resposta.cost_usd,
                    escalated=resposta.escalated,
                    latency_ms=resposta.latency_ms,
                )
            )

            if not resposta.tool_calls:
                texto_final = resposta.text
                break

            mensagens.append({"role": "assistant", "content": resposta.raw_content})
            resultados = []
            for chamada in resposta.tool_calls:
                usadas.append(chamada["name"])
                resultados.append(await self._run_tool(tenant, liberadas, chamada))
            mensagens.append({"role": "user", "content": resultados})
        else:
            # 4. Estouro do laço: o modelo não convergiu em MAX_ITERATIONS.
            logger.warning(
                "Loop do agente cortado em %d iterações (tenant=%s, conversa=%s)",
                MAX_ITERATIONS,
                tenant.id,
                conversation_id,
            )
            return AgentReply(
                text=tenant.escalation_phrase,
                conversation_id=conversation_id,
                escalated=True,
                cost_usd=custo,
                latency_ms=latencia,
                tools_used=usadas,
                iterations=MAX_ITERATIONS,
            )

        # 5. Grava no cache apenas primeira pergunta respondida sem escrita.
        if not history and not (set(usadas) & FERRAMENTAS_DE_ESCRITA):
            await cache.store(tenant.id, message, texto_final)

        return AgentReply(
            text=texto_final,
            conversation_id=conversation_id,
            escalated=escalated,
            cost_usd=custo,
            latency_ms=latencia,
            tools_used=usadas,
            iterations=iteracoes,
        )

    async def _run_tool(
        self, tenant: Tenant, liberadas: dict[str, Tool], chamada: dict[str, Any]
    ) -> dict[str, Any]:
        """Executa uma ferramenta e monta o bloco tool_result."""
        nome = chamada["name"]
        bloco: dict[str, Any] = {"type": "tool_result", "tool_use_id": chamada["id"]}
        with span("agent.tool", {"tenant.id": tenant.id, "tool.name": nome}):
            ferramenta = liberadas.get(nome)
            if ferramenta is None:
                bloco["content"] = f"Ferramenta {nome} não disponível."
                bloco["is_error"] = True
                return bloco
            try:
                argumentos = chamada.get("input") or {}
                bloco["content"] = await ferramenta.handler(tenant, **argumentos)
            except ToolError as erro:
                bloco["content"] = str(erro)
                bloco["is_error"] = True
            except TypeError as erro:
                # O modelo inventou/omitiu argumentos: devolve para corrigir.
                bloco["content"] = f"Argumentos inválidos para {nome}: {erro}"
                bloco["is_error"] = True
            except Exception:
                logger.exception("Ferramenta %s falhou (tenant=%s)", nome, tenant.id)
                bloco["content"] = "A ferramenta falhou. Não tente de novo."
                bloco["is_error"] = True
        return bloco
