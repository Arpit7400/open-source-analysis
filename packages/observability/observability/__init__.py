"""Observability (Phase 14): spans + metrics with graceful degradation.

Zero-dependency built-in tracer by default; upgrades to OpenTelemetry when
``opentelemetry-*`` is installed and ``CAREERFORGE_OTEL_ENABLED`` is set.
"""

from __future__ import annotations

from observability.tracing import (
    SpanRecord,
    Telemetry,
    get_telemetry,
    redact_attrs,
)

__all__ = [
    "SpanRecord",
    "Telemetry",
    "get_telemetry",
    "redact_attrs",
]
