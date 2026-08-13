"""Ingestão de documentos e busca vetorial por tenant."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from app.db import tenant_connection, to_pgvector
from app.rag.chunker import chunk_text, normalize
from app.rag.embeddings import get_embedder


@dataclass
class Passage:
    """Trecho recuperado da base do tenant, com a fonte e o score de cosseno."""

    content: str
    source: str
    score: float


async def ingest_document(tenant_id: str, source: str, text: str) -> int:
    """Ingere um documento e devolve quantos chunks foram criados.

    Idempotente pelo conteúdo: o SHA-256 do texto normalizado tem UNIQUE com
    o tenant no banco. Reingerir o mesmo arquivo devolve 0 sem duplicar nada.
    """
    texto = normalize(text)
    if not texto:
        return 0
    sha = hashlib.sha256(texto.encode("utf-8")).hexdigest()
    pedacos = chunk_text(texto)
    vetores = await get_embedder().embed(pedacos)

    async with tenant_connection(tenant_id) as conn:
        doc_id = await conn.fetchval(
            """
            INSERT INTO documents (tenant_id, source, content_sha)
            VALUES ($1, $2, $3)
            ON CONFLICT (tenant_id, content_sha) DO NOTHING
            RETURNING id
            """,
            tenant_id,
            source,
            sha,
        )
        if doc_id is None:
            return 0
        for ordinal, (pedaco, vetor) in enumerate(zip(pedacos, vetores, strict=True)):
            await conn.execute(
                """
                INSERT INTO chunks (tenant_id, document_id, ordinal, content, embedding)
                VALUES ($1, $2, $3, $4, $5::vector)
                """,
                tenant_id,
                doc_id,
                ordinal,
                pedaco,
                to_pgvector(vetor),
            )
    return len(pedacos)


async def search(
    tenant_id: str, query: str, limit: int = 5, min_score: float = 0.15
) -> list[Passage]:
    """Busca por similaridade de cosseno, descartando resultados fracos.

    Devolver nada é melhor que devolver ruído: sem passagem acima de
    `min_score`, o agente admite que não sabe — e isso custa menos que uma
    resposta inventada sobre preço.
    """
    vetor = await get_embedder().embed_one(query)
    async with tenant_connection(tenant_id) as conn:
        linhas = await conn.fetch(
            """
            SELECT c.content, d.source, 1 - (c.embedding <=> $2::vector) AS score
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.tenant_id = $1
            ORDER BY c.embedding <=> $2::vector
            LIMIT $3
            """,
            tenant_id,
            to_pgvector(vetor),
            limit,
        )
    return [
        Passage(content=linha["content"], source=linha["source"], score=float(linha["score"]))
        for linha in linhas
        if float(linha["score"]) >= min_score
    ]
