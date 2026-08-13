"""API HTTP do Atendo: rotas, autenticação e histórico de conversas.

Nenhum endpoint aceita tenant_id como parâmetro: o tenant vem sempre da
chave de API. O cliente não escolhe quem ele é — a chave escolhe.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from app import db
from app.agent.loop import Agent
from app.channels import whatsapp
from app.config import Tenant, get_settings, load_tenants, tenant_by_api_key
from app.gateway import cache, usage
from app.gateway.llm import LLMGateway
from app.rag import store
from app.telemetry import setup_telemetry

logger = logging.getLogger(__name__)

UI_INDEX = Path(__file__).resolve().parent / "ui" / "index.html"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_telemetry()
    await db.init_pool()
    await db.upsert_tenants(load_tenants())
    app.state.gateway = LLMGateway()
    app.state.agent = Agent(app.state.gateway)
    logger.info("Atendo no ar com %d tenants.", len(load_tenants()))
    yield
    await db.close_pool()


app = FastAPI(title="Atendo", version="1.0.0", lifespan=lifespan)
app.include_router(whatsapp.router)

# CSP da UI: tudo inline e mesma origem — nenhum CDN, nenhum script externo.
# Aplicada só na página da UI para não quebrar o Swagger de /docs.
CSP_UI = (
    "default-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "script-src 'self' 'unsafe-inline'; "
    "connect-src 'self'; "
    "img-src 'self' data:; "
    "frame-ancestors 'none'; "
    "base-uri 'none'; "
    "form-action 'self'"
)


@app.middleware("http")
async def security_headers(request: Request, call_next: Any) -> Any:
    """Cabeçalhos de segurança em toda resposta.

    A API é consumida por widget e integrações — nada aqui deve poder ser
    embutido em iframe de terceiros nem ter o tipo de conteúdo adivinhado.
    """
    resposta = await call_next(request)
    resposta.headers.setdefault("X-Content-Type-Options", "nosniff")
    resposta.headers.setdefault("X-Frame-Options", "DENY")
    resposta.headers.setdefault("Referrer-Policy", "no-referrer")
    resposta.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if request.url.path == "/":
        resposta.headers.setdefault("Content-Security-Policy", CSP_UI)
    return resposta


def current_tenant(x_api_key: str = Header(default="")) -> Tenant:
    """Autentica pelo header X-Api-Key. 401 sem header ou com chave inválida."""
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Informe o header X-Api-Key.")
    tenant = tenant_by_api_key(x_api_key)
    if tenant is None:
        raise HTTPException(status_code=401, detail="Chave de API inválida.")
    return tenant


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = Field(default=None, max_length=64)


class ChatResponse(BaseModel):
    reply: str
    conversation_id: str
    cached: bool
    escalated: bool
    cost_usd: float
    latency_ms: int
    tools_used: list[str]


class IngestRequest(BaseModel):
    source: str = Field(min_length=1, max_length=200)
    # Teto de 500k caracteres: documento maior que isso é abuso ou engano,
    # e sem teto o endpoint vira vetor de exaustão de memória e de banco.
    text: str = Field(min_length=1, max_length=500_000)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(UI_INDEX, media_type="text/html")


@app.post("/chat", response_model=ChatResponse)
async def chat(
    corpo: ChatRequest,
    request: Request,
    tenant: Tenant = Depends(current_tenant),
) -> ChatResponse:
    if not get_settings().anthropic_api_key:
        # Falha de configuração explicada, em vez de um 500 opaco do gateway.
        raise HTTPException(
            status_code=503,
            detail=(
                "Modelo não configurado: defina ANTHROPIC_API_KEY no arquivo .env e reinicie a API."
            ),
        )

    identidade = request.client.host if request.client else "desconhecido"
    if not await cache.check_rate_limit(tenant.id, identidade):
        raise HTTPException(
            status_code=429, detail="Muitas mensagens em um minuto; aguarde um instante."
        )

    conversation_id = corpo.conversation_id or str(uuid.uuid4())
    history = await _load_history(tenant.id, conversation_id)
    agent: Agent = request.app.state.agent
    reply = await agent.respond(tenant, conversation_id, history, corpo.message)
    await _persist_turn(tenant.id, conversation_id, "web", corpo.message, reply.text)

    return ChatResponse(
        reply=reply.text,
        conversation_id=conversation_id,
        cached=reply.cached,
        escalated=reply.escalated,
        cost_usd=round(reply.cost_usd, 6),
        latency_ms=reply.latency_ms,
        tools_used=reply.tools_used,
    )


@app.post("/ingest")
async def ingest(corpo: IngestRequest, tenant: Tenant = Depends(current_tenant)) -> dict[str, int]:
    chunks = await store.ingest_document(tenant.id, corpo.source, corpo.text)
    return {"chunks_criados": chunks}


@app.get("/metrics/usage")
async def metrics_usage(
    days: int = Query(default=30, ge=1, le=365),
    tenant: Tenant = Depends(current_tenant),
) -> dict[str, Any]:
    return await usage.summary(tenant.id, days=days)


@app.get("/appointments")
async def appointments(tenant: Tenant = Depends(current_tenant)) -> list[dict[str, Any]]:
    async with db.tenant_connection(tenant.id) as conn:
        linhas = await conn.fetch(
            """
            SELECT customer, phone, service, starts_at, status
            FROM appointments
            WHERE tenant_id = $1
            ORDER BY starts_at
            """,
            tenant.id,
        )
    return [
        {
            "customer": linha["customer"],
            "phone": linha["phone"],
            "service": linha["service"],
            "starts_at": linha["starts_at"].isoformat(),
            "status": linha["status"],
        }
        for linha in linhas
    ]


async def _load_history(
    tenant_id: str, conversation_id: str, limit: int = 10
) -> list[dict[str, Any]]:
    """Últimas mensagens da conversa, em ordem cronológica."""
    async with db.tenant_connection(tenant_id) as conn:
        linhas = await conn.fetch(
            """
            SELECT role, content FROM messages
            WHERE tenant_id = $1 AND conversation_id = $2
            ORDER BY created_at DESC, id DESC
            LIMIT $3
            """,
            tenant_id,
            conversation_id,
            limit,
        )
    return [{"role": linha["role"], "content": linha["content"]} for linha in reversed(linhas)]


async def _persist_turn(
    tenant_id: str,
    conversation_id: str,
    channel: str,
    user_message: str,
    assistant_message: str,
    external_id: str | None = None,
) -> None:
    """Cria a conversa se necessário e grava o par de mensagens do turno."""
    async with db.tenant_connection(tenant_id) as conn:
        await conn.execute(
            """
            INSERT INTO conversations (id, tenant_id, channel, external_id)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (id) DO NOTHING
            """,
            conversation_id,
            tenant_id,
            channel,
            external_id,
        )
        await conn.execute(
            """
            INSERT INTO messages (tenant_id, conversation_id, role, content)
            VALUES ($1, $2, 'user', $3), ($1, $2, 'assistant', $4)
            """,
            tenant_id,
            conversation_id,
            user_message,
            assistant_message,
        )


@app.exception_handler(Exception)
async def erro_interno(request: Request, exc: Exception) -> JSONResponse:
    """Loga o stack trace e devolve mensagem neutra — sem vazar detalhes."""
    logger.exception("Erro não tratado em %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Erro interno. Tente novamente em instantes."},
    )
