"""Verification-swarm endpoint (Phase 10).

``POST /api/v1/verifications/run`` takes a finding, generates candidate patches
(Phase 9) and runs the independent verification swarm (Phase 10) over them,
returning each candidate with its verdict (ACCEPTED | REJECTED | NO_SUBMISSION),
per-check results, and a summary. Authors never verify their own output.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger("careerforge_api.verify_router")

router = APIRouter(prefix="/verifications", tags=["verifications"])


class RunRequest(BaseModel):
    """Body for ``POST /verifications/run``."""

    repo_path: str
    finding_id: str | None = None
    summary: str
    category: str = "CODE_QUALITY"
    path: str | None = None
    line: int | None = None
    snippet: str = ""
    use_llm: bool = False


def _error(status: int, code: str, message: str, detail: Any = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "detail": detail}},
    )


@router.post("/run")
async def run_verification(request: RunRequest) -> Any:
    """Generate candidates for a finding, then verify them independently."""
    try:
        from patch_gen import LocalLLM, PatchGenerator
        from verify_swarm import verify_candidates
    except Exception as exc:  # pragma: no cover - packages optional at boot
        return _error(503, "VERIFY_UNAVAILABLE", "Verification subsystem unavailable.", str(exc))

    llm = LocalLLM() if request.use_llm else None
    gen = PatchGenerator(llm)
    try:
        cset = await gen.generate_for_finding(
            request.repo_path,
            finding_id=request.finding_id,
            summary=request.summary,
            category=request.category,
            path=request.path,
            line=request.line,
            snippet=request.snippet,
        )
        verified = verify_candidates(request.repo_path, cset.candidates)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("verification run failed")
        return _error(500, "VERIFY_FAILED", "Verification run failed.", str(exc))

    accepted = [c for c in verified if c.verdict == "ACCEPTED"]
    rejected = [c for c in verified if c.verdict == "REJECTED"]
    return {
        "finding_id": request.finding_id,
        "problem_summary": cset.problem_summary,
        "generated_by": cset.generated_by,
        "candidates": [c.model_dump(mode="json") for c in verified],
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "gate_summary": (
            f"{len(accepted)} accepted, {len(rejected)} rejected by independent "
            f"verifiers out of {len(verified)} candidate(s)."
        ),
    }
