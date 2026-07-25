# observability — CareerForge AI Phase 14

Spans + metrics for the handbook §10 signals (HTTP, model, retrieval, sandbox,
GitHub, agent steps), with graceful degradation:

- **Built-in backend (default, zero deps):** an in-process recorder keeping the
  recent spans + counter/histogram aggregates in memory, exposed via
  `GET /api/v1/system/metrics`. Keeps the app fully runnable with no stack.
- **OpenTelemetry backend:** used automatically when `opentelemetry-api`/`-sdk`
  are installed **and** `CAREERFORGE_OTEL_ENABLED=1`. Real spans to your
  collector; the built-in ring still mirrors them for the local view.

Secrets never enter attributes — `redact_attrs` masks token/authorization/
secret/password/api_key/cookie keys before recording.

```python
from observability import get_telemetry
tel = get_telemetry()
with tel.span("model.call", model="qwen2.5:7b") as attrs:
    attrs["tokens"] = 512          # recorded (redacted if sensitive)
tel.incr("requests")
print(tel.snapshot()["backend"])   # "builtin" or "opentelemetry"
```
