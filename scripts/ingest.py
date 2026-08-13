"""Ingestão de documentos na base de um tenant.

Uso:
    python -m scripts.ingest --tenant clinica-sorriso --path ./docs
    python -m scripts.ingest --tenant adv-silva --path ./contrato.pdf

Aceita .txt, .md e .pdf (via pypdf); diretórios são varridos recursivamente.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from app import db
from app.config import load_tenants
from app.rag import store

EXTENSOES = {".txt", ".md", ".pdf"}


def ler_arquivo(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return "\n\n".join((pagina.extract_text() or "") for pagina in reader.pages)
    return path.read_text(encoding="utf-8", errors="replace")


def coletar_arquivos(alvo: Path) -> list[Path]:
    if alvo.is_file():
        if alvo.suffix.lower() not in EXTENSOES:
            raise SystemExit(f"Extensão não suportada: {alvo.suffix} (aceito: .txt .md .pdf)")
        return [alvo]
    if alvo.is_dir():
        return sorted(p for p in alvo.rglob("*") if p.suffix.lower() in EXTENSOES)
    raise SystemExit(f"Caminho não encontrado: {alvo}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Ingere documentos na base de um tenant.")
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--path", required=True)
    args = parser.parse_args()

    if args.tenant not in load_tenants():
        print(f"Tenant desconhecido: {args.tenant}. Disponíveis: {', '.join(load_tenants())}")
        sys.exit(2)

    arquivos = coletar_arquivos(Path(args.path))
    if not arquivos:
        print("Nenhum arquivo .txt, .md ou .pdf encontrado.")
        sys.exit(2)

    await db.init_pool()
    try:
        total = 0
        for arquivo in arquivos:
            chunks = await store.ingest_document(args.tenant, arquivo.name, ler_arquivo(arquivo))
            print(f"  {arquivo}: {chunks} chunks")
            total += chunks
        print(f"Ingestão concluída: {total} chunks novos. (0 = já estava ingerido.)")
    finally:
        await db.close_pool()


if __name__ == "__main__":
    asyncio.run(main())
