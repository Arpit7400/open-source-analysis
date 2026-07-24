"""RAG HTTP surface — ``/api/v1/rag/*`` (RAG_CONTRACT.md § *New API surface*).

An :class:`~fastapi.APIRouter` with the three contract endpoints:

* ``POST /rag/query``               → :class:`rag_core.models.RagAnswer`
* ``POST /rag/index/repository``    → index summary
* ``GET  /rag/collections``         → per-collection counts

The router is a thin transport shell over :mod:`careerforge_api.rag_service`
(which owns the pipeline singleton and seeding). It:

* validates request bodies with Pydantic v2 models,
* returns the exact JSON shapes from the contract, and
* maps failures to the shared error envelope
  ``{"error": {"code", "message", "detail"}}`` (API_CONTRACT.md § *Conventions*)
  with an appropriate HTTP status — ``503`` when the RAG subsystem is down,
  ``400`` for an unknown domain, ``404`` for a missing repository path.

It is mounted by ``main.py`` under the ``/api/v1`` prefix, so the concrete paths
become ``/api/v1/rag/...``.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from careerforge_api import rag_service
from careerforge_api.rag_service import RagUnavailableError

logger = logging.getLogger("careerforge_api.rag_router")

router = APIRouter(prefix="/rag", tags=["rag"])


# ---------------------------------------------------------------------------
# Request models (Pydantic v2)
# ---------------------------------------------------------------------------
class RagQueryRequest(BaseModel):
    """``POST /api/v1/rag/query`` request body (RAG_CONTRACT.md)."""

    model_config = ConfigDict(extra="ignore")

    query: str = Field(..., min_length=1, description="The natural-language question.")
    domain: str = Field(..., min_length=1, description="One of the six fixed collections.")
    filters: dict[str, Any] | None = Field(
        default=None, description="Optional metadata/time/version filters."
    )
    top_k: int | None = Field(
        default=None, ge=1, description="Final context size; defaults to config."
    )


class RagIndexRepositoryRequest(BaseModel):
    """``POST /api/v1/rag/index/repository`` request body (RAG_CONTRACT.md)."""

    model_config = ConfigDict(extra="ignore")

    repo_path: str = Field(..., min_length=1, description="Local path to the repository.")
    repo_id: str = Field(..., min_length=1, description="Repository id, e.g. 'owner/name'.")
    commit: str | None = Field(default=None, description="Optional commit sha for provenance.")


# ---------------------------------------------------------------------------
# Error helper (shared contract envelope)
# ---------------------------------------------------------------------------
def _error(status_code: int, code: str, message: str, detail: Any = None) -> JSONResponse:
    """Return the contract error envelope with the given HTTP status."""
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "detail": detail}},
    )


def _unavailable(exc: RagUnavailableError) -> JSONResponse:
    """503 envelope for a degraded/unavailable RAG subsystem."""
    return _error(
        503,
        "RAG_UNAVAILABLE",
        "The RAG subsystem is unavailable.",
        exc.reason,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("/query")
async def rag_query(request: RagQueryRequest) -> Any:
    """Answer ``query`` against ``domain`` → :class:`RagAnswer` (or NO-ANSWER).

    A NO-ANSWER is a *successful* 200 response with ``answered: false`` and a
    ``no_answer_reason`` — it is not an error. Errors are reserved for an unknown
    domain (400) or a down subsystem (503).
    """
    try:
        answer = await rag_service.query(
            request.query, request.domain, request.filters, request.top_k
        )
    except RagUnavailableError as exc:
        return _unavailable(exc)
    except Exception as exc:  # unknown domain, embedder error, etc.
        # ``validate_domain`` raises ``UnknownDomainError`` (a ``ValueError``).
        if _is_unknown_domain(exc):
            return _error(400, "UNKNOWN_DOMAIN", "Unknown RAG domain.", str(exc))
        logger.exception("rag_query failed for domain=%s", request.domain)
        return _error(500, "RAG_QUERY_FAILED", "Failed to answer the query.", str(exc))
    # ``answer`` is a Pydantic v2 model; return its plain-dict serialization so
    # FastAPI emits the exact contract JSON shape.
    return answer.model_dump(mode="json")


@router.post("/index/repository")
async def rag_index_repository(request: RagIndexRepositoryRequest) -> Any:
    """Index a local repository directory → index summary (RAG_CONTRACT.md).

    Response::

        { "indexed_chunks": int, "collections": {domain: count},
          "embedder": str, "store": str }
    """
    try:
        summary = await rag_service.index_repository(
            request.repo_path, request.repo_id, request.commit
        )
    except RagUnavailableError as exc:
        return _unavailable(exc)
    except (NotADirectoryError, FileNotFoundError) as exc:
        return _error(404, "REPO_PATH_NOT_FOUND", "Repository path not found.", str(exc))
    except Exception as exc:
        logger.exception("rag_index_repository failed for %s", request.repo_path)
        return _error(500, "RAG_INDEX_FAILED", "Failed to index the repository.", str(exc))
    return summary


@router.get("/collections")
async def rag_collections() -> Any:
    """Return per-collection counts + active providers (RAG_CONTRACT.md).

    Response::

        { "collections": [ {"name": str, "count": int, "dim": int} ],
          "embedder": str, "store": str }
    """
    try:
        return await rag_service.collections()
    except RagUnavailableError as exc:
        return _unavailable(exc)
    except Exception as exc:
        logger.exception("rag_collections failed")
        return _error(500, "RAG_COLLECTIONS_FAILED", "Failed to list collections.", str(exc))


def _is_unknown_domain(exc: Exception) -> bool:
    """Best-effort detection of ``rag_core.domains.UnknownDomainError``.

    We avoid importing ``rag_core`` at module scope (so the router imports even
    when ``rag_core`` is absent), so match on the exception class name instead of
    an ``isinstance`` against a possibly-unavailable type.
    """
    return type(exc).__name__ == "UnknownDomainError" or (
        isinstance(exc, ValueError) and "Unknown RAG domain" in str(exc)
    )


__all__ = ["router", "RagQueryRequest", "RagIndexRepositoryRequest"]
