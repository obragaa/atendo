"""Cache semântico (Postgres) e rate limit (Redis).

Cada armazenamento com o que corresponde à sua natureza: o cache semântico
exige busca por similaridade e o pgvector já está no projeto — adicionar
RediSearch seria uma dependência de produção inteira para um problema que o
banco existente resolve. O rate limit é contador volátil de alta frequência
com perda tolerável: Redis.

O limiar de 0.96 é alto de propósito: falso negativo custa uma chamada de
modelo; falso positivo entrega a resposta errada ao cliente final.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import redis.asyncio as aioredis

from app.config import get_settings
from app.db import tenant_connection, to_pgvector
from app.rag.embeddings import get_embedder


@dataclass
class CacheHit:
    answer: str
    score: float


async def lookup(tenant_id: str, question: str) -> CacheHit | None:
    """Busca o vizinho mais próximo não expirado; só devolve acima do limiar."""
    settings = get_settings()
    vetor = await get_embedder().embed_one(question)
    async with tenant_connection(tenant_id) as conn:
        linha = await conn.fetchrow(
            """
            SELECT id, answer, 1 - (embedding <=> $2::vector) AS score
            FROM semantic_cache
            WHERE tenant_id = $1 AND expires_at > now()
            ORDER BY embedding <=> $2::vector
            LIMIT 1
            """,
            tenant_id,
            to_pgvector(vetor),
        )
        if linha is None or float(linha["score"]) < settings.cache_similarity_threshold:
            return None
        await conn.execute("UPDATE semantic_cache SET hits = hits + 1 WHERE id = $1", linha["id"])
        return CacheHit(answer=linha["answer"], score=float(linha["score"]))


async def store(tenant_id: str, question: str, answer: str) -> None:
    settings = get_settings()
    vetor = await get_embedder().embed_one(question)
    async with tenant_connection(tenant_id) as conn:
        await conn.execute(
            """
            INSERT INTO semantic_cache (tenant_id, question, answer, embedding, expires_at)
            VALUES ($1, $2, $3, $4::vector, now() + make_interval(secs => $5))
            """,
            tenant_id,
            question,
            answer,
            to_pgvector(vetor),
            settings.cache_ttl_seconds,
        )


@lru_cache
def _redis() -> aioredis.Redis:
    return aioredis.from_url(get_settings().redis_url, decode_responses=True)


async def check_rate_limit(tenant_id: str, identity: str) -> bool:
    """INCR com EXPIRE de 60s na primeira ocorrência. True = dentro do limite."""
    settings = get_settings()
    chave = f"ratelimit:{tenant_id}:{identity}"
    cliente = _redis()
    contagem = await cliente.incr(chave)
    if contagem == 1:
        await cliente.expire(chave, 60)
    return int(contagem) <= settings.rate_limit_per_minute
