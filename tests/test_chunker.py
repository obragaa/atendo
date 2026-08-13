"""Testes do chunker: normalização, cascata e invariantes de tamanho."""

from __future__ import annotations

import pytest

from app.rag.chunker import chunk_text, normalize


def test_normalize_colapsa_espacos_e_linhas() -> None:
    entrada = "Olá   mundo\t!\r\nSegunda    linha\n\n\n\n\nNovo parágrafo  "
    esperado = "Olá mundo !\nSegunda linha\n\nNovo parágrafo"
    assert normalize(entrada) == esperado


def test_texto_curto_vira_um_chunk() -> None:
    chunks = chunk_text("Um texto pequeno que cabe inteiro.", size=900, overlap=120)
    assert chunks == ["Um texto pequeno que cabe inteiro."]


def test_texto_vazio_nao_gera_chunk() -> None:
    assert chunk_text("") == []
    assert chunk_text("   \n\n  \t ") == []


def test_respeita_o_tamanho_maximo() -> None:
    texto = "\n\n".join(
        f"Parágrafo número {i} com um punhado de palavras para ocupar espaço." for i in range(40)
    )
    for size, overlap in [(900, 120), (200, 40), (80, 10)]:
        for chunk in chunk_text(texto, size=size, overlap=overlap):
            assert len(chunk) <= size


def test_sentenca_gigante_e_quebrada() -> None:
    # Uma "sentença" sem pontuação maior que o chunk inteiro.
    sentenca = " ".join(f"palavra{i}" for i in range(300))
    chunks = chunk_text(sentenca, size=200, overlap=20)
    assert len(chunks) > 1
    assert all(len(c) <= 200 for c in chunks)


def test_palavra_maior_que_o_limite_e_fatiada() -> None:
    palavra = "x" * 500
    chunks = chunk_text(palavra, size=100, overlap=10)
    assert all(len(c) <= 100 for c in chunks)
    assert sum(c.count("x") for c in chunks) >= 500


def test_overlap_maior_ou_igual_ao_size_levanta_erro() -> None:
    with pytest.raises(ValueError):
        chunk_text("qualquer texto", size=100, overlap=100)
    with pytest.raises(ValueError):
        chunk_text("qualquer texto", size=100, overlap=150)
    with pytest.raises(ValueError):
        chunk_text("qualquer texto", size=0, overlap=0)
    with pytest.raises(ValueError):
        chunk_text("qualquer texto", size=100, overlap=-1)


def test_nenhum_conteudo_se_perde() -> None:
    """Toda palavra da entrada normalizada aparece em algum chunk."""
    texto = "\n\n".join(
        f"Bloco {i}: preço do serviço {i} é {i * 10} reais. Convênio aceito: Plano{i}."
        for i in range(30)
    )
    chunks = chunk_text(texto, size=180, overlap=30)
    conteudo = " ".join(chunks)
    for palavra in normalize(texto).replace("\n", " ").split(" "):
        assert palavra in conteudo


def test_overlap_repete_o_fim_do_chunk_anterior() -> None:
    texto = " ".join(f"palavra{i}" for i in range(200))
    chunks = chunk_text(texto, size=150, overlap=40)
    assert len(chunks) >= 2
    # O início do segundo chunk deve conter o fim do primeiro.
    cauda = chunks[0][-20:].split(" ")[-1]
    assert cauda in chunks[1]
