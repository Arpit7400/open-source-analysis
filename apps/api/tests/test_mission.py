"""Repository-analysis (flagship flow) endpoint tests.

Covers ``POST /api/v1/repositories/analyze``, ``GET /api/v1/missions/{id}``,
``POST /api/v1/approvals/{id}``, and ``GET /api/v1/pulse``. The mission is
advanced deterministically via ``run_mission_sync`` (no sleeping on the live
stream), then the snapshot is inspected. The load-bearing safety rule verified
here: approvals NEVER perform a GitHub write.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from careerforge_api.main import app, run_mission_sync

client = TestClient(app)

_REPO = "https://github.com/owner/name"

_MISSION_STATUSES = {
    "QUEUED",
    "PLANNING",
    "RUNNING",
    "AWAITING_APPROVAL",
    "COMPLETED",
    "FAILED",
    "CANCELLED",
}
_AGENT_GROUPS = {
    "STATIC",
    "RUNTIME",
    "INTAKE",
    "DUPLICATE",
    "FIX",
    "VERIFY",
    "CONTROL",
    "AGGREGATE",
}
_VERDICTS = {"ACCEPTED", "REJECTED", "NO_SUBMISSION", "PENDING"}


def test_analyze_returns_mission_id_and_queued() -> None:
    resp = client.post("/api/v1/repositories/analyze", json={"repo_url": _REPO})
    assert resp.status_code in (200, 202)
    body = resp.json()
    assert "mission_id" in body and isinstance(body["mission_id"], str) and body["mission_id"]
    assert body["status"] == "QUEUED"


def test_analyze_requires_repo_url() -> None:
    resp = client.post("/api/v1/repositories/analyze", json={})
    assert resp.status_code == 400
    assert "error" in resp.json()


def test_mission_snapshot_after_run_has_agents_and_findings() -> None:
    # Advance a whole mission deterministically (no live-stream waiting).
    mission_id = run_mission_sync(_REPO)

    resp = client.get(f"/api/v1/missions/{mission_id}")
    assert resp.status_code == 200
    mission = resp.json()

    assert mission["mission_id"] == mission_id
    assert mission["repo_url"] == _REPO
    assert mission["status"] in _MISSION_STATUSES

    # The multi-agent graph is populated.
    assert len(mission["agents"]) >= 1
    for agent in mission["agents"]:
        assert set(agent) >= {"id", "label", "group", "state", "progress"}
        assert agent["group"] in _AGENT_GROUPS
        assert 0.0 <= agent["progress"] <= 1.0

    # Edges reference the graph.
    assert isinstance(mission["edges"], list)

    # Findings are produced with evidence and reproduction metadata.
    assert len(mission["findings"]) >= 1
    for finding in mission["findings"]:
        assert set(finding) >= {
            "finding_id",
            "category",
            "severity",
            "confidence",
            "summary",
            "evidence",
            "agent_id",
        }
        assert isinstance(finding["evidence"], list)

    # Candidates exist, and at least one was REJECTED — proving that the
    # independent-verification step actually rejects bad fixes.
    assert len(mission["candidates"]) >= 1
    verdicts = {c["verdict"] for c in mission["candidates"]}
    assert verdicts <= _VERDICTS
    assert "REJECTED" in verdicts, "expected at least one REJECTED candidate"


def test_mission_reaches_approval_gate_with_non_submittable_draft() -> None:
    mission_id = run_mission_sync(_REPO)
    mission = client.get(f"/api/v1/missions/{mission_id}").json()

    approval = mission["approval"]
    assert approval is not None
    assert approval["required"] is True
    draft = approval["draft"]
    assert draft is not None
    assert draft["kind"] in {"ISSUE", "PR"}
    # Human-in-the-loop safety gate: the draft is NOT auto-submittable.
    assert draft["submittable"] is False
    assert draft.get("reason_not_submittable")


def test_get_unknown_mission_404() -> None:
    resp = client.get("/api/v1/missions/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
    assert "error" in resp.json()


def test_approval_never_performs_github_write() -> None:
    mission_id = run_mission_sync(_REPO)

    for decision in ("APPROVE", "REJECT"):
        # Re-run a fresh mission per decision so state is clean.
        mid = run_mission_sync(_REPO)
        resp = client.post(f"/api/v1/approvals/{mid}", json={"decision": decision, "note": "n"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        # THE safety invariant: no GitHub write, ever.
        assert body["github_write"] is False
        # An approval only ever saves the draft locally.
        assert body["action_taken"] in {"DRAFT_SAVED_LOCALLY", "DRAFT_DISCARDED"}

    # Sanity: approving explicitly reports the local-save action.
    resp = client.post(f"/api/v1/approvals/{mission_id}", json={"decision": "APPROVE"})
    assert resp.json()["action_taken"] == "DRAFT_SAVED_LOCALLY"
    assert resp.json()["github_write"] is False


def test_approval_rejects_invalid_decision() -> None:
    mission_id = run_mission_sync(_REPO)
    resp = client.post(f"/api/v1/approvals/{mission_id}", json={"decision": "MAYBE"})
    assert resp.status_code == 400
    assert "error" in resp.json()


def test_approval_unknown_mission_404() -> None:
    resp = client.post(
        "/api/v1/approvals/00000000-0000-0000-0000-000000000000",
        json={"decision": "APPROVE"},
    )
    assert resp.status_code == 404


def test_pulse_shape() -> None:
    resp = client.get("/api/v1/pulse")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert isinstance(items, list)
    assert len(items) >= 1
    for item in items:
        assert set(item) >= {
            "id",
            "title",
            "source",
            "technology",
            "published_at",
            "momentum",
            "personal_relevance",
            "actionability",
            "why_it_matters",
            "skill_gap",
            "suggested_action",
            "canonical_url",
        }
        assert item["source"] in {"arXiv", "GitHub", "Blog", "Advisory"}
        for metric in ("momentum", "personal_relevance", "actionability"):
            assert 0.0 <= item[metric] <= 1.0
