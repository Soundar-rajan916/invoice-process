from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter, SpanExportResult

from app.core.config import settings
from app.core.logging import logger


class SafeConsoleSpanExporter(ConsoleSpanExporter):
    def export(self, spans: Any) -> SpanExportResult:
        try:
            return super().export(spans)
        except Exception:
            return SpanExportResult.SUCCESS

# ---------------------------------------------------------------------------
# 1. OpenTelemetry Tracing Setup (6.2)
# ---------------------------------------------------------------------------
_tracer_initialized = False


def init_tracing() -> None:
    global _tracer_initialized
    if _tracer_initialized:
        return

    resource = Resource.create({"service.name": "invoiceflow", "environment": settings.ENVIRONMENT})
    provider = TracerProvider(resource=resource)

    if getattr(settings, "OTEL_EXPORTER_OTLP_ENDPOINT", None):
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            otlp_exporter = OTLPSpanExporter(endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT)
            provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
            logger.info("OTLP Trace exporter configured", endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT)
        except Exception as e:
            logger.warning("Could not initialize OTLPSpanExporter, falling back to console", error=str(e))
            provider.add_span_processor(BatchSpanProcessor(SafeConsoleSpanExporter()))
    else:
        # In-memory / console exporter for dev/test
        provider.add_span_processor(BatchSpanProcessor(SafeConsoleSpanExporter()))

    trace.set_tracer_provider(provider)
    _tracer_initialized = True


def get_tracer(name: str = "invoiceflow") -> trace.Tracer:
    init_tracing()
    return trace.get_tracer(name)


@asynccontextmanager
async def trace_span(
    name: str,
    attributes: dict[str, Any] | None = None,
) -> AsyncGenerator[trace.Span, None]:
    tracer = get_tracer()
    with tracer.start_as_current_span(name) as span:
        if attributes:
            for k, v in attributes.items():
                if v is not None:
                    span.set_attribute(k, str(v) if not isinstance(v, (int, float, bool)) else v)
        yield span


def inject_trace_headers(headers: dict[str, str]) -> dict[str, str]:
    """Injects W3C traceparent into Celery or HTTP headers."""
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

    propagator = TraceContextTextMapPropagator()
    carrier: dict[str, str] = {}
    propagator.inject(carrier)
    headers.update(carrier)
    return headers


def extract_trace_context(headers: dict[str, str]) -> Any:
    """Extracts W3C traceparent from headers for distributed span linking."""
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

    propagator = TraceContextTextMapPropagator()
    return propagator.extract(headers)


# ---------------------------------------------------------------------------
# 2. In-Memory Prometheus Metrics Registry (6.2)
# ---------------------------------------------------------------------------
class MetricsRegistry:
    def __init__(self) -> None:
        self.llm_429_count: int = 0
        self.llm_tokens_total: dict[str, int] = {}
        self.llm_cost_total: float = 0.0
        self.llm_durations: list[float] = []
        self.task_durations: dict[str, list[float]] = {}
        self.push_attempts: dict[str, int] = {"success": 0, "client_error": 0, "server_error": 0}
        self.reviewer_edits: int = 0
        self.watchdog_requeues: int = 0

        # WhatsApp metrics (Section 5)
        self.whatsapp_session_state: int = 0  # 1=connected, 0=disconnected/needs_qr/unknown
        self.whatsapp_inbound_total: dict[str, int] = {
            "ingested": 0,
            "ignored": 0,
            "failed": 0,
            "skipped": 0,
        }
        self.whatsapp_outbound_total: dict[str, int] = {
            "sent": 0,
            "failed": 0,
            "skipped": 0,
        }
        self.whatsapp_signature_failures_total: int = 0

    def record_429(self) -> None:
        self.llm_429_count += 1

    def record_llm_usage(self, model: str, prompt_tokens: int, completion_tokens: int, latency_seconds: float) -> None:
        key_p = f"{model}|prompt"
        key_c = f"{model}|completion"
        self.llm_tokens_total[key_p] = self.llm_tokens_total.get(key_p, 0) + prompt_tokens
        self.llm_tokens_total[key_c] = self.llm_tokens_total.get(key_c, 0) + completion_tokens
        cost = (prompt_tokens * 0.00000005) + (completion_tokens * 0.00000010)
        self.llm_cost_total += cost
        self.llm_durations.append(latency_seconds)
        if len(self.llm_durations) > 1000:
            self.llm_durations = self.llm_durations[-500:]

    def record_push_result(self, result_type: str) -> None:
        self.push_attempts[result_type] = self.push_attempts.get(result_type, 0) + 1

    def record_reviewer_edit(self) -> None:
        self.reviewer_edits += 1

    def record_watchdog_requeue(self) -> None:
        self.watchdog_requeues += 1

    def set_whatsapp_session_state(self, state: str) -> None:
        self.whatsapp_session_state = 1 if state.lower() == "connected" else 0

    def record_whatsapp_inbound(self, result: str) -> None:
        self.whatsapp_inbound_total[result] = self.whatsapp_inbound_total.get(result, 0) + 1

    def record_whatsapp_outbound(self, result: str) -> None:
        self.whatsapp_outbound_total[result] = self.whatsapp_outbound_total.get(result, 0) + 1

    def record_whatsapp_signature_failure(self) -> None:
        self.whatsapp_signature_failures_total += 1


metrics_registry = MetricsRegistry()
