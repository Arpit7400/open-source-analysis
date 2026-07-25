"""Tracing + metrics with graceful degradation (Phase 14).

Instruments the things the handbook §10 calls for — HTTP requests, model calls,
retrieval, sandbox commands, GitHub calls, agent steps — as spans with typed
attributes, plus simple counters/histograms.

Two backends, chosen automatically:

* **OpenTelemetry** when ``opentelemetry-api``/``-sdk`` are installed and
  ``CAREERFORGE_OTEL_ENABLED`` is truthy — real spans exported to your collector.
* **Built-in** otherwise — a dependency-free in-process recorder that keeps the
  last N spans + metric aggregates in memory (exposed via a ``/system/metrics``
  endpoint). This keeps the app fully runnable with no observability stack.

Secrets never enter attributes: :func:`redact_attrs` scrubs known-sensitive
keys before a span records them.
"""

from __future__ import annotations

import contextlib
import os
import time
from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager
from threading import Lock
from typing import Any

_SENSITIVE_KEYS = {
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "auth",
    "secret",
    "password",
    "passwd",
    "api_key",
    "apikey",
    "cookie",
    "credential",
    "credentials",
}


def _key_is_sensitive(key: str) -> bool:
    """True if ``key`` names a secret.

    Matches on word boundaries (split on non-alphanumerics) so ``token`` and
    ``authorization`` are caught but ``tokens`` (a benign count) is not.
    """
    lowered = key.lower()
    if lowered in _SENSITIVE_KEYS:
        return True
    parts = {p for p in _split_words(lowered) if p}
    return bool(parts & _SENSITIVE_KEYS)


def _split_words(text: str) -> list[str]:
    word: list[str] = []
    out: list[str] = []
    for ch in text:
        if ch.isalnum():
            word.append(ch)
        elif word:
            out.append("".join(word))
            word = []
    if word:
        out.append("".join(word))
    return out


def redact_attrs(attrs: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``attrs`` with sensitive values masked."""
    return {k: ("***REDACTED***" if _key_is_sensitive(k) else v) for k, v in attrs.items()}


class SpanRecord:
    """A finished span (built-in backend)."""

    __slots__ = ("attributes", "duration_ms", "error", "name", "status")

    def __init__(
        self,
        name: str,
        attributes: dict[str, Any],
        duration_ms: float,
        status: str,
        error: str | None,
    ) -> None:
        self.name = name
        self.attributes = attributes
        self.duration_ms = duration_ms
        self.status = status
        self.error = error

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "attributes": self.attributes,
            "duration_ms": round(self.duration_ms, 3),
            "status": self.status,
            "error": self.error,
        }


class Telemetry:
    """Process-wide telemetry: spans + counters + histograms.

    Thread-safe. Uses OpenTelemetry when available+enabled; always also keeps a
    small in-memory ring of recent spans and metric aggregates for the built-in
    ``/system/metrics`` view.
    """

    def __init__(self, max_spans: int = 500, elapsed: Any = None) -> None:
        self._lock = Lock()
        self._spans: deque[SpanRecord] = deque(maxlen=max_spans)
        self._counters: dict[str, int] = {}
        self._histograms: dict[str, list[float]] = {}
        # injectable clock (defaults to perf_counter) so tests are deterministic
        self._clock = elapsed or time.perf_counter
        self._otel = _try_otel_tracer()

    # -- metrics -------------------------------------------------------------
    def incr(self, name: str, by: int = 1) -> None:
        with self._lock:
            self._counters[name] = self._counters.get(name, 0) + by

    def observe(self, name: str, value: float) -> None:
        with self._lock:
            self._histograms.setdefault(name, []).append(value)

    # -- spans ---------------------------------------------------------------
    @contextmanager
    def span(self, name: str, **attributes: Any) -> Iterator[dict[str, Any]]:
        """Context manager recording a span. Yields a mutable attribute dict.

        Extra attributes set on the yielded dict during the block are recorded
        (after redaction). Exceptions mark the span an error and re-raise.
        """
        attrs: dict[str, Any] = dict(attributes)
        start = self._clock()
        otel_cm = self._otel.start_as_current_span(name) if self._otel else None
        otel_span = otel_cm.__enter__() if otel_cm else None
        status = "OK"
        error: str | None = None
        try:
            yield attrs
        except Exception as exc:
            status = "ERROR"
            error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            duration_ms = (self._clock() - start) * 1000.0
            safe = redact_attrs(attrs)
            if otel_span is not None:
                for k, v in safe.items():
                    with contextlib.suppress(Exception):
                        otel_span.set_attribute(k, v if isinstance(v, (str, int, float, bool)) else str(v))
                if error:
                    with contextlib.suppress(Exception):
                        otel_span.set_attribute("error", error)
            if otel_cm is not None:
                otel_cm.__exit__(None, None, None)
            with self._lock:
                self._spans.append(SpanRecord(name, safe, duration_ms, status, error))
                self._counters[f"span.{name}.count"] = self._counters.get(f"span.{name}.count", 0) + 1
                self._histograms.setdefault(f"span.{name}.ms", []).append(duration_ms)

    # -- export --------------------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        """Return recent spans + metric aggregates (for /system/metrics)."""
        with self._lock:
            spans = [s.as_dict() for s in self._spans]
            counters = dict(self._counters)
            hist = {
                k: {
                    "count": len(v),
                    "avg_ms": round(sum(v) / len(v), 3) if v else 0.0,
                    "max_ms": round(max(v), 3) if v else 0.0,
                }
                for k, v in self._histograms.items()
            }
        return {
            "backend": "opentelemetry" if self._otel else "builtin",
            "span_count": len(spans),
            "recent_spans": spans[-50:],
            "counters": counters,
            "histograms": hist,
        }

    @property
    def backend(self) -> str:
        return "opentelemetry" if self._otel else "builtin"


def _try_otel_tracer() -> Any | None:
    """Return an OpenTelemetry tracer if installed AND enabled, else None."""
    if os.environ.get("CAREERFORGE_OTEL_ENABLED", "").lower() not in {"1", "true", "yes"}:
        return None
    try:
        from opentelemetry import trace

        return trace.get_tracer("careerforge")
    except Exception:
        return None


# Process-wide default instance.
_TELEMETRY: Telemetry | None = None


def get_telemetry() -> Telemetry:
    """Return the process-wide :class:`Telemetry` singleton."""
    global _TELEMETRY
    if _TELEMETRY is None:
        _TELEMETRY = Telemetry()
    return _TELEMETRY
