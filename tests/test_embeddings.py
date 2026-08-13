"""Testes do embedder de hashing: dimensão, determinismo e norma."""

from __future__ import annotations

import math

from app.rag.embeddings import HashingEmbedder


def _norma(vetor: list[float]) -> float:
    return math.sqrt(sum(v * v for v in vetor))


async def test_dimensao_fixa() -> None:
    embedder = HashingEmbedder(dim=256)
    vetores = await embedder.embed(["primeiro texto", "segundo texto bem maior que o outro"])
    assert all(len(v) == 256 for v in vetores)


async def test_determinismo() -> None:
    embedder = HashingEmbedder(dim=512)
    a = await embedder.embed_one("qual o preço da limpeza?")
    b = await embedder.embed_one("qual o preço da limpeza?")
    assert a == b


async def test_norma_unitaria() -> None:
    embedder = HashingEmbedder(dim=512)
    for texto in ["curto", "um texto um pouco mais longo com várias palavras", ""]:
        vetor = await embedder.embed_one(texto)
        assert math.isclose(_norma(vetor), 1.0, rel_tol=1e-9)


async def test_textos_diferentes_geram_vetores_diferentes() -> None:
    embedder = HashingEmbedder(dim=512)
    a = await embedder.embed_one("qual o preço da limpeza dental?")
    b = await embedder.embed_one("vocês atendem aos sábados?")
    assert a != b


async def test_textos_parecidos_ficam_mais_proximos_que_diferentes() -> None:
    """Sanidade da similaridade: paráfrase > assunto diferente."""
    embedder = HashingEmbedder(dim=1024)
    base = await embedder.embed_one("qual o preço da limpeza dental")
    parecido = await embedder.embed_one("qual o valor do preço da limpeza")
    distinto = await embedder.embed_one("documentos para abrir processo trabalhista")

    def cos(u: list[float], v: list[float]) -> float:
        return sum(a * b for a, b in zip(u, v, strict=True))

    assert cos(base, parecido) > cos(base, distinto)
