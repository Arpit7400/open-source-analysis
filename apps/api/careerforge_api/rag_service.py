"""Thin adapter between the FastAPI transport layer and ``rag_core``.

This module owns the *lifecycle* of the real RAG subsystem inside the API
process. It:

* Lazily builds a **singleton** :class:`rag_core.pipeline.RagPipeline` via
  :meth:`RagPipeline.build` (which itself resolves every provider local-first:
  Ollama embedder or hash fallback, Qdrant server / on-disk / ``:memory:``,
  lexical or model reranker). Building is done once and cached.

* **Seeds** the repository's own ``docs/`` directory into ``repository_docs`` and
  a small code sample (``packages/rag_core/rag_core``) into ``repository_code``
  the first time the pipeline is used, so a fresh ``POST /api/v1/rag/query``
  returns a real, cited answer out of the box. Seeding is lazy and cached, runs
  under a lock so concurrent first requests don't double-index, and never raises
  into the request path (a seed failure is logged and the query proceeds).

* **Degrades gracefully.** If ``rag_core`` cannot be imported, or the pipeline
  cannot be built, the adapter enters a clearly-flagged *unavailable* state
  (:data:`health_label` returns ``"down"``) and every operation raises
  :class:`RagUnavailableError`. The rest of the API still boots and serves — the
  RAG endpoints simply report the degradation using the contract error shape.

Nothing here is hard-coded: providers and connection modes are chosen entirely
by :class:`rag_core.config.RagSettings` (``CAREERFORGE_*`` env). Which providers
actually served a request are surfaced on the answer and via
:func:`health_label` so degradation is never silent.

Everything is cross-platform: repository paths are resolved with
:mod:`pathlib` from this file's location, with no shell/OS assumptions.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    from rag_core.models import RagAnswer
    from rag_core.pipeline import RagPipeline

logger = logging.getLogger("careerforge_api.rag_service")

# ``rag_service.py`` lives at ``apps/api/careerforge_api/rag_service.py``.
# parents[3] is the repository root (``.../careerforge-ai``).
_REPO_ROOT: Path = Path(__file__).resolve().parents[3]

#: Repo-relative source id used for the seeded corpus provenance.
_SEED_REPO_ID: str = "careerforge-ai/careerforge-ai"

#: Directories seeded on first use. ``docs/`` → ``repository_docs`` (Markdown),
#: and a small real code sample → ``repository_code`` (Python AST chunks). The
#: code sample is intentionally the ``rag_core`` package itself so a fresh
#: install returns genuine, cited answers about the RAG subsystem.
_SEED_DOCS_DIR: Path = _REPO_ROOT / "docs"
_SEED_CODE_DIR: Path = _REPO_ROOT / "packages" / "rag_core" / "rag_core"


class RagUnavailableError(RuntimeError):
    """Raised when the RAG subsystem could not be initialised or used.

    Carries a human-readable ``reason`` the router surfaces in the contract
    error envelope's ``detail`` so operators can see *why* RAG is down without
    reading server logs.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class _RagService:
    """Process-wide holder for the lazily-built pipeline + seed state.

    A single instance (:data:`_SERVICE`) is shared by every request. All mutable
    state transitions (build, seed) are guarded by an :class:`asyncio.Lock` so
    concurrent first requests cannot race into a double build/index.
    """

    def __init__(self) -> None:
        self._pipeline: RagPipeline | None = None
        self._build_failed_reason: str | None = None
        self._seeded: bool = False
        self._lock = asyncio.Lock()

    # -- construction --------------------------------------------------------

    def _try_build_locked(self) -> RagPipeline | None:
        """Build the pipeline once; cache success or the failure reason.

        Must be called while holding :attr:`_lock`. Returns the pipeline or
        ``None`` (with :attr:`_build_failed_reason` set) on failure. Import and
        build errors are caught so the API keeps booting when ``rag_core`` (or
        its deps like ``qdrant-client``) is missing.
        """
        if self._pipeline is not None:
            return self._pipeline
        if self._build_failed_reason is not None:
            return None
        try:
            from rag_core.pipeline import RagPipeline as _RagPipeline
        except Exception as exc:  # ImportError or transitive dep failure
            self._build_failed_reason = f"rag_core import failed: {exc}"
            logger.warning(
                "RAG subsystem unavailable: %s. RAG endpoints will report 'down'.",
                self._build_failed_reason,
            )
            return None
        try:
            self._pipeline = _RagPipeline.build()
        except Exception as exc:  # provider/config/build failure
            self._build_failed_reason = f"RagPipeline.build() failed: {exc}"
            logger.warning(
                "RAG subsystem unavailable: %s. RAG endpoints will report 'down'.",
                self._build_failed_reason,
            )
            return None
        logger.info(
            "RAG pipeline built (embedder=%s store=%s).",
            self._pipeline.used_embedder,
            self._pipeline.used_vector_store,
        )
        return self._pipeline

    async def _ensure_ready(self) -> RagPipeline:
        """Return the built + seeded pipeline, or raise :class:`RagUnavailableError`."""
        async with self._lock:
            pipeline = self._try_build_locked()
            if pipeline is None:
                raise RagUnavailableError(
                    self._build_failed_reason or "RAG subsystem is unavailable."
                )
            await self._seed_locked(pipeline)
            return pipeline

    # -- seeding -------------------------------------------------------------

    async def _seed_locked(self, pipeline: RagPipeline) -> None:
        """Index the repo's own docs/code once, best-effort (must hold lock).

        A seed failure is logged and swallowed: an empty corpus simply yields
        NO-ANSWER responses rather than breaking the endpoint. ``_seeded`` is set
        regardless so we never retry a failing seed on every request.
        """
        if self._seeded:
            return
        self._seeded = True
        try:
            if _SEED_DOCS_DIR.is_dir():
                summary = await pipeline.index_repository(
                    _SEED_DOCS_DIR, _SEED_REPO_ID, commit=None
                )
                logger.info("Seeded docs from %s: %s", _SEED_DOCS_DIR, summary)
            else:
                logger.info("Seed docs dir %s absent; skipping.", _SEED_DOCS_DIR)

            if _SEED_CODE_DIR.is_dir():
                summary = await pipeline.index_repository(
                    _SEED_CODE_DIR, _SEED_REPO_ID, commit=None
                )
                logger.info("Seeded code from %s: %s", _SEED_CODE_DIR, summary)
            else:
                logger.info("Seed code dir %s absent; skipping.", _SEED_CODE_DIR)
        except Exception as exc:  # never break the request path on a seed error
            logger.warning("RAG seed indexing failed (%s); continuing empty.", exc)

    # -- operations ----------------------------------------------------------

    async def query(
        self,
        query: str,
        domain: str,
        filters: dict[str, Any] | None,
        top_k: int | None,
    ) -> RagAnswer:
        pipeline = await self._ensure_ready()
        return await pipeline.answer(query, domain, filters, top_k)

    async def index_repository(
        self,
        repo_path: str,
        repo_id: str,
        commit: str | None,
    ) -> dict[str, Any]:
        pipeline = await self._ensure_ready()
        # Do not let an explicit index call re-seed; the caller supplies its own
        # corpus. (Seeding already ran inside _ensure_ready.)
        return await pipeline.index_repository(repo_path, repo_id, commit)

    async def collections(self) -> dict[str, Any]:
        pipeline = await self._ensure_ready()
        return await pipeline.collections()

    def health_label(self) -> str:
        """Return the ``services.rag`` health value for ``/system/health``.

        One of (per RAG_CONTRACT.md):

        * ``"ollama+qdrant-server"`` / ``"ollama+qdrant-local"``
        * ``"hash+qdrant-server"``   / ``"hash+qdrant-local"``
        * ``"down"`` when the subsystem could not be built.

        This is a **synchronous, non-seeding** probe: it builds the pipeline (a
        cheap, cached operation) but never triggers indexing, so the health
        endpoint stays fast. On any failure it returns ``"down"`` — health
        checks must never raise.
        """
        try:
            # Build without seeding. We can't take the async lock from a sync
            # context, so we reuse the already-built pipeline when present and
            # otherwise attempt a one-shot build guarded by try/except. The
            # build is idempotent and cached on the instance.
            pipeline = self._pipeline
            if pipeline is None and self._build_failed_reason is None:
                pipeline = self._try_build_locked()
            if pipeline is None:
                return "down"
            embed = _embedder_label(pipeline.used_embedder)
            store = _store_label(pipeline.used_vector_store)
            return f"{embed}+{store}"
        except Exception as exc:  # health must never raise
            logger.debug("health_label probe failed (%s); reporting down.", exc)
            return "down"


def _embedder_label(used_embedder: str) -> str:
    """Map ``RagAnswer.used_embedder`` to the health prefix (``ollama``/``hash``)."""
    return "ollama" if used_embedder.startswith("ollama") else "hash"


def _store_label(used_vector_store: str) -> str:
    """Map ``RagAnswer.used_vector_store`` to the health suffix.

    ``"qdrant:server"`` → ``"qdrant-server"``; anything else (``"qdrant:local"``)
    → ``"qdrant-local"``.
    """
    return "qdrant-server" if used_vector_store.endswith("server") else "qdrant-local"


# Process-wide singleton used by the router and the health endpoint.
_SERVICE = _RagService()


# -- module-level facade (what the router imports) ---------------------------


async def query(
    query_text: str,
    domain: str,
    filters: dict[str, Any] | None = None,
    top_k: int | None = None,
) -> RagAnswer:
    """Answer ``query_text`` against ``domain``; see :meth:`_RagService.query`."""
    return await _SERVICE.query(query_text, domain, filters, top_k)


async def index_repository(
    repo_path: str,
    repo_id: str,
    commit: str | None = None,
) -> dict[str, Any]:
    """Index a local repository directory; see :meth:`_RagService.index_repository`."""
    return await _SERVICE.index_repository(repo_path, repo_id, commit)


async def collections() -> dict[str, Any]:
    """Return per-collection counts; see :meth:`_RagService.collections`."""
    return await _SERVICE.collections()


def health_label() -> str:
    """Return the ``services.rag`` health string; see :meth:`_RagService.health_label`."""
    return _SERVICE.health_label()


__all__ = [
    "RagUnavailableError",
    "query",
    "index_repository",
    "collections",
    "health_label",
]
