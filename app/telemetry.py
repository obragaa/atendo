"""OpenTelemetry opcional: spans reais quando habilitado, no-op quando não.

Com OTEL_ENABLED=false (o padrão), `span()` vira um context manager de custo
zero — ninguém precisa subir Jaeger para rodar os testes ou desenvolver.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from app.config import get_settings

_tracer: Any = None


def setup_telemetry() -> None:
    """Configura o TracerProvider se OTEL_ENABLED=true.

    Os imports ficam aqui dentro para a suíte de testes não pagar o custo de
    carregar o SDK do OpenTelemetry quando a telemetria está desligada.
    """
    global _tracer
    settings = get_settings()
    if not settings.otel_enabled:
        _tracer = None
        return

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(
        resource=Resource.create({"service.name": settings.otel_service_name})
    )
    exporter = OTLPSpanExporter(
        endpoint=f"{settings.otel_exporter_otlp_endpoint.rstrip('/')}/v1/traces"
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer("atendo")


@contextmanager
def span(name: str, attributes: dict[str, Any] | None = None) -> Iterator[Any]:
    """Abre um span com atributos — ou não faz nada, se telemetria desligada."""
    if _tracer is None:
        yield None
        return
    with _tracer.start_as_current_span(name) as s:
        for chave, valor in (attributes or {}).items():
            s.set_attribute(chave, valor)
        yield s
