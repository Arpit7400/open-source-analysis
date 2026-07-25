"""Observability tests (built-in backend; no OTel, no network)."""

from __future__ import annotations

import pytest

from observability import Telemetry, redact_attrs
from observability.tracing import get_telemetry


def test_span_records_duration_and_attributes() -> None:
    tel = Telemetry()
    with tel.span("model.call", model="qwen2.5:7b") as attrs:
        attrs["tokens"] = 128
    snap = tel.snapshot()
    assert snap["backend"] == "builtin"
    span = snap["recent_spans"][-1]
    assert span["name"] == "model.call"
    assert span["attributes"]["model"] == "qwen2.5:7b"
    assert span["attributes"]["tokens"] == 128
    assert span["status"] == "OK"
    assert span["duration_ms"] >= 0.0


def test_span_records_errors_and_reraises() -> None:
    tel = Telemetry()
    with pytest.raises(ValueError), tel.span("risky") as attrs:
        attrs["stage"] = "boom"
        raise ValueError("nope")
    span = tel.snapshot()["recent_spans"][-1]
    assert span["status"] == "ERROR"
    assert "ValueError" in (span["error"] or "")


def test_secrets_are_redacted_in_spans() -> None:
    tel = Telemetry()
    with tel.span("github.call", authorization="Bearer ghp_secret", repo="a/b"):
        pass
    span = tel.snapshot()["recent_spans"][-1]
    assert span["attributes"]["authorization"] == "***REDACTED***"
    assert span["attributes"]["repo"] == "a/b"


def test_redact_attrs_masks_known_keys() -> None:
    out = redact_attrs({"api_key": "x", "token": "y", "name": "ok"})
    assert out["api_key"] == "***REDACTED***"
    assert out["token"] == "***REDACTED***"
    assert out["name"] == "ok"


def test_counters_and_histograms() -> None:
    tel = Telemetry()
    tel.incr("requests")
    tel.incr("requests", 2)
    tel.observe("latency", 10.0)
    tel.observe("latency", 20.0)
    snap = tel.snapshot()
    assert snap["counters"]["requests"] == 3
    assert snap["histograms"]["latency"]["count"] == 2
    assert snap["histograms"]["latency"]["avg_ms"] == 15.0


def test_span_updates_derived_metrics() -> None:
    tel = Telemetry()
    with tel.span("retrieval.query"):
        pass
    snap = tel.snapshot()
    assert snap["counters"]["span.retrieval.query.count"] == 1
    assert "span.retrieval.query.ms" in snap["histograms"]


def test_singleton() -> None:
    assert get_telemetry() is get_telemetry()
