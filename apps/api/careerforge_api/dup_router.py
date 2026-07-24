"""Duplicate-detection endpoint (Phase 8).

``POST /api/v1/duplicates/check`` scores a proposed issue/finding against a set
of candidate issues/PRs and returns ranked duplicate matches with confidence and
explanations. Uses the real ``rag_core`` embedder for the semantic signal when
available, degrading to exact+lexical otherwise.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger("careerforge_api.dup_router")

router = APIRouter(prefix="/duplicates", tags=["duplicates"])


class _QueryModel(BaseModel):
    title: str = ""
    body: str = ""
    error_strings: list[str] = Field(default_factory=list)
    symbols: list[str] = Field(default_factory=list)
    stack_frames: list[str] = Field(default_factory=list)


class _CandidateModel(BaseModel):
    id: str
    number: int | None = None
    title: str = ""
    body: str = ""
    url: str | None = None
    state: str | None = None
    is_pull: bool = False


class DuplicateCheckRequest(BaseModel):
    """Body for ``POST /duplicates/check``."""

    query: _QueryModel
    candidates: list[_CandidateModel]
    top_k: int = 10
    use_embeddings: bool = True


def _error(status: int, code: str, message: str, detail: Any = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "detail": detail}},
    )


@router.post("/check")
async def check_duplicates(request: DuplicateCheckRequest) -> Any:
    """Rank ``candidates`` against ``query`` for duplication."""
    try:
        from dup_detect import Candidate, DuplicateQuery, detect_duplicates
    except Exception as exc:  # pragma: no cover - package optional at boot
        return _error(503, "DUP_UNAVAILABLE", "Duplicate detection unavailable.", str(exc))

    embedder = None
    if request.use_embeddings:
        try:
            from rag_core.config import get_rag_settings
            from rag_core.embeddings import get_embedder

            embedder = get_embedder(get_rag_settings())
        except Exception as exc:
            logger.warning("embedder unavailable, using exact+lexical only: %s", exc)

    query = DuplicateQuery(**request.query.model_dump())
    candidates = [Candidate(**c.model_dump()) for c in request.candidates]
    try:
        report = await detect_duplicates(query, candidates, embedder=embedder, top_k=request.top_k)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("duplicate check failed")
        return _error(500, "DUP_CHECK_FAILED", "Duplicate check failed.", str(exc))
    return report.model_dump(mode="json")
