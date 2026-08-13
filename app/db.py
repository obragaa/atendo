"""Pool de conexões asyncpg e isolamento por tenant.

Toda leitura ou escrita de dado de cliente passa por `tenant_connection`:
ela abre a transação e define `app.tenant_id`, a variável que as policies
de Row Level Security usam para filtrar. A aplicação continua escrevendo
WHERE tenant_id nas queries — a RLS é a rede de segurança para o dia em que
alguém esquecer.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg

from app.config import Tenant, get_settings

_pool: asyncpg.Pool | None = None


async def _init_connection(conn: asyncpg.Connection) -> None:
    # jsonb entra e sai como dict, sem json.dumps espalhado pelo código.
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


async def init_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            get_settings().database_url, init=_init_connection, min_size=1, max_size=10
        )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Pool não inicializado — chame init_pool() no startup.")
    return _pool


@asynccontextmanager
async def tenant_connection(tenant_id: str) -> AsyncIterator[asyncpg.Connection]:
    """Conexão com o contexto do tenant aplicado.

    O set_config usa is_local=TRUE: o contexto vive só dentro da transação e
    morre com ela — a conexão volta limpa ao pool, sem vazar tenant entre
    requisições.
    """
    async with pool().acquire() as conn, conn.transaction():
        await conn.execute("SELECT set_config('app.tenant_id', $1, TRUE)", tenant_id)
        yield conn


def to_pgvector(values: list[float]) -> str:
    """Serializa um vetor como literal pgvector.

    asyncpg não conhece o tipo `vector`; o literal `[0.1,0.2,...]` com cast
    `$n::vector` no SQL evita depender de codec binário da extensão.
    """
    return "[" + ",".join(f"{v:.7g}" for v in values) + "]"


async def upsert_tenants(tenants: dict[str, Tenant]) -> None:
    """Sincroniza o catálogo YAML com a tabela tenants (alvo das FKs)."""
    async with pool().acquire() as conn:
        for tenant in tenants.values():
            await conn.execute(
                """
                INSERT INTO tenants (id, name, api_key_hash, active)
                VALUES ($1, $2, $3, TRUE)
                ON CONFLICT (id) DO UPDATE
                    SET name = EXCLUDED.name,
                        api_key_hash = EXCLUDED.api_key_hash,
                        active = TRUE
                """,
                tenant.id,
                tenant.name,
                tenant.api_key_hash,
            )
