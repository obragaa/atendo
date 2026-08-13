"""Contabilidade de custo: uma linha em usage_events por chamada de modelo.

usage_events é a fonte do preço cobrado do cliente. cost_per_conversation_usd
é a métrica que permite precificar a mensalidade com margem conhecida em vez
de chute: mensalidade viável = custo por conversa × conversas/mês × margem.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.db import pool


@dataclass
class UsageRecord:
    tenant_id: str
    conversation_id: str | None
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    cached: bool = False
    escalated: bool = False
    latency_ms: int = 0


async def record(registro: UsageRecord) -> None:
    async with pool().acquire() as conn:
        await conn.execute(
            """
            INSERT INTO usage_events
                (tenant_id, conversation_id, model, input_tokens, output_tokens,
                 cost_usd, cached, escalated, latency_ms)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """,
            registro.tenant_id,
            registro.conversation_id,
            registro.model,
            registro.input_tokens,
            registro.output_tokens,
            registro.cost_usd,
            registro.cached,
            registro.escalated,
            registro.latency_ms,
        )


async def summary(tenant_id: str, days: int = 30) -> dict:
    """Resumo de uso dos últimos `days` dias, com o custo por conversa."""
    async with pool().acquire() as conn:
        linha = await conn.fetchrow(
            """
            SELECT count(*)                                            AS calls,
                   count(DISTINCT conversation_id)                     AS conversations,
                   COALESCE(sum(cost_usd), 0)                          AS cost_usd,
                   COALESCE(avg(latency_ms), 0)                        AS avg_latency_ms,
                   COALESCE(avg(CASE WHEN cached THEN 1.0 ELSE 0 END), 0)    AS cache_hit_rate,
                   COALESCE(avg(CASE WHEN escalated THEN 1.0 ELSE 0 END), 0) AS escalation_rate
            FROM usage_events
            WHERE tenant_id = $1
              AND created_at >= now() - make_interval(days => $2)
            """,
            tenant_id,
            days,
        )
    conversas = int(linha["conversations"] or 0)
    custo = float(linha["cost_usd"])
    return {
        "calls": int(linha["calls"]),
        "conversations": conversas,
        "cost_usd": round(custo, 6),
        "cost_per_conversation_usd": round(custo / conversas, 6) if conversas else 0.0,
        "avg_latency_ms": int(linha["avg_latency_ms"]),
        "cache_hit_rate": round(float(linha["cache_hit_rate"]), 4),
        "escalation_rate": round(float(linha["escalation_rate"]), 4),
    }


async def over_budget(tenant_id: str, budget_usd: float) -> bool:
    """Compara o gasto do mês corrente com o teto do tenant."""
    async with pool().acquire() as conn:
        total = await conn.fetchval(
            """
            SELECT COALESCE(sum(cost_usd), 0)
            FROM usage_events
            WHERE tenant_id = $1
              AND created_at >= date_trunc('month', now())
            """,
            tenant_id,
        )
    return float(total) >= budget_usd
