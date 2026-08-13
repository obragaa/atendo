"""Webhook da WhatsApp Cloud API (Meta).

Segurança antes de conveniência: o handshake exige verify token configurado
(sem bypass por configuração ausente), o POST valida a assinatura HMAC do
corpo antes de olhar o conteúdo, e o tenant é resolvido pelo phone_number_id
que a Meta envia — nunca por um campo controlado pelo remetente.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from app.config import Tenant, get_settings, load_tenants

logger = logging.getLogger(__name__)

router = APIRouter()

GRAPH_URL = "https://graph.facebook.com/v20.0"


@router.get("/webhooks/whatsapp")
async def verificar(request: Request) -> PlainTextResponse:
    """Handshake de inscrição da Meta."""
    settings = get_settings()
    if not settings.whatsapp_verify_token:
        # Sem token configurado não existe verificação legítima possível.
        raise HTTPException(status_code=503, detail="Webhook do WhatsApp não configurado.")

    params = request.query_params
    modo = params.get("hub.mode", "")
    token = params.get("hub.verify_token", "")
    challenge = params.get("hub.challenge", "")
    if modo == "subscribe" and hmac.compare_digest(token, settings.whatsapp_verify_token):
        return PlainTextResponse(challenge)
    raise HTTPException(status_code=403, detail="Token de verificação inválido.")


@router.post("/webhooks/whatsapp")
async def receber(request: Request) -> dict[str, str]:
    corpo = await request.body()
    assinatura = request.headers.get("X-Hub-Signature-256", "")
    if not signature_valida(corpo, assinatura):
        raise HTTPException(status_code=403, detail="Assinatura inválida.")

    try:
        payload = json.loads(corpo)
    except json.JSONDecodeError:
        return {"status": "ignorado"}

    mensagem = extract_message(payload)
    if mensagem is None:
        return {"status": "ignorado"}

    tenant = _tenant_por_phone_number_id(mensagem["phone_number_id"])
    if tenant is None:
        logger.warning("Mensagem para phone_number_id sem tenant: %s", mensagem["phone_number_id"])
        return {"status": "ignorado"}

    if not get_settings().anthropic_api_key:
        # Sem modelo configurado, responder 200 evita o loop de retries da
        # Meta; o problema é do operador e aparece no log, não no cliente.
        logger.error("Mensagem de WhatsApp recebida sem ANTHROPIC_API_KEY configurada.")
        return {"status": "sem_modelo"}

    conversation_id = conversation_id_para(tenant.id, mensagem["sender"])

    # Import tardio para evitar ciclo: main inclui este router no import.
    from app.main import _load_history, _persist_turn

    agent = request.app.state.agent
    history = await _load_history(tenant.id, conversation_id)
    reply = await agent.respond(tenant, conversation_id, history, mensagem["text"])
    await _persist_turn(
        tenant.id,
        conversation_id,
        "whatsapp",
        mensagem["text"],
        reply.text,
        external_id=mensagem["sender"],
    )
    await send_text(mensagem["sender"], reply.text)
    return {"status": "ok"}


def signature_valida(corpo: bytes, header: str) -> bool:
    """Valida o X-Hub-Signature-256 (formato "sha256=<hex>") do corpo cru.

    Sem App Secret configurado não há como validar — fail closed.
    """
    segredo = get_settings().whatsapp_app_secret
    if not segredo or not header.startswith("sha256="):
        return False
    esperado = hmac.new(segredo.encode("utf-8"), corpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(header.removeprefix("sha256="), esperado)


def extract_message(payload: Any) -> dict[str, str] | None:
    """Extrai a primeira mensagem de texto do payload da Meta.

    Payloads de status, tipos que não sejam texto e estruturas malformadas
    devolvem None — nunca levantam exceção.
    """
    try:
        value = payload["entry"][0]["changes"][0]["value"]
    except (KeyError, IndexError, TypeError):
        return None
    if not isinstance(value, dict):
        return None

    mensagens = value.get("messages")
    if not isinstance(mensagens, list) or not mensagens:
        return None  # payloads de status chegam sem "messages"
    mensagem = mensagens[0]
    if not isinstance(mensagem, dict) or mensagem.get("type") != "text":
        return None  # áudio, imagem, sticker etc.

    texto = mensagem.get("text")
    corpo = texto.get("body", "") if isinstance(texto, dict) else ""
    remetente = mensagem.get("from", "")
    metadata = value.get("metadata")
    phone_number_id = metadata.get("phone_number_id", "") if isinstance(metadata, dict) else ""
    if not corpo or not remetente or not phone_number_id:
        return None
    return {"text": corpo, "sender": remetente, "phone_number_id": phone_number_id}


def conversation_id_para(tenant_id: str, sender: str) -> str:
    """uuid5 determinístico sobre tenant:telefone.

    O mesmo cliente retoma a conversa de onde parou; tenants diferentes nunca
    compartilham conversa, mesmo com o mesmo telefone.
    """
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{tenant_id}:{sender}"))


def _tenant_por_phone_number_id(phone_number_id: str) -> Tenant | None:
    if not phone_number_id:
        return None
    for tenant in load_tenants().values():
        if tenant.whatsapp_phone_number_id == phone_number_id:
            return tenant
    return None


async def send_text(to: str, text: str) -> None:
    """Envia texto pelo Graph API; sem token configurado, loga em dry-run."""
    settings = get_settings()
    if not settings.whatsapp_access_token or not settings.whatsapp_phone_number_id:
        # Truncado: conteúdo de conversa é dado pessoal e não pertence a log.
        logger.info("[dry-run] WhatsApp para %s: %.80s", to, text)
        return
    url = f"{GRAPH_URL}/{settings.whatsapp_phone_number_id}/messages"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resposta = await client.post(
            url,
            headers={"Authorization": f"Bearer {settings.whatsapp_access_token}"},
            json={
                "messaging_product": "whatsapp",
                "to": to,
                "type": "text",
                "text": {"body": text},
            },
        )
        resposta.raise_for_status()
