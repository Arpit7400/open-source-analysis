"""Static-analysis endpoints (Phase 5).

``POST /api/v1/analysis/static`` runs the real static-analysis swarm over a
local repository path and returns typed findings with exact ``path:line``
evidence.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from careerforge_api import analysis_service

logger = logging.getLogger("careerforge_api.analysis_router")

router = APIRouter(prefix="/analysis", tags=["analysis"])


class StaticAnalysisRequest(BaseModel):
    """Body for ``POST /analysis/static``."""

    repo_path: str
    repo_id: str | None = None
    include_tools: bool = True


def _error(status: int, code: str, message: str, detail: Any = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "detail": detail}},
    )


@router.post("/static")
async def run_static_analysis(request: StaticAnalysisRequest) -> Any:
    """Run the AST + ruff/mypy agents over ``repo_path`` and return findings."""
    try:
        return analysis_service.analyze(
            request.repo_path, request.repo_id, include_tools=request.include_tools
        )
    except NotADirectoryError as exc:
        return _error(404, "REPO_PATH_NOT_FOUND", "Repository path not found.", str(exc))
    except RuntimeError as exc:
        return _error(
            503, "ANALYSIS_UNAVAILABLE", "Static analysis subsystem unavailable.", str(exc)
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("static analysis failed for %s", request.repo_path)
        return _error(500, "ANALYSIS_FAILED", "Static analysis failed.", str(exc))
