"""Testes do webhook do WhatsApp: extração, assinatura HMAC e identidade.

O TestClient nunca sobe lifespan (sem banco): os cenários de assinatura usam
payload de status — validado e ignorado antes de tocar agente ou banco.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.agent.loop import AgentReply
from app.channels.whatsapp import conversation_id_para, extract_message, signature_valida
from app.config import get_settings
from app.main import app

SEGREDO = "app-secret-de-teste"


def payload_texto(
    phone_number_id: str = "111000000000001",
    sender: str = "5511999998888",
    texto: str = "Olá!",
) -> dict[str, Any]:
    """Payload no formato real da Cloud API para mensagem de texto."""
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "123456",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "551140020022",
                                "phone_number_id": phone_number_id,
                            },
                            "contacts": [{"profile": {"name": "Cliente"}, "wa_id": sender}],
                            "messages": [
                                {
                                    "from": sender,
                                    "id": "wamid.ABC",
                                    "timestamp": "1700000000",
                                    "type": "text",
                                    "text": {"body": texto},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


def payload_status() -> dict[str, Any]:
    """Atualização de entrega — chega sem 'messages'."""
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {"phone_number_id": "111000000000001"},
                            "statuses": [{"id": "wamid.ABC", "status": "delivered"}],
                        },
                    }
                ]
            }
        ],
    }


def payload_audio() -> dict[str, Any]:
    payload = payload_texto()
    payload["entry"][0]["changes"][0]["value"]["messages"][0] = {
        "from": "5511999998888",
        "id": "wamid.AUD",
        "type": "audio",
        "audio": {"id": "media-id"},
    }
    return payload


def _assinar(corpo: bytes, segredo: str = SEGREDO) -> str:
    return "sha256=" + hmac.new(segredo.encode("utf-8"), corpo, hashlib.sha256).hexdigest()


@pytest.fixture
def cliente(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(get_settings(), "whatsapp_app_secret", SEGREDO)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Extração.
# ---------------------------------------------------------------------------


def test_extrai_mensagem_de_texto() -> None:
    mensagem = extract_message(payload_texto(texto="Quanto custa a limpeza?"))
    assert mensagem == {
        "text": "Quanto custa a limpeza?",
        "sender": "5511999998888",
        "phone_number_id": "111000000000001",
    }


def test_ignora_payload_de_status() -> None:
    assert extract_message(payload_status()) is None


def test_ignora_audio() -> None:
    assert extract_message(payload_audio()) is None


@pytest.mark.parametrize(
    "malformado",
    [
        None,
        {},
        [],
        "texto solto",
        {"entry": []},
        {"entry": [{}]},
        {"entry": [{"changes": []}]},
        {"entry": [{"changes": [{}]}]},
        {"entry": [{"changes": [{"value": None}]}]},
        {"entry": [{"changes": [{"value": {"messages": "não é lista"}}]}]},
        {"entry": [{"changes": [{"value": {"messages": [{"type": "text"}]}}]}]},
    ],
)
def test_payload_malformado_nao_quebra(malformado: Any) -> None:
    assert extract_message(malformado) is None


# ---------------------------------------------------------------------------
# Assinatura HMAC.
# ---------------------------------------------------------------------------


def test_assinatura_valida_passa(cliente: TestClient) -> None:
    corpo = json.dumps(payload_status()).encode()
    resposta = cliente.post(
        "/webhooks/whatsapp",
        content=corpo,
        headers={"X-Hub-Signature-256": _assinar(corpo), "content-type": "application/json"},
    )
    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ignorado"}


def test_assinatura_invalida_falha(cliente: TestClient) -> None:
    corpo = json.dumps(payload_status()).encode()
    resposta = cliente.post(
        "/webhooks/whatsapp",
        content=corpo,
        headers={"X-Hub-Signature-256": "sha256=" + "0" * 64},
    )
    assert resposta.status_code == 403


def test_assinatura_ausente_falha(cliente: TestClient) -> None:
    corpo = json.dumps(payload_status()).encode()
    resposta = cliente.post("/webhooks/whatsapp", content=corpo)
    assert resposta.status_code == 403


def test_sem_app_secret_recusa_mesmo_com_assinatura(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configuração ausente não vira bypass: fail closed."""
    monkeypatch.setattr(get_settings(), "whatsapp_app_secret", "")
    corpo = json.dumps(payload_status()).encode()
    resposta = TestClient(app).post(
        "/webhooks/whatsapp",
        content=corpo,
        headers={"X-Hub-Signature-256": _assinar(corpo)},
    )
    assert resposta.status_code == 403


def test_signature_valida_direto() -> None:
    corpo = b'{"qualquer": "coisa"}'
    settings = get_settings()
    original = settings.whatsapp_app_secret
    settings.whatsapp_app_secret = SEGREDO
    try:
        assert signature_valida(corpo, _assinar(corpo)) is True
        assert signature_valida(corpo, _assinar(corpo, "outro-segredo")) is False
        assert signature_valida(corpo, "") is False
        assert signature_valida(corpo, "md5=abc") is False
    finally:
        settings.whatsapp_app_secret = original


# ---------------------------------------------------------------------------
# Handshake (GET).
# ---------------------------------------------------------------------------


def test_handshake_sem_token_configurado_devolve_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "whatsapp_verify_token", "")
    resposta = TestClient(app).get(
        "/webhooks/whatsapp",
        params={"hub.mode": "subscribe", "hub.verify_token": "x", "hub.challenge": "42"},
    )
    assert resposta.status_code == 503


def test_handshake_com_token_correto_devolve_challenge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "whatsapp_verify_token", "token-verificacao")
    resposta = TestClient(app).get(
        "/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "token-verificacao",
            "hub.challenge": "42",
        },
    )
    assert resposta.status_code == 200
    assert resposta.text == "42"


# ---------------------------------------------------------------------------
# Identidade de conversa.
# ---------------------------------------------------------------------------


def test_conversation_id_estavel_por_telefone() -> None:
    a = conversation_id_para("clinica-sorriso", "5511999998888")
    b = conversation_id_para("clinica-sorriso", "5511999998888")
    assert a == b


def test_conversation_id_diferente_entre_tenants() -> None:
    a = conversation_id_para("clinica-sorriso", "5511999998888")
    b = conversation_id_para("adv-silva", "5511999998888")
    assert a != b


# ---------------------------------------------------------------------------
# Fluxo completo com agente dublê (sem banco, sem rede).
# ---------------------------------------------------------------------------


def test_fluxo_completo_com_agente_fake(
    cliente: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    enviados: list[tuple[str, str]] = []

    class FakeAgent:
        async def respond(
            self, tenant: Any, conversation_id: str, history: Any, message: str
        ) -> AgentReply:
            return AgentReply(text=f"eco: {message}", conversation_id=conversation_id)

    async def fake_history(tenant_id: str, conversation_id: str, limit: int = 10) -> list:
        return []

    async def fake_persist(*args: Any, **kwargs: Any) -> None:
        return None

    async def fake_send(to: str, text: str) -> None:
        enviados.append((to, text))

    monkeypatch.setattr("app.main._load_history", fake_history)
    monkeypatch.setattr("app.main._persist_turn", fake_persist)
    monkeypatch.setattr("app.channels.whatsapp.send_text", fake_send)
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "chave-de-teste")
    app.state.agent = FakeAgent()

    corpo = json.dumps(payload_texto(texto="Oi, tudo bem?")).encode()
    resposta = cliente.post(
        "/webhooks/whatsapp",
        content=corpo,
        headers={"X-Hub-Signature-256": _assinar(corpo), "content-type": "application/json"},
    )
    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok"}
    assert enviados == [("5511999998888", "eco: Oi, tudo bem?")]
