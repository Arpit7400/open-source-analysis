"""Sandbox endpoints (Phase 6) — safety-first, execution gated.

* ``POST /api/v1/sandbox/preflight`` — run the static safety preflight over a
  local repo path. Always safe (read-only scan, no execution).
* ``POST /api/v1/sandbox/policy-check`` — validate a batch of commands against
  the allowlist policy. Never runs anything.
* ``GET  /api/v1/sandbox/status`` — report whether execution is currently
  permitted (flag + engine availability), for operator visibility.

Actual container execution is intentionally NOT exposed as a fire-and-forget
endpoint here: it is driven by the (later) runtime-investigation workflow and
remains gated behind the ``repository_execution`` flag, which is OFF by default.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from careerforge_api.config import get_settings

logger = logging.getLogger("careerforge_api.sandbox_router")

router = APIRouter(prefix="/sandbox", tags=["sandbox"])


class PreflightRequest(BaseModel):
    repo_path: str


class PolicyCheckRequest(BaseModel):
    commands: list[list[str]]


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


@router.post("/preflight")
async def preflight(request: PreflightRequest) -> Any:
    """Static safety preflight over a local repository (read-only)."""
    try:
        from sandbox import run_preflight
    except Exception as exc:  # pragma: no cover
        return _error(503, "SANDBOX_UNAVAILABLE", "Sandbox subsystem unavailable.", str(exc))
    try:
        result = run_preflight(request.repo_path, execution_flag_enabled=_exec_flag())
    except NotADirectoryError as exc:
        return _error(404, "REPO_PATH_NOT_FOUND", "Repository path not found.", str(exc))
    return result.model_dump(mode="json")


@router.post("/policy-check")
async def policy_check(request: PolicyCheckRequest) -> Any:
    """Validate commands against the sandbox allowlist policy (no execution)."""
    try:
        from sandbox import validate_all
    except Exception as exc:  # pragma: no cover
        return _error(503, "SANDBOX_UNAVAILABLE", "Sandbox subsystem unavailable.", str(exc))
    decisions = validate_all(request.commands)
    return {
        "decisions": [d.model_dump(mode="json") for d in decisions],
        "all_allowed": all(d.allowed for d in decisions),
    }


@router.get("/status")
async def status() -> Any:
    """Report whether repository execution is currently permitted."""
    try:
        from sandbox import container_engine
    except Exception:
        return {"execution_flag": _exec_flag(), "engine": None, "can_execute": False}
    engine = container_engine()
    flag = _exec_flag()
    return {
        "execution_flag": flag,
        "engine": engine,
        "can_execute": bool(flag and engine),
        "note": (
            "Execution disabled by default. Enable CAREERFORGE_FLAGS__REPOSITORY_EXECUTION "
            "and run a container engine to permit sandboxed runs."
        ),
    }
