"""Providers de embedding.

Dois providers atrás da mesma interface: o de hashing (padrão) e um endpoint
compatível com a API de embeddings da OpenAI (inclui Ollama local). A escolha
é por configuração — o resto do código só conhece `Embedder`.
"""

from __future__ import annotations

import math
import re
from abc import ABC, abstractmethod
from functools import lru_cache
from hashlib import blake2b
from itertools import pairwise

import httpx

from app.config import get_settings

_PALAVRAS = re.compile(r"\w+", re.UNICODE)


class Embedder(ABC):
    """Interface comum: `dim` fixa e vetores normalizados."""

    dim: int

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_one(self, text: str) -> list[float]:
        return (await self.embed([text]))[0]


class HashingEmbedder(Embedder):
    """Embedding determinístico por projeção de n-gramas.

    Projeta unigramas e bigramas num vetor de dimensão fixa via blake2b, com
    sinal alternado pelo hash, e normaliza para norma 1. Não captura semântica
    como um modelo treinado — captura sobreposição de vocabulário — mas é
    determinístico, roda offline e não custa nada. É o padrão do projeto: é o
    que faz `git clone && make up` funcionar em qualquer máquina sem chave de
    API. Para qualidade de produção, configure EMBEDDING_PROVIDER=openai.
    """

    def __init__(self, dim: int = 1536) -> None:
        self.dim = dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vetor(texto) for texto in texts]

    def _vetor(self, texto: str) -> list[float]:
        vetor = [0.0] * self.dim
        for token in self._tokens(texto):
            digest = blake2b(token.encode("utf-8"), digest_size=8).digest()
            indice = int.from_bytes(digest[:4], "little") % self.dim
            sinal = 1.0 if digest[4] & 1 else -1.0
            vetor[indice] += sinal
        norma = math.sqrt(sum(v * v for v in vetor))
        if norma == 0.0:
            # Texto vazio: vetor unitário estável em vez de divisão por zero.
            vetor[0] = 1.0
            return vetor
        return [v / norma for v in vetor]

    @staticmethod
    def _tokens(texto: str) -> list[str]:
        palavras = [p.lower() for p in _PALAVRAS.findall(texto)]
        bigramas = [f"{a} {b}" for a, b in pairwise(palavras)]
        return palavras + bigramas


class OpenAIEmbedder(Embedder):
    """POST {base_url}/embeddings — OpenAI ou qualquer endpoint compatível."""

    def __init__(self, model: str, api_key: str, base_url: str, dim: int) -> None:
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.dim = dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resposta = await client.post(
                f"{self.base_url}/embeddings",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "input": texts, "dimensions": self.dim},
            )
            resposta.raise_for_status()
        itens = resposta.json()["data"]
        # A API não garante ordem; reordena por index antes de devolver.
        itens.sort(key=lambda item: item["index"])
        return [item["embedding"] for item in itens]


@lru_cache
def get_embedder() -> Embedder:
    """Singleton do provider ativo. openai exige chave; sem chave, hashing."""
    settings = get_settings()
    if settings.embedding_provider == "openai" and settings.embedding_api_key:
        return OpenAIEmbedder(
            model=settings.embedding_model,
            api_key=settings.embedding_api_key,
            base_url=settings.embedding_base_url,
            dim=settings.embedding_dim,
        )
    return HashingEmbedder(dim=settings.embedding_dim)
