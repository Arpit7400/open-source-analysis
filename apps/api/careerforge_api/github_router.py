"""GitHub HTTP surface — ``/api/v1/github/*`` (GITHUB_CONTRACT.md § *New API endpoints*).

An :class:`~fastapi.APIRouter` exposing the contract's read-only endpoints plus
the indexing trigger:

* ``GET  /github/repo?owner=&name=``                 → RepoMeta
* ``GET  /github/repo/issues?owner=&name=&state=``   → ``{ "issues":   IssueRef[] }``
* ``GET  /github/repo/pulls?owner=&name=&state=``     → ``{ "pulls":    PullRef[] }``
* ``GET  /github/repo/commits?owner=&name=``          → ``{ "commits":  CommitRef[] }``
* ``GET  /github/repo/releases?owner=&name=``         → ``{ "releases": ReleaseRef[] }``
* ``GET  /github/rate-limit``                         → RateLimit
* ``POST /github/index?owner=&name=``                 → index summary (README + Python
                                                        files → rag_core repository_docs /
                                                        repository_code)

The router is a thin transport shell over :mod:`careerforge_api.github_service`
(which owns the client lifecycle, redaction, and RAG wiring). It:

* validates ``owner``/``name``/``state`` query params,
* returns the exact JSON shapes from the contract (Pydantic models serialised
  with ``model_dump(mode="json")``), and
* maps failures to the shared error envelope
  ``{"error": {"code", "message", "detail"}}`` (API_CONTRACT.md § *Conventions*)
  with an appropriate HTTP status — ``404`` for a missing repository, ``403``
  for a GitHub rate-limit rejection (**never leaking the token**), ``503`` when
  the GitHub subsystem is unavailable.

It is mounted by ``main.py`` under the ``/api/v1`` prefix, so the concrete paths
become ``/api/v1/github/...``.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from careerforge_api import github_service
from careerforge_api.github_service import GitHubServiceError

logger = logging.getLogger("careerforge_api.github_router")

router = APIRouter(prefix="/github", tags=["github"])


# ---------------------------------------------------------------------------
# Error helpers (shared contract envelope)
# ---------------------------------------------------------------------------
def _error(status_code: int, code: str, message: str, detail: Any = None) -> JSONResponse:
    """Return the contract error envelope with the given HTTP status."""
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "detail": detail}},
    )


def _unavailable(exc: GitHubServiceError) -> JSONResponse:
    """503 envelope for a degraded/unavailable GitHub subsystem."""
    return _error(
        503,
        "GITHUB_UNAVAILABLE",
        "The GitHub subsystem is unavailable.",
        exc.reason,
    )


def _is_rate_limit_error(exc: Exception) -> bool:
    """Best-effort detection of ``github_client.RateLimitError``.

    Matched by class name so this module imports cleanly even when
    ``github_client`` is absent (the wrappers then only ever raise
    :class:`GitHubServiceError`).
    """
    return type(exc).__name__ == "RateLimitError"


def _is_not_found_error(exc: Exception) -> bool:
    """Detect a repository-not-found ``github_client.GitHubClientError``.

    The client raises a ``GitHubClientError`` whose (already-redacted) message
    embeds ``HTTP 404`` for a missing repo. We match on class name + the ``404``
    marker so no import of ``github_client`` is required here.
    """
    if type(exc).__name__ != "GitHubClientError":
        return False
    return "HTTP 404" in str(exc)


def _map_github_error(exc: Exception, *, repo: str | None = None) -> JSONResponse:
    """Translate any GitHub-layer exception into the contract error envelope.

    * :class:`GitHubServiceError`  → ``503 GITHUB_UNAVAILABLE``.
    * rate-limit rejection         → ``403 GITHUB_RATE_LIMITED`` (token-free).
    * repository not found         → ``404 REPO_NOT_FOUND``.
    * anything else                → ``502 GITHUB_ERROR`` (redacted message).

    ``str(exc)`` is safe to surface: every ``github_client`` error is redacted at
    the source, and :class:`GitHubServiceError` is only ever built from redacted
    strings. The token can never appear here.
    """
    if isinstance(exc, GitHubServiceError):
        return _unavailable(exc)
    if _is_rate_limit_error(exc):
        reset_at = getattr(exc, "reset_at", None)
        reset_iso = reset_at.isoformat() if reset_at is not None else None
        return _error(
            403,
            "GITHUB_RATE_LIMITED",
            "GitHub API rate limit exceeded.",
            {"reset_at": reset_iso, "remaining": getattr(exc, "remaining", None)},
        )
    if _is_not_found_error(exc):
        return _error(
            404,
            "REPO_NOT_FOUND",
            "Repository not found." if repo is None else f"Repository {repo} not found.",
            str(exc),
        )
    logger.warning("GitHub operation failed: %s", exc)
    return _error(502, "GITHUB_ERROR", "GitHub request failed.", str(exc))


def _dump_many(models: list[Any]) -> list[dict[str, Any]]:
    """Serialise a list of Pydantic v2 models to contract JSON dicts."""
    return [m.model_dump(mode="json") for m in models]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("/repo")
async def github_repo(
    owner: str = Query(..., min_length=1, description="Repository owner / org login."),
    name: str = Query(..., min_length=1, description="Repository name."),
) -> Any:
    """Return :class:`github_client.RepoMeta` for ``owner/name``."""
    try:
        repo = await github_service.get_repo(owner, name)
    except Exception as exc:
        return _map_github_error(exc, repo=f"{owner}/{name}")
    return repo.model_dump(mode="json")


@router.get("/repo/issues")
async def github_repo_issues(
    owner: str = Query(..., min_length=1),
    name: str = Query(..., min_length=1),
    state: str = Query("open", description="open | closed | all."),
) -> Any:
    """Return ``{ "issues": IssueRef[] }`` (pull requests excluded)."""
    try:
        issues = await github_service.list_issues(owner, name, state=state)
    except Exception as exc:
        return _map_github_error(exc, repo=f"{owner}/{name}")
    return {"issues": _dump_many(issues)}


@router.get("/repo/pulls")
async def github_repo_pulls(
    owner: str = Query(..., min_length=1),
    name: str = Query(..., min_length=1),
    state: str = Query("open", description="open | closed | all."),
) -> Any:
    """Return ``{ "pulls": PullRef[] }``."""
    try:
        pulls = await github_service.list_pulls(owner, name, state=state)
    except Exception as exc:
        return _map_github_error(exc, repo=f"{owner}/{name}")
    return {"pulls": _dump_many(pulls)}


@router.get("/repo/commits")
async def github_repo_commits(
    owner: str = Query(..., min_length=1),
    name: str = Query(..., min_length=1),
) -> Any:
    """Return ``{ "commits": CommitRef[] }``."""
    try:
        commits = await github_service.list_commits(owner, name)
    except Exception as exc:
        return _map_github_error(exc, repo=f"{owner}/{name}")
    return {"commits": _dump_many(commits)}


@router.get("/repo/releases")
async def github_repo_releases(
    owner: str = Query(..., min_length=1),
    name: str = Query(..., min_length=1),
) -> Any:
    """Return ``{ "releases": ReleaseRef[] }``."""
    try:
        releases = await github_service.list_releases(owner, name)
    except Exception as exc:
        return _map_github_error(exc, repo=f"{owner}/{name}")
    return {"releases": _dump_many(releases)}


@router.get("/rate-limit")
async def github_rate_limit() -> Any:
    """Return the current core :class:`github_client.RateLimit`."""
    try:
        limit = await github_service.rate_limit()
    except Exception as exc:
        return _map_github_error(exc)
    return limit.model_dump(mode="json")


@router.post("/index")
async def github_index(
    owner: str = Query(..., min_length=1),
    name: str = Query(..., min_length=1),
) -> Any:
    """Index a repository's README + Python files into ``rag_core``.

    README → ``repository_docs`` and Python files → ``repository_code``. Returns
    the index summary (see :func:`careerforge_api.github_service.index_repo`).
    """
    try:
        return await github_service.index_repo(owner, name)
    except Exception as exc:
        return _map_github_error(exc, repo=f"{owner}/{name}")


__all__ = ["router"]
