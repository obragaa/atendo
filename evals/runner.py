"""Runner da suíte de avaliação.

Sem isso, "melhorei o prompt" é opinião. O runner injeta os fixtures, roda
cada caso contra o agente real e sai com código 1 quando a taxa de acerto
fica abaixo do limiar — é o que bloqueia o merge no CI.

Uso:
    python -m evals.runner --min-pass-rate 0.85 [--tenant clinica-sorriso]
                           [--json evals-report.json]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import unicodedata
from pathlib import Path
from typing import Any

import yaml

from app import db
from app.agent.loop import Agent, AgentReply
from app.config import get_settings, load_tenants
from app.gateway.llm import LLMGateway
from app.rag import store

CASES_DIR = Path(__file__).resolve().parent / "cases"


def folding(texto: str) -> str:
    """Minúsculas e sem acento: 'Não' e 'nao' comparam iguais."""
    nfd = unicodedata.normalize("NFD", texto.casefold())
    return "".join(c for c in nfd if not unicodedata.combining(c))


def avaliar(caso: dict[str, Any], reply: AgentReply) -> tuple[bool, str]:
    """Aplica expect_any (basta um), forbid (nenhum) e must_use_tool."""
    texto = folding(reply.text)

    esperados = caso.get("expect_any") or []
    if esperados and not any(folding(e) in texto for e in esperados):
        return False, f"nenhum termo esperado apareceu ({', '.join(esperados[:4])}…)"

    for proibido in caso.get("forbid") or []:
        if folding(proibido) in texto:
            return False, f"apareceu termo proibido: {proibido!r}"

    ferramenta = caso.get("must_use_tool")
    if ferramenta and ferramenta not in reply.tools_used:
        return False, f"não usou a ferramenta obrigatória {ferramenta!r}"

    return True, "ok"


async def rodar(args: argparse.Namespace) -> int:
    if not get_settings().anthropic_api_key:
        print("ANTHROPIC_API_KEY não configurada — a avaliação chama o modelo real.")
        return 2

    caso_path = CASES_DIR / f"{args.tenant}.yaml"
    if not caso_path.exists():
        print(f"Arquivo de casos não encontrado: {caso_path}")
        return 2
    dados = yaml.safe_load(caso_path.read_text(encoding="utf-8"))
    tenant = load_tenants()[dados["tenant"]]

    await db.init_pool()
    try:
        await db.upsert_tenants(load_tenants())

        # Cache limpo antes da rodada: a suíte mede o modelo, não o cache —
        # senão a segunda execução avaliaria respostas decoradas.
        async with db.tenant_connection(tenant.id) as conn:
            await conn.execute("DELETE FROM semantic_cache WHERE tenant_id = $1", tenant.id)

        for fixture in dados.get("fixtures", []):
            await store.ingest_document(tenant.id, fixture["source"], fixture["text"])

        agent = Agent(LLMGateway())
        resultados: list[dict[str, Any]] = []
        custo_total = 0.0
        latencias: list[int] = []

        for caso in dados["cases"]:
            reply = await agent.respond(tenant, f"eval-{caso['id']}", [], caso["message"])
            aprovado, motivo = avaliar(caso, reply)
            custo_total += reply.cost_usd
            latencias.append(reply.latency_ms)
            resultados.append(
                {
                    "id": caso["id"],
                    "aprovado": aprovado,
                    "motivo": motivo,
                    "resposta": reply.text,
                    "tools_used": reply.tools_used,
                    "cost_usd": round(reply.cost_usd, 6),
                    "latency_ms": reply.latency_ms,
                    "escalated": reply.escalated,
                }
            )
            status = "PASS" if aprovado else "FAIL"
            print(f"[{status}] {caso['id']:<22} {motivo}")
            if not aprovado:
                print(f"       resposta: {reply.text[:180]}")

        aprovados = sum(1 for r in resultados if r["aprovado"])
        taxa = aprovados / len(resultados) if resultados else 0.0
        latencia_media = int(sum(latencias) / len(latencias)) if latencias else 0

        print("-" * 60)
        print(
            f"Taxa de acerto: {taxa:.0%} ({aprovados}/{len(resultados)})  |  "
            f"custo total: ${custo_total:.5f}  |  latência média: {latencia_media} ms"
        )

        if args.json_path:
            relatorio = {
                "tenant": tenant.id,
                "pass_rate": round(taxa, 4),
                "min_pass_rate": args.min_pass_rate,
                "cost_usd": round(custo_total, 6),
                "avg_latency_ms": latencia_media,
                "cases": resultados,
            }
            Path(args.json_path).write_text(
                json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(f"Relatório gravado em {args.json_path}")

        if taxa < args.min_pass_rate:
            print(f"REPROVADO: taxa {taxa:.0%} abaixo do mínimo {args.min_pass_rate:.0%}.")
            return 1
        return 0
    finally:
        await db.close_pool()


def main() -> None:
    parser = argparse.ArgumentParser(description="Roda a suíte de avaliação do Atendo.")
    parser.add_argument("--min-pass-rate", type=float, default=0.85)
    parser.add_argument("--tenant", default="clinica-sorriso")
    parser.add_argument("--json", dest="json_path", default="")
    args = parser.parse_args()
    sys.exit(asyncio.run(rodar(args)))


if __name__ == "__main__":
    main()
