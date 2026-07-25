"""Runtime-investigation endpoints (Phase 7).

* ``POST /api/v1/runtime/environment`` — detect a repo's Python environment
  (read-only; always safe).
* ``POST /api/v1/runtime/investigate`` — plan + (if armed) run sandboxed
  install/tests/lint/type steps and return runtime findings + reproduction
  status. Execution is gated behind the repository_execution flag.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from careerforge_api.config import get_settings

logger = logging.getLogger("careerforge_api.runtime_router")

router = APIRouter(prefix="/runtime", tags=["runtime"])


class RepoRequest(BaseModel):
    repo_path: str


def _error(status: int, code: str, message: str, detail: Any = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "detail": detail}},
    )


def _exec_flag() -> bool:
    try:
        return bool(get_settings().flags.repository_execution)
    except Exception:
        return False


@router.post("/environment")
async def environment(request: RepoRequest) -> Any:
    """Detect the repository's Python environment (read-only)."""
    try:
        from runtime_investigation import detect_environment
    except Exception as exc:  # pragma: no cover
        return _error(503, "RUNTIME_UNAVAILABLE", "Runtime subsystem unavailable.", str(exc))
    try:
        env = detect_environment(request.repo_path)
    except NotADirectoryError as exc:
        return _error(404, "REPO_PATH_NOT_FOUND", "Repository path not found.", str(exc))
    return env.model_dump(mode="json")


@router.post("/investigate")
async def investigate(request: RepoRequest) -> Any:
    """Plan + (if armed) run sandboxed runtime steps; return findings."""
    try:
        from runtime_investigation import RuntimeInvestigator
    except Exception as exc:  # pragma: no cover
        return _error(503, "RUNTIME_UNAVAILABLE", "Runtime subsystem unavailable.", str(exc))
    investigator = RuntimeInvestigator(execution_flag_enabled=_exec_flag())
    try:
        report = investigator.investigate(request.repo_path)
    except NotADirectoryError as exc:
        return _error(404, "REPO_PATH_NOT_FOUND", "Repository path not found.", str(exc))
    return report.model_dump(mode="json")
