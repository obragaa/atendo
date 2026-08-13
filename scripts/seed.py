"""Popula o banco para a demo: tenants + documentos de exemplo.

Os documentos da clínica vêm do arquivo de casos da avaliação — fonte única
de verdade: o que a demo responde é exatamente o que a suíte avalia. A
ingestão é idempotente; rodar o seed duas vezes não duplica nada.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import yaml

from app import db
from app.config import load_tenants
from app.rag import store

RAIZ = Path(__file__).resolve().parent.parent

DOCS_ADVOCACIA: dict[str, str] = {
    "consulta.md": (
        "Consulta inicial no Silva & Associados: R$ 350, com duração de até "
        "1 hora, nas modalidades presencial ou por videoconferência. O valor "
        "da consulta é abatido dos honorários caso o cliente contrate o "
        "escritório para a causa."
    ),
    "atuacao.md": (
        "Áreas de atuação do Silva & Associados: direito trabalhista "
        "(rescisões, verbas, assédio), direito de família (divórcio, pensão, "
        "guarda), direito do consumidor (cobranças indevidas, vícios de "
        "produto e serviço) e direito previdenciário (aposentadorias e "
        "benefícios do INSS)."
    ),
    "documentos.md": (
        "Documentos para a consulta inicial: documento de identidade e CPF. "
        "Casos trabalhistas: carteira de trabalho, contrato e holerites. "
        "Casos de família: certidões de casamento ou nascimento. Casos de "
        "consumidor: notas fiscais, contratos e protocolos de atendimento. "
        "Casos previdenciários: extrato CNIS e carta de concessão ou "
        "indeferimento do INSS."
    ),
    "honorarios.md": (
        "Honorários do Silva & Associados: definidos após a análise do caso "
        "na consulta inicial, formalizados em contrato escrito. Conforme o "
        "tipo de causa, podem combinar valor fixo, mensalidade ou percentual "
        "de êxito. O escritório não promete resultado nem prazo de processo."
    ),
}


async def main() -> None:
    await db.init_pool()
    try:
        tenants = load_tenants()
        await db.upsert_tenants(tenants)
        print(f"Tenants sincronizados: {', '.join(tenants)}")

        casos = yaml.safe_load(
            (RAIZ / "evals" / "cases" / "clinica-sorriso.yaml").read_text(encoding="utf-8")
        )
        for fixture in casos["fixtures"]:
            chunks = await store.ingest_document(
                "clinica-sorriso", fixture["source"], fixture["text"]
            )
            print(f"  clinica-sorriso/{fixture['source']}: {chunks} chunks")

        for source, texto in DOCS_ADVOCACIA.items():
            chunks = await store.ingest_document("adv-silva", source, texto)
            print(f"  adv-silva/{source}: {chunks} chunks")

        print("Seed concluído. (0 chunks = documento já estava ingerido.)")
    finally:
        await db.close_pool()


if __name__ == "__main__":
    asyncio.run(main())
