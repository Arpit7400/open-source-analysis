"""Health / system endpoint tests.

Verify ``GET /api/v1/system/health`` returns the exact contract shape, reports
every backing service as ``mock`` in demo mode, and that both safety flags are
false. Also checks the resources endpoint and root banner.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from careerforge_api.main import app

client = TestClient(app)

# Enums / constants straight from docs/API_CONTRACT.md.
_VALID_PROFILES = {"CPU_LOW", "VRAM_8_12", "VRAM_16_24", "WORKSTATION"}
_MOCKABLE_SERVICES = {"database", "qdrant", "redis", "ollama", "temporal"}
# The RAG subsystem (Phases 2 & 4) is a real service: its health value is a
# provider label (e.g. "ollama+qdrant-local", "hash+qdrant-local", "down"),
# not one of the mock/up/down statuses the stub services report.
_ALL_SERVICES = {
    "api",
    "rag",
    "github",
    "static_analysis",
    "duplicates",
    "candidates",
    "verifications",
    *_MOCKABLE_SERVICES,
}


def test_health_returns_200_and_contract_shape() -> None:
    resp = client.get("/api/v1/system/health")
    assert resp.status_code == 200

    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"] == "1.0.0"

    # Services block: api is up; the rest are present with a valid status.
    services = body["services"]
    assert set(services) == _ALL_SERVICES
    assert services["api"] == "up"
    for name in _MOCKABLE_SERVICES:
        assert services[name] in {"up", "down", "mock"}
    # rag reports a non-empty provider label.
    assert isinstance(services["rag"], str) and services["rag"]
    # github reports a provider label: "authenticated" | "anonymous" | "down".
    assert services["github"] in {"authenticated", "anonymous", "down"}
    # static_analysis reports "ready" | "down".
    assert services["static_analysis"] in {"ready", "down"}
    # duplicates (Phase 8) reports "ready" | "down".
    assert services["duplicates"] in {"ready", "down"}
    # candidates (Phase 9) reports "ready" | "down".
    assert services["candidates"] in {"ready", "down"}
    # verifications (Phase 10) reports "ready" | "down".
    assert services["verifications"] in {"ready", "down"}

    # Hardware profile must be one of the four contract values.
    assert body["hardware_profile"] in _VALID_PROFILES

    # Flags block: exactly the two contract flags, both booleans.
    flags = body["flags"]
    assert set(flags) == {"github_writes", "repository_execution"}
    assert isinstance(flags["github_writes"], bool)
    assert isinstance(flags["repository_execution"], bool)


def test_health_reports_mock_services_and_false_flags_in_demo() -> None:
    body = client.get("/api/v1/system/health").json()

    # Demo mode: no real DB / vector store / cache / model / workflow engine.
    for name in _MOCKABLE_SERVICES:
        assert body["services"][name] == "mock", f"{name} should be 'mock' in demo mode"

    # Safety flags are OFF by default — no GitHub writes, no repo execution.
    assert body["flags"]["github_writes"] is False
    assert body["flags"]["repository_execution"] is False


def test_resources_shape() -> None:
    resp = client.get("/api/v1/system/resources")
    assert resp.status_code == 200

    body = resp.json()
    assert set(body) == {
        "cpu_percent",
        "ram_used_mb",
        "ram_total_mb",
        "active_agents",
        "max_agents",
    }
    assert isinstance(body["cpu_percent"], (int, float))
    assert body["cpu_percent"] >= 0
    assert body["ram_used_mb"] >= 0
    assert body["ram_total_mb"] >= 0
    assert body["active_agents"] >= 0
    assert body["max_agents"] >= 1


def test_root_banner() -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "CareerForge AI API"
    assert body["version"] == "1.0.0"
    assert body["api_base"] == "/api/v1"
    assert body["hardware_profile"] in _VALID_PROFILES


def test_unknown_route_returns_contract_error_shape() -> None:
    resp = client.get("/api/v1/does-not-exist")
    assert resp.status_code == 404
    body = resp.json()
    # Structured error envelope: { "error": { code, message, detail } }.
    assert "error" in body
    assert set(body["error"]) >= {"code", "message"}
    assert isinstance(body["error"]["code"], str)
    assert isinstance(body["error"]["message"], str)
