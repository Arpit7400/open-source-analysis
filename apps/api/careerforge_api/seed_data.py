"""CareerForge AI — deterministic seed content for the Profile Brain.

This module supplies the demo-mode data behind the Profile Brain endpoints:

* ``GET /api/v1/profile``            → :func:`get_profile`
* ``GET /api/v1/skills``             → :func:`get_skills`
* ``GET /api/v1/skills/{id}/evidence`` → :func:`get_evidence_for_skill`
* ``GET /api/v1/pulse``              → :func:`get_pulse_items`

Everything here is **deterministic** — no system randomness, no clocks that
change the shape — so the demo is byte-stable across runs and platforms
(Windows / macOS / Linux).  Timestamps are fixed ISO-8601 UTC strings.

The single most important product rule enforced here:

    >>> UNSUPPORTED LLM CLAIMS NEVER RAISE A SKILL SCORE. <<<

An LLM parsing a resume can only produce ``SELF_DECLARED`` claims. Confidence,
evidence_strength and ``verification_level`` are only elevated by *tool-verified*
or externally-validated evidence (passing tests, merged PRs, CI runs, released
packages).  See :data:`_SKILLS` — every skill's ``last_change_reason`` cites the
concrete evidence that moved it, and no skill is ``TOOL_VERIFIED`` or above
without at least one ``TOOL_VERIFIED``/``EXTERNALLY_VALIDATED`` evidence record.

Functions return plain ``dict`` objects that match the Profile / Skill /
Evidence / PulseItem shapes in ``docs/API_CONTRACT.md`` exactly.  The canonical
``VerificationLevel`` enum values are imported from ``careerforge_api.schemas``
when available, with a byte-identical local fallback so this module is always
importable while sibling tracks are still being built.
"""

from __future__ import annotations

import copy
from typing import Any

# ---------------------------------------------------------------------------
# VerificationLevel enum (with byte-identical local fallback).
# ---------------------------------------------------------------------------
try:  # pragma: no cover - exercised only when the sibling module exists
    from careerforge_api.schemas import VerificationLevel

    def _v(member: Any) -> str:
        return str(getattr(member, "value", member))

except Exception:  # pragma: no cover - fallback when schemas not yet present

    def _v(member: Any) -> str:
        return str(member)

    class VerificationLevel:  # type: ignore
        SELF_DECLARED = "SELF_DECLARED"
        AI_INFERRED = "AI_INFERRED"
        TOOL_VERIFIED = "TOOL_VERIFIED"
        HUMAN_REVIEWED = "HUMAN_REVIEWED"
        EXTERNALLY_VALIDATED = "EXTERNALLY_VALIDATED"


# ---------------------------------------------------------------------------
# Fixed identifiers.  Deterministic, human-readable UUID-shaped strings so the
# demo is stable and evidence links resolve without a database.
# ---------------------------------------------------------------------------
USER_ID = "11111111-1111-4111-8111-111111111111"

# Deterministic timestamps (frozen).  We do NOT call datetime.now() so seed
# output never drifts between runs / machines.
_T = {
    "recent": "2026-07-22T14:30:00Z",
    "week": "2026-07-17T09:15:00Z",
    "month": "2026-06-28T11:00:00Z",
    "quarter": "2026-05-02T16:45:00Z",
    "old": "2026-02-11T08:20:00Z",
}


def _sid(n: int) -> str:
    """Deterministic skill UUID-shaped id (skill index -> stable id)."""
    return f"22222222-2222-4222-8222-{n:012d}"


def _eid(n: int) -> str:
    """Deterministic evidence UUID-shaped id."""
    return f"33333333-3333-4333-8333-{n:012d}"


def _pid(n: int) -> str:
    """Deterministic pulse-item UUID-shaped id."""
    return f"44444444-4444-4444-8444-{n:012d}"


# ---------------------------------------------------------------------------
# Evidence records.
#
# Each evidence record matches the GET /skills/{id}/evidence item shape:
#   { id, type, summary, source_url, verification_level, created_at }
#
# NOTE ON THE CORE RULE: only COMMIT / TEST / PR / PROJECT evidence that was
# actually verified by a tool (tests run, CI green, PR merged, package
# published) carries TOOL_VERIFIED or EXTERNALLY_VALIDATED. A DOC or a
# self-declared claim stays at SELF_DECLARED / AI_INFERRED and therefore can
# never, on its own, raise a skill's score.
# ---------------------------------------------------------------------------
_EVIDENCE: list[dict[str, Any]] = [
    {
        "id": _eid(1),
        "type": "TEST",
        "summary": "17 unit tests for the RAG chunker pass in CI (pytest, 100% of new lines covered).",
        "source_url": "https://github.com/ada-lovelace/rag-lab/actions/runs/8123456",
        "verification_level": _v(VerificationLevel.TOOL_VERIFIED),
        "created_at": _T["recent"],
    },
    {
        "id": _eid(2),
        "type": "PR",
        "summary": "Merged PR #482 to cpython-adjacent tooling: fix asyncio task-group cancellation leak.",
        "source_url": "https://github.com/python-tooling/asyncflow/pull/482",
        "verification_level": _v(VerificationLevel.EXTERNALLY_VALIDATED),
        "created_at": _T["week"],
    },
    {
        "id": _eid(3),
        "type": "COMMIT",
        "summary": "Commit a1b2c3d: migrate ORM layer to SQLAlchemy 2.0 typed mappings; mypy --strict clean.",
        "source_url": "https://github.com/ada-lovelace/ledger-svc/commit/a1b2c3d",
        "verification_level": _v(VerificationLevel.TOOL_VERIFIED),
        "created_at": _T["month"],
    },
    {
        "id": _eid(4),
        "type": "TEST",
        "summary": "Property-based tests (Hypothesis) for the retry/backoff decorator — 3k cases, all green.",
        "source_url": "https://github.com/ada-lovelace/resilient/actions/runs/8098765",
        "verification_level": _v(VerificationLevel.TOOL_VERIFIED),
        "created_at": _T["week"],
    },
    {
        "id": _eid(5),
        "type": "PROJECT",
        "summary": "Published `vecstore-lite` to PyPI (v0.4.1); 2.1k downloads/month.",
        "source_url": "https://pypi.org/project/vecstore-lite/",
        "verification_level": _v(VerificationLevel.EXTERNALLY_VALIDATED),
        "created_at": _T["quarter"],
    },
    {
        "id": _eid(6),
        "type": "COMMIT",
        "summary": "Dockerized the inference service; multi-stage build cuts image 1.9GB → 340MB.",
        "source_url": "https://github.com/ada-lovelace/infer-svc/commit/d4e5f6a",
        "verification_level": _v(VerificationLevel.TOOL_VERIFIED),
        "created_at": _T["month"],
    },
    {
        "id": _eid(7),
        "type": "DOC",
        "summary": "Wrote an internal design doc on evaluation harness for RAG (peer-reviewed).",
        "source_url": "https://github.com/ada-lovelace/rag-lab/blob/main/docs/eval.md",
        "verification_level": _v(VerificationLevel.HUMAN_REVIEWED),
        "created_at": _T["month"],
    },
    {
        "id": _eid(8),
        "type": "TEST",
        "summary": "FastAPI contract tests (schemathesis) run green against the OpenAPI spec in CI.",
        "source_url": "https://github.com/ada-lovelace/ledger-svc/actions/runs/8076543",
        "verification_level": _v(VerificationLevel.TOOL_VERIFIED),
        "created_at": _T["recent"],
    },
    {
        "id": _eid(9),
        "type": "PR",
        "summary": "Merged PR #77 adding ruff + mypy pre-commit gates across the monorepo.",
        "source_url": "https://github.com/ada-lovelace/monorepo/pull/77",
        "verification_level": _v(VerificationLevel.EXTERNALLY_VALIDATED),
        "created_at": _T["week"],
    },
    {
        "id": _eid(10),
        "type": "COMMIT",
        "summary": "Implemented a Postgres LISTEN/NOTIFY event bus; integration tests exercise it.",
        "source_url": "https://github.com/ada-lovelace/ledger-svc/commit/b7c8d9e",
        "verification_level": _v(VerificationLevel.TOOL_VERIFIED),
        "created_at": _T["quarter"],
    },
    {
        "id": _eid(11),
        "type": "PROJECT",
        "summary": "Kaggle notebook on gradient-checkpointing for long-context training (bronze medal).",
        "source_url": "https://kaggle.com/ada-lovelace/grad-checkpoint",
        "verification_level": _v(VerificationLevel.EXTERNALLY_VALIDATED),
        "created_at": _T["old"],
    },
    {
        "id": _eid(12),
        "type": "DOC",
        "summary": "Resume states 'expert in Rust' — no supporting artifacts found in linked repos.",
        "source_url": "resume://ada-lovelace/2026",
        # Deliberately SELF_DECLARED: an unverified resume claim. This must NOT
        # raise the Rust skill's score on its own (see the Rust skill below).
        "verification_level": _v(VerificationLevel.SELF_DECLARED),
        "created_at": _T["old"],
    },
    {
        "id": _eid(13),
        "type": "COMMIT",
        "summary": "Vectorized feature pipeline with NumPy; benchmark 8.4x speedup (asv committed).",
        "source_url": "https://github.com/ada-lovelace/feat-pipe/commit/c0ffee1",
        "verification_level": _v(VerificationLevel.TOOL_VERIFIED),
        "created_at": _T["month"],
    },
    {
        "id": _eid(14),
        "type": "TEST",
        "summary": "End-to-end pytest suite for the CLI (`cf-cli`) runs green on the Windows CI matrix too.",
        "source_url": "https://github.com/ada-lovelace/cf-cli/actions/runs/8065432",
        "verification_level": _v(VerificationLevel.TOOL_VERIFIED),
        "created_at": _T["recent"],
    },
]


# Index evidence by id for the per-skill evidence endpoint.
_EVIDENCE_BY_ID: dict[str, dict[str, Any]] = {e["id"]: e for e in _EVIDENCE}


# ---------------------------------------------------------------------------
# Skills.  ~12 skills spanning every VerificationLevel.
#
# Fields match the GET /skills item shape exactly:
#   id, name, category, confidence, evidence_strength, recency, complexity,
#   independence, verification_level, evidence_ids, last_updated,
#   last_change_reason, related_skill_ids
#
# INVARIANT enforced by _validate_skill_rule() at import time:
#   verification_level >= TOOL_VERIFIED  IFF  the skill has at least one
#   TOOL_VERIFIED / HUMAN_REVIEWED / EXTERNALLY_VALIDATED evidence record.
#   Skills backed only by SELF_DECLARED / AI_INFERRED evidence stay low —
#   unsupported claims never raise the score.
# ---------------------------------------------------------------------------
_SKILLS: list[dict[str, Any]] = [
    {
        "id": _sid(1),
        "name": "Python",
        "category": "language",
        "confidence": 0.94,
        "evidence_strength": 0.9,
        "recency": 0.98,
        "complexity": 0.8,
        "independence": 0.9,
        "verification_level": _v(VerificationLevel.TOOL_VERIFIED),
        "evidence_ids": [_eid(1), _eid(3), _eid(8), _eid(14)],
        "last_updated": _T["recent"],
        "last_change_reason": "Raised to TOOL_VERIFIED: 17 new unit tests passed in CI (run 8123456); "
        "cross-platform CLI suite green on Windows matrix.",
        "related_skill_ids": [_sid(2), _sid(4), _sid(7)],
    },
    {
        "id": _sid(2),
        "name": "AsyncIO",
        "category": "language",
        "confidence": 0.83,
        "evidence_strength": 0.85,
        "recency": 0.9,
        "complexity": 0.85,
        "independence": 0.8,
        "verification_level": _v(VerificationLevel.EXTERNALLY_VALIDATED),
        "evidence_ids": [_eid(2)],
        "last_updated": _T["week"],
        "last_change_reason": "Raised to EXTERNALLY_VALIDATED: merged PR #482 fixing an asyncio task-group "
        "cancellation leak in a third-party library.",
        "related_skill_ids": [_sid(1)],
    },
    {
        "id": _sid(3),
        "name": "RAG Systems",
        "category": "ml",
        "confidence": 0.8,
        "evidence_strength": 0.82,
        "recency": 0.97,
        "complexity": 0.9,
        "independence": 0.75,
        "verification_level": _v(VerificationLevel.TOOL_VERIFIED),
        "evidence_ids": [_eid(1), _eid(7)],
        "last_updated": _T["recent"],
        "last_change_reason": "Raised to TOOL_VERIFIED by 17 passing chunker tests (run 8123456); "
        "the peer-reviewed eval doc alone would only support HUMAN_REVIEWED.",
        "related_skill_ids": [_sid(1), _sid(9), _sid(10)],
    },
    {
        "id": _sid(4),
        "name": "FastAPI",
        "category": "framework",
        "confidence": 0.79,
        "evidence_strength": 0.78,
        "recency": 0.95,
        "complexity": 0.7,
        "independence": 0.8,
        "verification_level": _v(VerificationLevel.TOOL_VERIFIED),
        "evidence_ids": [_eid(8)],
        "last_updated": _T["recent"],
        "last_change_reason": "Raised to TOOL_VERIFIED: schemathesis contract tests run green against the "
        "OpenAPI spec in CI (run 8076543).",
        "related_skill_ids": [_sid(1), _sid(5)],
    },
    {
        "id": _sid(5),
        "name": "SQLAlchemy",
        "category": "database",
        "confidence": 0.76,
        "evidence_strength": 0.77,
        "recency": 0.88,
        "complexity": 0.75,
        "independence": 0.78,
        "verification_level": _v(VerificationLevel.TOOL_VERIFIED),
        "evidence_ids": [_eid(3), _eid(10)],
        "last_updated": _T["month"],
        "last_change_reason": "Raised to TOOL_VERIFIED: ORM 2.0 typed-mapping migration is mypy --strict "
        "clean (commit a1b2c3d) and integration tests exercise LISTEN/NOTIFY.",
        "related_skill_ids": [_sid(4), _sid(6)],
    },
    {
        "id": _sid(6),
        "name": "PostgreSQL",
        "category": "database",
        "confidence": 0.72,
        "evidence_strength": 0.7,
        "recency": 0.8,
        "complexity": 0.7,
        "independence": 0.75,
        "verification_level": _v(VerificationLevel.TOOL_VERIFIED),
        "evidence_ids": [_eid(10)],
        "last_updated": _T["quarter"],
        "last_change_reason": "Raised to TOOL_VERIFIED: LISTEN/NOTIFY event bus covered by passing "
        "integration tests (commit b7c8d9e).",
        "related_skill_ids": [_sid(5)],
    },
    {
        "id": _sid(7),
        "name": "Type Safety (mypy)",
        "category": "tooling",
        "confidence": 0.74,
        "evidence_strength": 0.76,
        "recency": 0.9,
        "complexity": 0.65,
        "independence": 0.82,
        "verification_level": _v(VerificationLevel.EXTERNALLY_VALIDATED),
        "evidence_ids": [_eid(9), _eid(3)],
        "last_updated": _T["week"],
        "last_change_reason": "Raised to EXTERNALLY_VALIDATED: merged PR #77 added ruff + mypy pre-commit "
        "gates across the monorepo; strict typing verified in commit a1b2c3d.",
        "related_skill_ids": [_sid(1), _sid(5)],
    },
    {
        "id": _sid(8),
        "name": "Docker",
        "category": "devops",
        "confidence": 0.68,
        "evidence_strength": 0.7,
        "recency": 0.82,
        "complexity": 0.6,
        "independence": 0.7,
        "verification_level": _v(VerificationLevel.TOOL_VERIFIED),
        "evidence_ids": [_eid(6)],
        "last_updated": _T["month"],
        "last_change_reason": "Raised to TOOL_VERIFIED: multi-stage build reproducibly cuts the image "
        "1.9GB → 340MB (commit d4e5f6a, verified in CI build).",
        "related_skill_ids": [_sid(4)],
    },
    {
        "id": _sid(9),
        "name": "NumPy",
        "category": "ml",
        "confidence": 0.71,
        "evidence_strength": 0.72,
        "recency": 0.85,
        "complexity": 0.7,
        "independence": 0.78,
        "verification_level": _v(VerificationLevel.TOOL_VERIFIED),
        "evidence_ids": [_eid(13)],
        "last_updated": _T["month"],
        "last_change_reason": "Raised to TOOL_VERIFIED: vectorized feature pipeline shows a committed "
        "asv benchmark of 8.4x speedup (commit c0ffee1).",
        "related_skill_ids": [_sid(1), _sid(3)],
    },
    {
        "id": _sid(10),
        "name": "Vector Databases",
        "category": "ml",
        "confidence": 0.7,
        "evidence_strength": 0.74,
        "recency": 0.8,
        "complexity": 0.8,
        "independence": 0.72,
        "verification_level": _v(VerificationLevel.EXTERNALLY_VALIDATED),
        "evidence_ids": [_eid(5)],
        "last_updated": _T["quarter"],
        "last_change_reason": "Raised to EXTERNALLY_VALIDATED: authored `vecstore-lite`, published to PyPI "
        "with sustained external downloads (2.1k/month).",
        "related_skill_ids": [_sid(3), _sid(9)],
    },
    {
        "id": _sid(11),
        "name": "Distributed Training",
        "category": "ml",
        "confidence": 0.55,
        "evidence_strength": 0.5,
        "recency": 0.45,
        "complexity": 0.9,
        "independence": 0.6,
        "verification_level": _v(VerificationLevel.AI_INFERRED),
        "evidence_ids": [_eid(11)],
        "last_updated": _T["old"],
        "last_change_reason": "Held at AI_INFERRED: a single older Kaggle notebook is suggestive but not a "
        "reproducible tool-verified artifact; no CI-backed evidence to raise the score.",
        "related_skill_ids": [_sid(9)],
    },
    {
        "id": _sid(12),
        "name": "Rust",
        "category": "language",
        "confidence": 0.28,
        "evidence_strength": 0.15,
        "recency": 0.3,
        "complexity": 0.5,
        "independence": 0.4,
        "verification_level": _v(VerificationLevel.SELF_DECLARED),
        "evidence_ids": [_eid(12)],
        "last_updated": _T["old"],
        "last_change_reason": "Kept at SELF_DECLARED: the resume claims 'expert in Rust' but no commits, "
        "tests, PRs or published crates back it. Unsupported LLM/resume claims never raise the score.",
        "related_skill_ids": [],
    },
]


# ---------------------------------------------------------------------------
# Import-time invariant check for the core rule.  Runs once on import; cheap.
# ---------------------------------------------------------------------------
_VERIFIED_LEVELS = {
    _v(VerificationLevel.TOOL_VERIFIED),
    _v(VerificationLevel.HUMAN_REVIEWED),
    _v(VerificationLevel.EXTERNALLY_VALIDATED),
}
# Levels that must NOT, by themselves, be enough to reach a "verified" skill
# level. (Kept for documentation / potential external assertions.)
_UNVERIFIED_LEVELS = {
    _v(VerificationLevel.SELF_DECLARED),
    _v(VerificationLevel.AI_INFERRED),
}


def _validate_skill_rule() -> None:
    """Assert the core scoring rule holds for the seed data.

    A skill may only sit at TOOL_VERIFIED or above if it is backed by at least
    one tool-verified / human-reviewed / externally-validated evidence record.
    This encodes: *unsupported (self-declared / AI-inferred) claims never raise
    a skill's verification level on their own.*
    """
    for skill in _SKILLS:
        levels = {
            _EVIDENCE_BY_ID[eid]["verification_level"]
            for eid in skill["evidence_ids"]
            if eid in _EVIDENCE_BY_ID
        }
        if skill["verification_level"] in _VERIFIED_LEVELS:
            assert levels & _VERIFIED_LEVELS, (
                f"Skill {skill['name']!r} is {skill['verification_level']} but has no "
                f"tool-verified/externally-validated evidence — this would let an "
                f"unsupported claim raise the score, violating the core rule."
            )


_validate_skill_rule()


# ---------------------------------------------------------------------------
# Industry Pulse items (~6). Shape matches GET /pulse item exactly.
# ---------------------------------------------------------------------------
_PULSE_ITEMS: list[dict[str, Any]] = [
    {
        "id": _pid(1),
        "title": "PEP 703 (no-GIL / free-threaded CPython) stabilizing in 3.14",
        "source": "Blog",
        "technology": "CPython",
        "published_at": _T["recent"],
        "momentum": 0.92,
        "personal_relevance": 0.78,
        "actionability": 0.6,
        "why_it_matters": "Free-threaded builds change how CPU-bound Python parallelism is written; your "
        "asyncio and NumPy pipeline work is directly adjacent.",
        "skill_gap": "Benchmarking under free-threaded builds and understanding thread-safety implications "
        "for shared state.",
        "suggested_action": "Run your `feat-pipe` benchmark under a 3.14 free-threaded build and record the delta.",
        "canonical_url": "https://peps.python.org/pep-0703/",
    },
    {
        "id": _pid(2),
        "title": "requests 2.32.x advisory: pin to patched release (GHSA-j8r2-6x86-q33q)",
        "source": "Advisory",
        "technology": "requests",
        "published_at": _T["week"],
        "momentum": 0.7,
        "personal_relevance": 0.85,
        "actionability": 0.95,
        "why_it_matters": "Several of your services declare `requests` unpinned; a patched release closes a "
        "known advisory.",
        "skill_gap": "Dependency pinning discipline and reproducible lockfiles across services.",
        "suggested_action": "Pin `requests>=2.32.0` in setup.py/pyproject and regenerate lockfiles.",
        "canonical_url": "https://github.com/advisories/GHSA-j8r2-6x86-q33q",
    },
    {
        "id": _pid(3),
        "title": "SQLAlchemy 2.1 preview: typed ORM ergonomics and async improvements",
        "source": "GitHub",
        "technology": "SQLAlchemy",
        "published_at": _T["month"],
        "momentum": 0.64,
        "personal_relevance": 0.8,
        "actionability": 0.55,
        "why_it_matters": "Builds on the 2.0 typed-mapping migration you already shipped in `ledger-svc`.",
        "skill_gap": "Async session patterns and the 2.1 typing refinements.",
        "suggested_action": "Prototype an async session in `ledger-svc` behind a feature flag.",
        "canonical_url": "https://github.com/sqlalchemy/sqlalchemy/releases",
    },
    {
        "id": _pid(4),
        "title": "Retrieval-augmented eval harnesses: RAGAS-style metrics gaining adoption",
        "source": "arXiv",
        "technology": "RAG",
        "published_at": _T["week"],
        "momentum": 0.88,
        "personal_relevance": 0.9,
        "actionability": 0.7,
        "why_it_matters": "Directly extends your peer-reviewed RAG eval doc toward reproducible, metric-driven "
        "evaluation.",
        "skill_gap": "Automating faithfulness/answer-relevance scoring in CI.",
        "suggested_action": "Wire a RAGAS-style faithfulness metric into `rag-lab`'s CI and gate on regressions.",
        "canonical_url": "https://arxiv.org/abs/2309.15217",
    },
    {
        "id": _pid(5),
        "title": "ruff now covers most flake8 plugins; teams retiring legacy linters",
        "source": "Blog",
        "technology": "ruff",
        "published_at": _T["month"],
        "momentum": 0.75,
        "personal_relevance": 0.72,
        "actionability": 0.8,
        "why_it_matters": "You already added ruff + mypy gates (PR #77); consolidating remaining linters reduces "
        "CI time and config sprawl.",
        "skill_gap": "Migrating residual flake8/isort config into ruff's unified ruleset.",
        "suggested_action": "Replace the leftover flake8 config in the monorepo with ruff's equivalent rules.",
        "canonical_url": "https://docs.astral.sh/ruff/",
    },
    {
        "id": _pid(6),
        "title": "datetime.utcnow() deprecation: aware timestamps required on 3.12+",
        "source": "Advisory",
        "technology": "Python stdlib",
        "published_at": _T["quarter"],
        "momentum": 0.6,
        "personal_relevance": 0.68,
        "actionability": 0.9,
        "why_it_matters": "Naive `utcnow()` calls emit DeprecationWarnings and will break on newer runtimes; "
        "several repos still use it.",
        "skill_gap": "Timezone-aware datetime handling and warning-as-error CI gates.",
        "suggested_action": "Replace `datetime.utcnow()` with `datetime.now(timezone.utc)` and run tests with "
        "`-W error::DeprecationWarning`.",
        "canonical_url": "https://docs.python.org/3/library/datetime.html#datetime.datetime.utcnow",
    },
]


# ---------------------------------------------------------------------------
# Public accessors. All return deep copies so callers can mutate freely without
# corrupting the module-level seed data (important when the same process serves
# many requests).
# ---------------------------------------------------------------------------
def get_profile() -> dict[str, Any]:
    """Return the Profile object (GET /api/v1/profile shape)."""
    verified_count = sum(1 for s in _SKILLS if s["verification_level"] in _VERIFIED_LEVELS)
    merged_prs = sum(1 for e in _EVIDENCE if e["type"] == "PR")
    return {
        "user_id": USER_ID,
        "name": "Ada Lovelace",
        "headline": "Backend & ML engineer",
        "goals": [
            "Merge 3 OSS PRs",
            "Master RAG systems",
            "Ship a free-threaded Python benchmark",
        ],
        "verified_skill_count": verified_count,
        "merged_prs": merged_prs,
        "evidence_count": len(_EVIDENCE),
    }


def get_skills() -> dict[str, Any]:
    """Return the ``{"skills": [...]}`` envelope for ``GET /api/v1/skills``.

    Each item matches the ``Skill`` schema. Use :func:`list_skills` when a bare
    list is more convenient.
    """
    return {"skills": list_skills()}


def list_skills() -> list[dict[str, Any]]:
    """Return the bare list of skill dicts (each matching the ``Skill`` schema)."""
    return copy.deepcopy(_SKILLS)


def get_skill(skill_id: str) -> dict[str, Any] | None:
    """Return a single skill by id, or ``None`` if unknown."""
    for skill in _SKILLS:
        if skill["id"] == skill_id:
            return copy.deepcopy(skill)
    return None


def get_evidence(skill_id: str | None = None) -> list[dict[str, Any]]:
    """Return evidence records.

    With ``skill_id`` (the API path parameter) return only that skill's
    evidence, each matching the ``Evidence`` schema. Unknown ids yield an empty
    list so the endpoint degrades gracefully. With no argument, return every
    evidence record.
    """
    if skill_id is None:
        return copy.deepcopy(_EVIDENCE)
    skill = next((s for s in _SKILLS if s["id"] == skill_id), None)
    if skill is None:
        return []
    return [
        copy.deepcopy(_EVIDENCE_BY_ID[eid])
        for eid in skill["evidence_ids"]
        if eid in _EVIDENCE_BY_ID
    ]


def get_evidence_for_skill(skill_id: str) -> dict[str, Any] | None:
    """Return the ``{"skill_id", "evidence"}`` envelope for a skill.

    Returns ``None`` if the skill id is unknown so the API layer can 404.
    """
    skill = next((s for s in _SKILLS if s["id"] == skill_id), None)
    if skill is None:
        return None
    return {"skill_id": skill_id, "evidence": get_evidence(skill_id)}


def get_pulse_items() -> dict[str, Any]:
    """Return the ``{"items": [...]}`` envelope for ``GET /api/v1/pulse``.

    Each item matches the ``PulseItem`` schema. Use :func:`get_pulse` for a bare
    list.
    """
    return {"items": get_pulse()}


def get_pulse() -> list[dict[str, Any]]:
    """Return the bare list of industry-pulse item dicts (each matching ``PulseItem``)."""
    return copy.deepcopy(_PULSE_ITEMS)


# A conservative keyword map for the demo resume parser. Every extracted claim
# is SELF_DECLARED: ingestion NEVER fabricates verification (the core rule).
_RESUME_KEYWORDS: dict[str, str] = {
    "python": "Python",
    "asyncio": "AsyncIO",
    "fastapi": "FastAPI",
    "flask": "Flask",
    "django": "Django",
    "sqlalchemy": "SQLAlchemy",
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "docker": "Docker",
    "kubernetes": "Kubernetes",
    "numpy": "NumPy",
    "pytorch": "PyTorch",
    "tensorflow": "TensorFlow",
    "rag": "RAG Systems",
    "vector database": "Vector Databases",
    "qdrant": "Vector Databases",
    "mypy": "Type Safety (mypy)",
    "rust": "Rust",
    "typescript": "TypeScript",
    "react": "React",
    "aws": "AWS",
    "redis": "Redis",
}


def extract_resume_claims(text: str) -> list[dict[str, Any]]:
    """Extract skill *claims* from resume text — ALWAYS as SELF_DECLARED.

    Matches the ``POST /api/v1/profile/ingest-resume`` claim shape:
    ``{ "skill", "evidence_level", "raw_span" }``. This is deliberately
    conservative: a resume/LLM claim is only ever a claim. It never raises a
    skill's verification level — only tool-verified evidence does that.
    """
    if not text:
        return []
    lowered = text.lower()
    seen: set[str] = set()
    claims: list[dict[str, Any]] = []
    for needle, canonical in _RESUME_KEYWORDS.items():
        idx = lowered.find(needle)
        if idx == -1 or canonical in seen:
            continue
        seen.add(canonical)
        start = max(0, idx - 24)
        end = min(len(text), idx + len(needle) + 24)
        claims.append(
            {
                "skill": canonical,
                "evidence_level": _v(VerificationLevel.SELF_DECLARED),
                "raw_span": text[start:end].strip(),
            }
        )
    return claims


__all__ = [
    "USER_ID",
    "get_profile",
    "get_skills",
    "list_skills",
    "get_skill",
    "get_evidence",
    "get_evidence_for_skill",
    "get_pulse_items",
    "get_pulse",
    "extract_resume_claims",
]
