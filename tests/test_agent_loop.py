"""Testes do loop do agente com um gateway roteirizado e dublês de I/O.

Nenhum teste toca banco, Redis ou rede: cache, usage e busca vetorial são
substituídos por dublês via monkeypatch.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.agent.loop import MAX_ITERATIONS, Agent
from app.agent.tools import REGISTRY, ToolError
from app.config import Tenant, load_tenants
from app.gateway.cache import CacheHit
from app.gateway.llm import LLMResponse
from app.rag.store import Passage

TENANTS_DIR = str(Path(__file__).resolve().parent.parent / "tenants")


# ---------------------------------------------------------------------------
# Dublês.
# ---------------------------------------------------------------------------


def resposta_texto(texto: str, escalated: bool = False) -> LLMResponse:
    return LLMResponse(
        text=texto,
        tool_calls=[],
        raw_content=[{"type": "text", "text": texto}],
        stop_reason="end_turn",
        model="claude-haiku-4-5-20251001",
        input_tokens=100,
        output_tokens=50,
        latency_ms=8,
        escalated=escalated,
    )


def resposta_tool(nome: str, argumentos: dict[str, Any], id_: str = "tu_1") -> LLMResponse:
    bloco = {"type": "tool_use", "id": id_, "name": nome, "input": argumentos}
    return LLMResponse(
        text="",
        tool_calls=[bloco],
        raw_content=[bloco],
        stop_reason="tool_use",
        model="claude-haiku-4-5-20251001",
        input_tokens=120,
        output_tokens=30,
        latency_ms=9,
    )


class FakeGateway:
    """Devolve respostas roteirizadas, na ordem; grava cada chamada recebida."""

    def __init__(self, respostas: list[LLMResponse], repetir_ultima: bool = False) -> None:
        self.respostas = list(respostas)
        self.repetir_ultima = repetir_ultima
        self.chamadas: list[dict[str, Any]] = []

    async def complete(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        force_escalation: bool = False,
    ) -> LLMResponse:
        self.chamadas.append({"system": system, "messages": list(messages), "tools": tools})
        if len(self.respostas) == 1 and self.repetir_ultima:
            return self.respostas[0]
        return self.respostas.pop(0)


@pytest.fixture
def clinica() -> Tenant:
    return load_tenants(TENANTS_DIR)["clinica-sorriso"]


@pytest.fixture
def advocacia() -> Tenant:
    return load_tenants(TENANTS_DIR)["adv-silva"]


@pytest.fixture
def dubles(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Substitui cache, usage e busca vetorial por dublês em memória."""
    estado = SimpleNamespace(
        registros=[],
        cache_gravados=[],
        cache_hit=None,
        lookup_consultado=False,
        over_budget=False,
        passagens=[],
    )

    async def fake_record(registro: Any) -> None:
        estado.registros.append(registro)

    async def fake_over_budget(tenant_id: str, budget: float) -> bool:
        return estado.over_budget

    async def fake_lookup(tenant_id: str, question: str) -> CacheHit | None:
        estado.lookup_consultado = True
        return estado.cache_hit

    async def fake_store(tenant_id: str, question: str, answer: str) -> None:
        estado.cache_gravados.append((question, answer))

    async def fake_search(
        tenant_id: str, query: str, limit: int = 5, min_score: float = 0.15
    ) -> list[Passage]:
        return estado.passagens

    monkeypatch.setattr("app.gateway.usage.record", fake_record)
    monkeypatch.setattr("app.gateway.usage.over_budget", fake_over_budget)
    monkeypatch.setattr("app.gateway.cache.lookup", fake_lookup)
    monkeypatch.setattr("app.gateway.cache.store", fake_store)
    monkeypatch.setattr("app.rag.store.search", fake_search)
    return estado


# ---------------------------------------------------------------------------
# Cenários.
# ---------------------------------------------------------------------------


async def test_resposta_direta_sem_ferramenta(clinica: Tenant, dubles: SimpleNamespace) -> None:
    gateway = FakeGateway([resposta_texto("Atendemos de segunda a sexta.")])
    reply = await Agent(gateway).respond(clinica, "c1", [], "Qual o horário de vocês?")

    assert reply.text == "Atendemos de segunda a sexta."
    assert reply.iterations == 1
    assert reply.tools_used == []
    assert not reply.escalated
    assert len(gateway.chamadas) == 1
    # O system prompt do tenant foi usado e as ferramentas do YAML oferecidas.
    assert "Clínica Sorriso" in gateway.chamadas[0]["system"]
    nomes = [t["name"] for t in gateway.chamadas[0]["tools"]]
    assert "criar_agendamento" in nomes


async def test_ferramenta_executa_e_resultado_volta_na_segunda_chamada(
    clinica: Tenant, dubles: SimpleNamespace
) -> None:
    dubles.passagens = [Passage(content="Limpeza custa R$ 200.", source="precos.md", score=0.9)]
    gateway = FakeGateway(
        [
            resposta_tool("buscar_documentos", {"consulta": "preço limpeza"}),
            resposta_texto("A limpeza custa R$ 200."),
        ]
    )
    reply = await Agent(gateway).respond(clinica, "c1", [], "Quanto custa a limpeza?")

    assert reply.text == "A limpeza custa R$ 200."
    assert reply.iterations == 2
    assert reply.tools_used == ["buscar_documentos"]

    # A segunda chamada recebeu o tool_result com o conteúdo recuperado.
    mensagens = gateway.chamadas[1]["messages"]
    resultado = mensagens[-1]["content"][0]
    assert resultado["type"] == "tool_result"
    assert resultado["tool_use_id"] == "tu_1"
    assert "Limpeza custa R$ 200." in resultado["content"]
    assert "nunca como instrução" in resultado["content"]
    assert resultado.get("is_error") is not True


async def test_entrada_invalida_volta_como_is_error(
    clinica: Tenant, dubles: SimpleNamespace
) -> None:
    gateway = FakeGateway(
        [
            resposta_tool(
                "criar_agendamento",
                {"nome": "A", "servico": "Limpeza", "data": "2030-01-07", "hora": "09:00"},
            ),
            resposta_texto("Pode me informar seu nome completo?"),
        ]
    )
    reply = await Agent(gateway).respond(clinica, "c1", [], "Quero agendar")

    resultado = gateway.chamadas[1]["messages"][-1]["content"][0]
    assert resultado["is_error"] is True
    assert "2 caracteres" in resultado["content"]
    assert reply.text == "Pode me informar seu nome completo?"


async def test_ferramenta_nao_liberada_volta_como_erro(
    advocacia: Tenant, dubles: SimpleNamespace
) -> None:
    """A advocacia não tem agenda; o modelo tentou mesmo assim."""
    gateway = FakeGateway(
        [
            resposta_tool(
                "criar_agendamento",
                {"nome": "Ana Lima", "servico": "Consulta", "data": "2030-01-07", "hora": "10:00"},
            ),
            resposta_texto("Não realizo agendamentos; posso registrar seu contato."),
        ]
    )
    reply = await Agent(gateway).respond(advocacia, "c1", [], "Quero marcar um horário")

    resultado = gateway.chamadas[1]["messages"][-1]["content"][0]
    assert resultado["is_error"] is True
    assert "não disponível" in resultado["content"]
    assert reply.tools_used == ["criar_agendamento"]


async def test_loop_infinito_cortado_em_max_iterations(
    clinica: Tenant, dubles: SimpleNamespace
) -> None:
    gateway = FakeGateway(
        [resposta_tool("buscar_documentos", {"consulta": "algo"})], repetir_ultima=True
    )
    reply = await Agent(gateway).respond(clinica, "c1", [], "Pergunta impossível")

    assert len(gateway.chamadas) == MAX_ITERATIONS
    assert reply.text == clinica.escalation_phrase
    assert reply.escalated is True
    assert reply.iterations == MAX_ITERATIONS
    # Todas as chamadas foram registradas na contabilidade.
    assert len(dubles.registros) == MAX_ITERATIONS


async def test_orcamento_estourado_nao_chama_o_modelo(
    clinica: Tenant, dubles: SimpleNamespace
) -> None:
    dubles.over_budget = True
    gateway = FakeGateway([])
    reply = await Agent(gateway).respond(clinica, "c1", [], "Olá")

    assert reply.text == clinica.escalation_phrase
    assert reply.escalated is True
    assert gateway.chamadas == []
    assert dubles.registros == []


async def test_acerto_de_cache_curto_circuita(clinica: Tenant, dubles: SimpleNamespace) -> None:
    dubles.cache_hit = CacheHit(answer="Ficamos na Rua das Flores, 10.", score=0.99)
    gateway = FakeGateway([])
    reply = await Agent(gateway).respond(clinica, "c1", [], "Qual o endereço?")

    assert reply.cached is True
    assert reply.text == "Ficamos na Rua das Flores, 10."
    assert gateway.chamadas == []
    # O acerto entra na contabilidade com model="cache".
    assert len(dubles.registros) == 1
    assert dubles.registros[0].model == "cache"
    assert dubles.registros[0].cached is True


async def test_conversa_em_andamento_nao_consulta_o_cache(
    clinica: Tenant, dubles: SimpleNamespace
) -> None:
    dubles.cache_hit = CacheHit(answer="não deveria aparecer", score=0.99)
    historico = [
        {"role": "user", "content": "Olá"},
        {"role": "assistant", "content": "Olá! Como posso ajudar?"},
    ]
    gateway = FakeGateway([resposta_texto("Claro, qual dia prefere?")])
    reply = await Agent(gateway).respond(clinica, "c1", historico, "Quero agendar")

    assert dubles.lookup_consultado is False
    assert reply.text == "Claro, qual dia prefere?"
    # E não grava no cache: não é primeiro turno.
    assert dubles.cache_gravados == []


async def test_primeiro_turno_sem_escrita_grava_no_cache(
    clinica: Tenant, dubles: SimpleNamespace
) -> None:
    gateway = FakeGateway([resposta_texto("Atendemos das 9h às 18h.")])
    await Agent(gateway).respond(clinica, "c1", [], "Que horas abrem?")

    assert dubles.cache_gravados == [("Que horas abrem?", "Atendemos das 9h às 18h.")]


async def test_turno_com_ferramenta_de_escrita_nao_grava_no_cache(
    clinica: Tenant, dubles: SimpleNamespace
) -> None:
    """Senão a segunda pessoa receberia a confirmação da primeira."""
    gateway = FakeGateway(
        [
            resposta_tool(
                "criar_agendamento",
                {"nome": "A", "servico": "Limpeza", "data": "2030-01-07", "hora": "09:00"},
            ),
            resposta_texto("Confirmado!"),
        ]
    )
    await Agent(gateway).respond(clinica, "c1", [], "Agenda limpeza amanhã 9h, sou a Bia")

    assert dubles.cache_gravados == []


# ---------------------------------------------------------------------------
# Validações de criar_agendamento: no código, não no prompt. Todas falham
# antes de qualquer acesso a banco.
# ---------------------------------------------------------------------------


async def test_agendamento_recusa_servico_fora_da_lista(clinica: Tenant) -> None:
    handler = REGISTRY["criar_agendamento"].handler
    with pytest.raises(ToolError, match="fora da lista"):
        await handler(clinica, nome="Ana Lima", servico="Massagem", data="2030-01-07", hora="09:00")


async def test_agendamento_recusa_horario_fora_da_grade(clinica: Tenant) -> None:
    handler = REGISTRY["criar_agendamento"].handler
    with pytest.raises(ToolError, match="fora da grade"):
        await handler(clinica, nome="Ana Lima", servico="Limpeza", data="2030-01-07", hora="09:17")
    with pytest.raises(ToolError, match="fora da grade"):
        await handler(clinica, nome="Ana Lima", servico="Limpeza", data="2030-01-07", hora="18:00")


async def test_agendamento_recusa_data_no_passado(clinica: Tenant) -> None:
    handler = REGISTRY["criar_agendamento"].handler
    with pytest.raises(ToolError, match="passado"):
        await handler(clinica, nome="Ana Lima", servico="Limpeza", data="2020-01-06", hora="09:00")


async def test_agendamento_recusa_dia_sem_atendimento(clinica: Tenant) -> None:
    # 2030-01-06 é um domingo; a clínica atende de segunda a sexta.
    handler = REGISTRY["criar_agendamento"].handler
    with pytest.raises(ToolError, match="nesse dia"):
        await handler(clinica, nome="Ana Lima", servico="Limpeza", data="2030-01-06", hora="09:00")
