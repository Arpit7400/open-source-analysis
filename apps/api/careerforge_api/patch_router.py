"""Candidate patch-generation endpoints (Phase 9).

* ``POST /api/v1/candidates/generate`` — generate candidate patches for a finding.
* ``GET  /api/v1/candidates/llm-status`` — report whether the local LLM is
  reachable (bootup/health visibility). Works whether or not the LLM is up.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger("careerforge_api.patch_router")

router = APIRouter(prefix="/candidates", tags=["candidates"])


class GenerateRequest(BaseModel):
    """Body for ``POST /candidates/generate``."""

    repo_path: str
    finding_id: str | None = None
    summary: str
    category: str = "CODE_QUALITY"
    path: str | None = None
    line: int | None = None
    snippet: str = ""
    use_llm: bool = True


def _error(status: int, code: str, message: str, detail: Any = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "detail": detail}},
    )


@router.get("/llm-status")
async def llm_status() -> Any:
    """Report local-LLM availability for patch generation (never raises)."""
    try:
        from patch_gen import probe

        return await probe()
    except Exception as exc:  # pragma: no cover
        return {"available": False, "mode": "template", "error": str(exc)}


@router.post("/generate")
async def generate_candidates(request: GenerateRequest) -> Any:
    """Generate candidate patches for a finding (template + optional LLM)."""
    try:
        from patch_gen import LocalLLM, PatchGenerator
    except Exception as exc:  # pragma: no cover - package optional at boot
        return _error(503, "PATCH_GEN_UNAVAILABLE", "Patch generation unavailable.", str(exc))

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
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("candidate generation failed")
        return _error(500, "PATCH_GEN_FAILED", "Candidate generation failed.", str(exc))
    return cset.model_dump(mode="json")
