"""Artifact-engine + opportunity-miner endpoints (Phase 13).

* ``POST /api/v1/artifacts/assignments`` — turn skill gaps into evidence-producing
  project assignments. If no skills are supplied, uses the seeded profile skills.
* ``POST /api/v1/opportunities/mine`` — rank candidate repositories + scoped
  contribution types by fit with the user's skills and maintainability signals.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger("careerforge_api.artifact_router")

router = APIRouter(tags=["artifacts"])


class _SkillIn(BaseModel):
    name: str
    confidence: float = 0.0


class AssignmentsRequest(BaseModel):
    """Body for ``POST /artifacts/assignments`` (skills optional -> use seed)."""

    skills: list[_SkillIn] | None = None
    target_confidence: float = 0.8
    min_gap: float = 0.15
    limit: int = 5


class _RepoIn(BaseModel):
    full_name: str
    language: str | None = None
    stars: int = 0
    open_issues: int = 0
    has_tests: bool = False
    has_contributing_guide: bool = False
    archived: bool = False
    recent_activity: bool = True


class MineRequest(BaseModel):
    """Body for ``POST /opportunities/mine``."""

    repos: list[_RepoIn]
    user_skills: list[str] = Field(default_factory=list)
    limit: int = 10


def _error(status: int, code: str, message: str, detail: Any = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "detail": detail}},
    )


def _seed_skills() -> list[dict[str, Any]]:
    try:
        from careerforge_api import seed_data

        return [
            {"name": s.get("name"), "confidence": s.get("confidence", 0.0)}
            for s in seed_data.list_skills()
        ]
    except Exception:
        return []


@router.post("/artifacts/assignments")
async def make_assignments(request: AssignmentsRequest) -> Any:
    """Build evidence-producing assignments from skill gaps."""
    try:
        from artifact_engine import assignments_for_skills
    except Exception as exc:  # pragma: no cover
        return _error(503, "ARTIFACT_UNAVAILABLE", "Artifact engine unavailable.", str(exc))

    skills = (
        [s.model_dump() for s in request.skills] if request.skills is not None else _seed_skills()
    )
    assignments = assignments_for_skills(
        skills,
        target_confidence=request.target_confidence,
        min_gap=request.min_gap,
        limit=request.limit,
    )
    return {
        "assignment_count": len(assignments),
        "assignments": [a.model_dump(mode="json") for a in assignments],
        "used_seed_skills": request.skills is None,
    }


@router.post("/opportunities/mine")
async def mine(request: MineRequest) -> Any:
    """Rank candidate repositories as contribution opportunities."""
    try:
        from artifact_engine import mine_opportunities
    except Exception as exc:  # pragma: no cover
        return _error(503, "MINER_UNAVAILABLE", "Opportunity miner unavailable.", str(exc))

    skills = request.user_skills or [s["name"] for s in _seed_skills() if s.get("name")]
    report = mine_opportunities(
        [r.model_dump() for r in request.repos],
        user_skills=skills,
        limit=request.limit,
    )
    return report.model_dump(mode="json")
