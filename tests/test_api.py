"""Testes da API HTTP: autenticação por chave, contrato do /chat e hardening."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.agent.loop import AgentReply
from app.config import get_settings
from app.main import app


def test_health_responde_ok() -> None:
    resposta = TestClient(app).get("/health")
    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok"}


def test_chat_sem_chave_devolve_401() -> None:
    resposta = TestClient(app).post("/chat", json={"message": "Oi"})
    assert resposta.status_code == 401


def test_chat_com_chave_errada_devolve_401() -> None:
    resposta = TestClient(app).post(
        "/chat", json={"message": "Oi"}, headers={"X-Api-Key": "chave-invalida"}
    )
    assert resposta.status_code == 401


@pytest.fixture
def api_com_dubles(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Sobe a API com agente e I/O de banco substituídos por dublês."""

    class FakeAgent:
        async def respond(
            self, tenant: Any, conversation_id: str, history: Any, message: str
        ) -> AgentReply:
            return AgentReply(
                text="Atendemos das 9h às 18h.",
                conversation_id=conversation_id,
                cost_usd=0.00123,
                latency_ms=42,
                tools_used=["buscar_documentos"],
            )

    async def fake_rate_limit(tenant_id: str, identity: str) -> bool:
        return True

    async def fake_history(tenant_id: str, conversation_id: str, limit: int = 10) -> list:
        return []

    async def fake_persist(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr("app.gateway.cache.check_rate_limit", fake_rate_limit)
    monkeypatch.setattr("app.main._load_history", fake_history)
    monkeypatch.setattr("app.main._persist_turn", fake_persist)
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "chave-de-teste")
    app.state.agent = FakeAgent()
    return TestClient(app)


def test_chat_com_chave_valida_devolve_200_e_recibo(api_com_dubles: TestClient) -> None:
    resposta = api_com_dubles.post(
        "/chat", json={"message": "Que horas abrem?"}, headers={"X-Api-Key": "demo-sorriso-123"}
    )
    assert resposta.status_code == 200
    data = resposta.json()
    assert data["reply"] == "Atendemos das 9h às 18h."
    assert data["conversation_id"]
    assert data["cached"] is False
    assert data["escalated"] is False
    assert data["cost_usd"] == 0.00123
    assert data["latency_ms"] == 42
    assert data["tools_used"] == ["buscar_documentos"]


def test_chat_estourou_rate_limit_devolve_429(
    api_com_dubles: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def sem_limite(tenant_id: str, identity: str) -> bool:
        return False

    monkeypatch.setattr("app.gateway.cache.check_rate_limit", sem_limite)
    resposta = api_com_dubles.post(
        "/chat", json={"message": "Oi"}, headers={"X-Api-Key": "demo-sorriso-123"}
    )
    assert resposta.status_code == 429


def test_ui_e_servida_na_raiz() -> None:
    resposta = TestClient(app).get("/")
    assert resposta.status_code == 200
    assert "text/html" in resposta.headers["content-type"]
    assert "atendo" in resposta.text.lower()


# ---------------------------------------------------------------------------
# Hardening: limites de entrada, configuração ausente e cabeçalhos.
# ---------------------------------------------------------------------------


def test_chat_sem_modelo_configurado_devolve_503(monkeypatch: pytest.MonkeyPatch) -> None:
    """Falha de configuração explicada — não um 500 opaco do gateway."""
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "")
    resposta = TestClient(app).post(
        "/chat", json={"message": "Oi"}, headers={"X-Api-Key": "demo-sorriso-123"}
    )
    assert resposta.status_code == 503
    assert "ANTHROPIC_API_KEY" in resposta.json()["detail"]


def test_cabecalhos_de_seguranca_presentes() -> None:
    resposta = TestClient(app).get("/health")
    assert resposta.headers["X-Content-Type-Options"] == "nosniff"
    assert resposta.headers["X-Frame-Options"] == "DENY"
    assert resposta.headers["Referrer-Policy"] == "no-referrer"

    ui = TestClient(app).get("/")
    assert "frame-ancestors 'none'" in ui.headers["Content-Security-Policy"]


def test_ingest_com_texto_gigante_devolve_422(api_com_dubles: TestClient) -> None:
    resposta = api_com_dubles.post(
        "/ingest",
        json={"source": "gigante.md", "text": "x" * 500_001},
        headers={"X-Api-Key": "demo-sorriso-123"},
    )
    assert resposta.status_code == 422


def test_metrics_com_days_fora_do_intervalo_devolve_422(api_com_dubles: TestClient) -> None:
    for days in (0, -5, 9999):
        resposta = api_com_dubles.get(
            f"/metrics/usage?days={days}", headers={"X-Api-Key": "demo-sorriso-123"}
        )
        assert resposta.status_code == 422


def test_conversation_id_gigante_devolve_422(api_com_dubles: TestClient) -> None:
    resposta = api_com_dubles.post(
        "/chat",
        json={"message": "Oi", "conversation_id": "c" * 65},
        headers={"X-Api-Key": "demo-sorriso-123"},
    )
    assert resposta.status_code == 422
