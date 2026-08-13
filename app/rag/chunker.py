"""Divisão de texto em chunks para indexação vetorial.

Estratégia em cascata: o texto quebra em parágrafos; parágrafo maior que o
limite vira sentenças; sentença maior que o limite quebra por palavra. As
unidades são então agrupadas até encher cada chunk, com sobreposição do fim
do chunk anterior — a sobreposição evita que uma resposta fique cortada na
fronteira entre dois chunks.
"""

from __future__ import annotations

import re

_FIM_DE_SENTENCA = re.compile(r"(?<=[.!?…])\s+")


def normalize(text: str) -> str:
    """Colapsa espaços, normaliza quebras de linha e reduz 3+ linhas em
    branco para 2 (um parágrafo em branco)."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(text: str, size: int = 900, overlap: int = 120) -> list[str]:
    """Divide `text` em chunks de até `size` caracteres.

    `overlap` é o número de caracteres do fim de um chunk repetidos no início
    do seguinte. Nenhum conteúdo se perde: toda unidade da entrada aparece
    inteira em algum chunk.
    """
    if size <= 0:
        raise ValueError(f"size deve ser positivo, recebi {size}")
    if overlap < 0 or overlap >= size:
        raise ValueError(f"overlap deve estar em [0, size), recebi {overlap} para size={size}")

    texto = normalize(text)
    if not texto:
        return []

    # Unidades cabem em size - overlap - 1 para que, mesmo precedidas da
    # cauda de sobreposição, o chunk nunca ultrapasse `size`.
    limite_unidade = max(1, size - overlap - 1)
    unidades = _unidades(texto, limite_unidade)

    chunks: list[str] = []
    atual = ""
    for unidade in unidades:
        if not atual:
            atual = unidade
        elif len(atual) + 1 + len(unidade) <= size:
            atual = f"{atual} {unidade}"
        else:
            chunks.append(atual)
            cauda = atual[-overlap:].lstrip() if overlap else ""
            atual = f"{cauda} {unidade}" if cauda else unidade
    if atual:
        chunks.append(atual)
    return chunks


def _unidades(texto: str, limite: int) -> list[str]:
    """Cascata parágrafo → sentença → palavra, garantindo unidades <= limite."""
    unidades: list[str] = []
    for paragrafo in texto.split("\n\n"):
        paragrafo = paragrafo.strip().replace("\n", " ")
        if not paragrafo:
            continue
        if len(paragrafo) <= limite:
            unidades.append(paragrafo)
            continue
        for sentenca in _FIM_DE_SENTENCA.split(paragrafo):
            sentenca = sentenca.strip()
            if not sentenca:
                continue
            if len(sentenca) <= limite:
                unidades.append(sentenca)
            else:
                unidades.extend(_por_palavras(sentenca, limite))
    return unidades


def _por_palavras(sentenca: str, limite: int) -> list[str]:
    partes: list[str] = []
    atual = ""
    for palavra in sentenca.split(" "):
        # Palavra sozinha maior que o limite (URL, código): fatia dura.
        while len(palavra) > limite:
            if atual:
                partes.append(atual)
                atual = ""
            partes.append(palavra[:limite])
            palavra = palavra[limite:]
        if not palavra:
            continue
        if not atual:
            atual = palavra
        elif len(atual) + 1 + len(palavra) <= limite:
            atual = f"{atual} {palavra}"
        else:
            partes.append(atual)
            atual = palavra
    if atual:
        partes.append(atual)
    return partes
