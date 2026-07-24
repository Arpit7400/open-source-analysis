"""Profile Brain endpoint tests.

Covers ``GET /api/v1/profile``, ``GET /api/v1/skills``, the per-skill evidence
endpoint, and ``POST /api/v1/profile/ingest-resume``. The load-bearing product
rule verified here: resume ingestion returns *claims* only, always at
``SELF_DECLARED`` — it never fabricates a higher verification level.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from careerforge_api.main import app

client = TestClient(app)

_VERIFICATION_LEVELS = {
    "SELF_DECLARED",
    "AI_INFERRED",
    "TOOL_VERIFIED",
    "HUMAN_REVIEWED",
    "EXTERNALLY_VALIDATED",
}

_SKILL_FIELDS = {
    "id",
    "name",
    "category",
    "confidence",
    "evidence_strength",
    "recency",
    "complexity",
    "independence",
    "verification_level",
    "evidence_ids",
    "last_updated",
    "last_change_reason",
    "related_skill_ids",
}


def test_profile_shape() -> None:
    resp = client.get("/api/v1/profile")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) >= {
        "user_id",
        "name",
        "headline",
        "goals",
        "verified_skill_count",
        "merged_prs",
        "evidence_count",
    }
    assert isinstance(body["goals"], list)
    assert body["verified_skill_count"] >= 0
    assert body["merged_prs"] >= 0
    assert body["evidence_count"] >= 0


def test_skills_list_shape() -> None:
    resp = client.get("/api/v1/skills")
    assert resp.status_code == 200
    body = resp.json()
    assert "skills" in body
    skills = body["skills"]
    assert isinstance(skills, list)
    assert len(skills) >= 1

    for skill in skills:
        # Every skill carries the full contract field set.
        assert set(skill) >= _SKILL_FIELDS, f"missing fields: {_SKILL_FIELDS - set(skill)}"
        assert skill["verification_level"] in _VERIFICATION_LEVELS
        # Scoring fields are normalized to [0, 1].
        for metric in (
            "confidence",
            "evidence_strength",
            "recency",
            "complexity",
            "independence",
        ):
            assert 0.0 <= skill[metric] <= 1.0
        assert isinstance(skill["evidence_ids"], list)
        assert isinstance(skill["related_skill_ids"], list)


def test_skill_evidence_shape_and_404() -> None:
    skills = client.get("/api/v1/skills").json()["skills"]
    skill_id = skills[0]["id"]

    resp = client.get(f"/api/v1/skills/{skill_id}/evidence")
    assert resp.status_code == 200
    body = resp.json()
    assert body["skill_id"] == skill_id
    assert isinstance(body["evidence"], list)
    for ev in body["evidence"]:
        assert set(ev) >= {
            "id",
            "type",
            "summary",
            "source_url",
            "verification_level",
            "created_at",
        }
        assert ev["type"] in {"COMMIT", "TEST", "DOC", "PR", "PROJECT"}
        assert ev["verification_level"] in _VERIFICATION_LEVELS

    # Unknown skill id → 404 with the structured error envelope.
    missing = client.get("/api/v1/skills/00000000-0000-0000-0000-000000000000/evidence")
    assert missing.status_code == 404
    assert "error" in missing.json()


def test_ingest_resume_json_returns_self_declared_claims() -> None:
    resume = "Senior engineer skilled in Python, FastAPI, and RAG systems."
    resp = client.post("/api/v1/profile/ingest-resume", json={"text": resume})
    assert resp.status_code == 200

    body = resp.json()
    assert "claims" in body
    claims = body["claims"]
    assert isinstance(claims, list)
    assert len(claims) >= 1, "expected at least one extracted claim"

    for claim in claims:
        assert set(claim) >= {"skill", "evidence_level", "raw_span"}
        # THE rule: resume claims are never auto-verified.
        assert claim["evidence_level"] == "SELF_DECLARED"
        assert isinstance(claim["skill"], str) and claim["skill"]
        assert isinstance(claim["raw_span"], str)


def test_ingest_resume_never_fabricates_verification() -> None:
    # Even a resume that *claims* deep verification must come back SELF_DECLARED.
    resume = "TOOL_VERIFIED expert. EXTERNALLY_VALIDATED. Python, Docker, PostgreSQL, Kubernetes."
    body = client.post("/api/v1/profile/ingest-resume", json={"text": resume}).json()
    levels = {c["evidence_level"] for c in body["claims"]}
    assert levels <= {"SELF_DECLARED"}, f"ingestion fabricated verification: {levels}"


def test_ingest_resume_multipart_file() -> None:
    content = b"Backend developer using Python and PostgreSQL."
    resp = client.post(
        "/api/v1/profile/ingest-resume",
        files={"file": ("resume.txt", content, "text/plain")},
    )
    assert resp.status_code == 200
    claims = resp.json()["claims"]
    assert all(c["evidence_level"] == "SELF_DECLARED" for c in claims)


def test_ingest_resume_empty_body_yields_no_claims() -> None:
    resp = client.post("/api/v1/profile/ingest-resume", json={})
    assert resp.status_code == 200
    assert resp.json()["claims"] == []
