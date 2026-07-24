"""Hybrid retrieval: dense + sparse -> RRF -> rerank -> time/version filter.

Implements the middle of the pipeline defined in ``docs/RAG_CONTRACT.md``
§ *Retrieval pipeline* (handbook §5.2), **in this exact order**::

    QUERY -> (metadata/time/version filters applied to the store query)
          -> DENSE (embed query, vector search top N)
             + SPARSE (BM25 top N)
          -> RECIPROCAL RANK FUSION (k=60)
          -> RERANK (local reranker; fallback = lexical overlap)
          -> TIME/VERSION FILTER (drop stale unless the query asks for history)
          -> DEDUPE by (path, symbol)
          -> ranked ``RetrievedChunk``

Design guarantees
-----------------
* **Deterministic** given a fixed embedder: RRF and the tie-breaking sort keys
  are stable; no wall-clock or randomness enters ranking.
* **Local-first & replaceable.** The BM25 index, reranker, and embedder are all
  injected/config-driven; nothing is hard-coded.
* **Graceful degradation.** The reranker falls back to lexical overlap when no
  model is configured (handled inside :func:`rag_core.rerank.get_reranker`);
  BM25 simply contributes nothing when a domain has no registered corpus.

Because the vector store only exposes nearest-neighbour search (not the full
corpus), the BM25 sparse index is fed by the indexer via
:meth:`HybridRetriever.register_chunks`, which keeps an in-memory mirror of the
chunks known per domain and (re)builds the domain's BM25 index from it. Tests
and callers that index through :class:`rag_core.indexer.RepositoryIndexer` get
this wiring for free.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from rag_core.bm25 import BM25Index
from rag_core.config import RagSettings, get_rag_settings
from rag_core.models import Chunk, RetrievedChunk
from rag_core.rerank import get_reranker

if TYPE_CHECKING:  # pragma: no cover - typing only
    from rag_core.embeddings import Embedder
    from rag_core.rerank import Reranker
    from rag_core.vector_store import VectorStore

logger = logging.getLogger("rag_core.retrieval")

# Words in a query that signal the user wants historical/deprecated/versioned
# material, which suppresses the "drop stale" time/version filter.
_HISTORY_TERMS: frozenset[str] = frozenset(
    {
        "history",
        "historical",
        "changed",
        "change",
        "changes",
        "changelog",
        "deprecated",
        "deprecation",
        "version",
        "versions",
        "versioned",
        "previous",
        "older",
        "old",
        "past",
        "legacy",
        "migrate",
        "migration",
        "evolution",
        "evolved",
    }
)

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


def query_asks_for_history(query: str) -> bool:
    """Return ``True`` when the query wants history/deprecated/versioned info.

    Detection is a case-insensitive token match against :data:`_HISTORY_TERMS`.
    When true, the time/version filter keeps stale/superseded chunks instead of
    dropping them.
    """
    tokens = {token.lower() for token in _TOKEN_RE.findall(query)}
    return bool(tokens & _HISTORY_TERMS)


class _Bm25Adapter:
    """Duck-typed adapter over :class:`rag_core.bm25.BM25Index`.

    Track A owns ``bm25.py``; its exact method names may vary (``add`` /
    ``add_document`` / ``index`` for ingest, ``query`` / ``search`` / ``top_n``
    for retrieval). This adapter binds to whatever the concrete index exposes so
    the retriever is resilient to reasonable naming, while still importing the
    contract class ``BM25Index`` verbatim. Retrieval always returns
    ``(chunk_id, score)`` pairs sorted best-first.
    """

    # Per-chunk add methods only. ``add`` is intentionally excluded: the
    # contract's ``BM25Index.add`` takes a *list* of chunks and is handled by
    # the bulk path in ``_build``; calling it with a single Chunk would make it
    # iterate the model's fields instead of a chunk list.
    _ADD_METHODS: tuple[str, ...] = (
        "add_document",
        "add_documents",
        "index",
        "add_chunk",
        "add_chunks",
    )
    _QUERY_METHODS: tuple[str, ...] = (
        "query",
        "search",
        "top_n",
        "retrieve",
        "rank",
    )

    def __init__(self, chunks: list[Chunk]) -> None:
        self._index = BM25Index()
        self._chunks = list(chunks)
        self._by_id: dict[str, Chunk] = {c.id: c for c in self._chunks}
        self._build()

    # -- ingest --------------------------------------------------------------

    def _build(self) -> None:
        """Populate the underlying index, trying bulk then per-doc ingest."""
        # Prefer a bulk ingest of the whole corpus if the index supports it.
        # The contract's ``BM25Index.add(chunks: list[Chunk])`` takes the whole
        # list, so ``add`` is tried first here (it must NOT be called per-chunk
        # below, which is why it is excluded from the per-doc ``_add_one`` path).
        for name in ("add", "add_documents", "add_chunks", "build", "fit", "index_all"):
            method = getattr(self._index, name, None)
            if callable(method):
                try:
                    method(self._chunks)
                    return
                except TypeError:
                    # Signature didn't accept a chunk list; fall through.
                    pass
        # Otherwise add each chunk one at a time via the first method that works.
        for chunk in self._chunks:
            self._add_one(chunk)

    def _add_one(self, chunk: Chunk) -> None:
        for name in self._ADD_METHODS:
            method = getattr(self._index, name, None)
            if not callable(method):
                continue
            for args in (
                (chunk,),
                (chunk.id, chunk.text),
                (chunk.text,),
                (chunk.id, chunk.text, chunk.metadata),
            ):
                try:
                    method(*args)
                    return
                except TypeError:
                    continue
        logger.debug(
            "BM25Index exposes no compatible add method; sparse retrieval for "
            "chunk %s is a no-op.",
            chunk.id,
        )

    # -- retrieval -----------------------------------------------------------

    def query(self, text: str, top_n: int) -> list[tuple[str, float]]:
        """Return ``(chunk_id, score)`` pairs, best-first, from the BM25 index."""
        for name in self._QUERY_METHODS:
            method = getattr(self._index, name, None)
            if not callable(method):
                continue
            for args in ((text, top_n), (text,)):
                try:
                    raw = method(*args)
                except TypeError:
                    continue
                normalised = self._normalise_results(raw, top_n)
                if normalised is not None:
                    return normalised
        return []

    def _normalise_results(
        self, raw: Any, top_n: int
    ) -> list[tuple[str, float]] | None:
        """Coerce a variety of BM25 return shapes into ``[(chunk_id, score)]``.

        Accepts iterables of: ``(chunk_id, score)`` tuples, ``(Chunk, score)``
        tuples, bare chunk ids, bare :class:`Chunk` objects, or objects exposing
        ``.id``/``.chunk``/``.score``. Returns ``None`` when nothing usable is
        found so the caller can try the next method name.
        """
        if raw is None:
            return None
        try:
            items = list(raw)
        except TypeError:
            return None
        results: list[tuple[str, float]] = []
        for rank, item in enumerate(items):
            cid, score = self._extract_id_score(item, rank)
            if cid is None:
                continue
            if cid not in self._by_id:
                continue
            results.append((cid, score))
        if not results:
            return None
        results.sort(key=lambda pair: (-pair[1], pair[0]))
        return results[:top_n]

    def _extract_id_score(
        self, item: Any, rank: int
    ) -> tuple[str | None, float]:
        # (id_or_chunk, score) tuple
        if isinstance(item, tuple) and len(item) == 2:
            key, score = item
            cid = self._as_id(key)
            try:
                return cid, float(score)
            except (TypeError, ValueError):
                return cid, self._rank_score(rank)
        # bare id / chunk
        cid = self._as_id(item)
        if cid is not None:
            return cid, self._rank_score(rank)
        # object with attributes
        obj_id = self._as_id(
            getattr(item, "chunk", None) or getattr(item, "id", None)
        )
        if obj_id is None:
            obj_id = self._as_id(getattr(item, "chunk_id", None))
        score = getattr(item, "score", None)
        try:
            return obj_id, float(score) if score is not None else self._rank_score(rank)
        except (TypeError, ValueError):
            return obj_id, self._rank_score(rank)

    @staticmethod
    def _as_id(value: Any) -> str | None:
        if isinstance(value, Chunk):
            return value.id
        if isinstance(value, str):
            return value
        return None

    @staticmethod
    def _rank_score(rank: int) -> float:
        """Monotonic descending pseudo-score when the index yields only order."""
        return 1.0 / float(rank + 1)

    def get(self, chunk_id: str) -> Chunk | None:
        return self._by_id.get(chunk_id)


class HybridRetriever:
    """Dense + sparse hybrid retriever with RRF fusion and reranking.

    Parameters
    ----------
    embedder:
        Provides the query embedding for dense search.
    vector_store:
        Backing :class:`rag_core.vector_store.VectorStore` for dense search.
    settings:
        :class:`rag_core.config.RagSettings` (``rag_top_n``, ``rag_top_k``,
        ``rrf_k`` and the reranker config are read from here).
    reranker:
        Optional injected :class:`rag_core.rerank.Reranker`. When ``None`` one is
        constructed via :func:`rag_core.rerank.get_reranker` (which itself
        degrades to a lexical reranker when no model is configured).

    The retriever keeps a per-domain in-memory mirror of the chunks it has been
    told about (:meth:`register_chunks`) and (re)builds a per-domain BM25 index
    from that mirror. This is what feeds the sparse leg of retrieval.
    """

    def __init__(
        self,
        embedder: Embedder,
        vector_store: VectorStore,
        settings: RagSettings | None = None,
        *,
        reranker: Reranker | None = None,
    ) -> None:
        self._embedder = embedder
        self._store = vector_store
        self._settings = settings or get_rag_settings()
        self._reranker: Reranker = reranker or get_reranker(self._settings)
        # domain -> {chunk_id: Chunk} mirror, and domain -> built BM25 adapter.
        self._corpus: dict[str, dict[str, Chunk]] = {}
        self._bm25: dict[str, _Bm25Adapter] = {}

    # -- BM25 corpus management ---------------------------------------------

    def register_chunks(self, domain: str, chunks: Iterable[Chunk]) -> None:
        """Add ``chunks`` to the in-memory mirror for ``domain`` and rebuild BM25.

        Called by :class:`rag_core.indexer.RepositoryIndexer` after upserting so
        the sparse index stays in lock-step with the vector store. Idempotent:
        re-registering the same chunk id overwrites in place.
        """
        mirror = self._corpus.setdefault(domain, {})
        added = 0
        for chunk in chunks:
            mirror[chunk.id] = chunk
            added += 1
        if added:
            self._rebuild_bm25(domain)
            logger.debug(
                "Registered %d chunk(s) for BM25 domain=%s (corpus size=%d).",
                added,
                domain,
                len(mirror),
            )

    def reload_bm25(self, domain: str, chunks: Iterable[Chunk]) -> None:
        """Replace the BM25 corpus for ``domain`` wholesale, then rebuild.

        Use when the caller has an authoritative, complete chunk set for a
        domain (e.g. re-indexing a repository from scratch).
        """
        self._corpus[domain] = {chunk.id: chunk for chunk in chunks}
        self._rebuild_bm25(domain)

    def _rebuild_bm25(self, domain: str) -> None:
        chunks = list(self._corpus.get(domain, {}).values())
        self._bm25[domain] = _Bm25Adapter(chunks)

    def known_chunks(self, domain: str) -> list[Chunk]:
        """Return the chunks currently mirrored for ``domain`` (for BM25)."""
        return list(self._corpus.get(domain, {}).values())

    # -- retrieval -----------------------------------------------------------

    async def retrieve(
        self,
        query: str,
        domain: str,
        filters: dict[str, Any] | None = None,
        top_n: int | None = None,
    ) -> list[RetrievedChunk]:
        """Run the hybrid pipeline and return ranked :class:`RetrievedChunk`.

        Steps (exact contract order): dense + sparse retrieval of ``top_n`` each,
        RRF fusion (``k = rrf_k``), rerank of the fused pool, time/version
        filtering (kept when the query asks for history), dedupe by
        ``(path, symbol)``. Deterministic given a fixed embedder.
        """
        pool = top_n if top_n is not None else self._settings.rag_top_n

        dense = await self._dense(query, domain, filters, pool)
        sparse = self._sparse(query, domain, pool)

        fused = self._reciprocal_rank_fusion(dense, sparse)
        if not fused:
            return []

        reranked = await self._rerank(query, fused)
        filtered = self._apply_time_version_filter(query, reranked)
        deduped = self._dedupe(filtered)
        deduped.sort(key=self._sort_key)
        return deduped

    # -- dense / sparse ------------------------------------------------------

    async def _dense(
        self,
        query: str,
        domain: str,
        filters: dict[str, Any] | None,
        pool: int,
    ) -> list[tuple[Chunk, float]]:
        vectors = await self._embedder.embed([query])
        if not vectors:
            return []
        query_vector = vectors[0]
        try:
            return await self._store.search(domain, query_vector, pool, filters)
        except Exception as exc:  # pragma: no cover - backend dependent
            logger.warning("Dense search failed for domain=%s: %s", domain, exc)
            return []

    def _sparse(
        self, query: str, domain: str, pool: int
    ) -> list[tuple[Chunk, float]]:
        adapter = self._bm25.get(domain)
        if adapter is None:
            return []
        results: list[tuple[Chunk, float]] = []
        for chunk_id, score in adapter.query(query, pool):
            chunk = adapter.get(chunk_id)
            if chunk is not None:
                results.append((chunk, score))
        return results

    # -- fusion --------------------------------------------------------------

    def _reciprocal_rank_fusion(
        self,
        dense: list[tuple[Chunk, float]],
        sparse: list[tuple[Chunk, float]],
    ) -> list[RetrievedChunk]:
        """Fuse dense & sparse rankings via RRF (``score = Σ 1/(k + rank)``).

        Ranks are 1-indexed within each list (in the order returned, i.e. by
        descending relevance). A chunk present in both lists sums its
        contributions. Raw dense/sparse scores are preserved on the
        :class:`RetrievedChunk` for transparency.
        """
        k = self._settings.rrf_k
        merged: dict[str, RetrievedChunk] = {}

        def contribute(
            items: list[tuple[Chunk, float]],
            which: str,
        ) -> None:
            for rank, (chunk, score) in enumerate(items, start=1):
                rrf = 1.0 / (k + rank)
                existing = merged.get(chunk.id)
                if existing is None:
                    existing = RetrievedChunk(
                        chunk=chunk,
                        dense_score=None,
                        sparse_score=None,
                        fused_score=0.0,
                        rerank_score=None,
                        final_score=0.0,
                    )
                    merged[chunk.id] = existing
                existing.fused_score += rrf
                if which == "dense":
                    existing.dense_score = score
                else:
                    existing.sparse_score = score

        contribute(dense, "dense")
        contribute(sparse, "sparse")

        for rc in merged.values():
            rc.final_score = rc.fused_score

        fused = list(merged.values())
        fused.sort(key=lambda rc: (-rc.fused_score, rc.chunk.id))
        return fused

    # -- rerank --------------------------------------------------------------

    async def _rerank(
        self, query: str, fused: list[RetrievedChunk]
    ) -> list[RetrievedChunk]:
        """Rerank the fused pool; ``final_score`` becomes the rerank score.

        On any reranker failure we keep the fused ordering (``final_score``
        stays the RRF score) so retrieval never hard-fails on a bad reranker.
        """
        chunks = [rc.chunk for rc in fused]
        try:
            scores = await self._reranker.rerank(query, chunks)
        except Exception as exc:  # pragma: no cover - provider dependent
            logger.warning("Reranker failed (%s); keeping RRF order.", exc)
            return fused
        if not scores or len(scores) != len(fused):
            logger.debug(
                "Reranker returned %d scores for %d chunks; keeping RRF order.",
                len(scores) if scores else 0,
                len(fused),
            )
            return fused
        for rc, score in zip(fused, scores, strict=True):
            rc.rerank_score = float(score)
            rc.final_score = float(score)
        fused.sort(key=self._sort_key)
        return fused

    # -- time / version filtering -------------------------------------------

    def _apply_time_version_filter(
        self, query: str, ranked: list[RetrievedChunk]
    ) -> list[RetrievedChunk]:
        """Drop stale/superseded chunks unless the query asks for history.

        "Stale" is decided per ``(path, symbol)`` group: only the most recent
        ``published_at`` (ISO-8601, lexicographic) survives; older entries are
        dropped. Chunks with no ``published_at`` are never dropped by this rule
        (they carry no staleness signal). When the query asks for history the
        whole ranked list passes through unchanged.
        """
        if query_asks_for_history(query):
            return ranked

        # Newest published_at per (path, symbol) group.
        newest: dict[tuple[str | None, str | None], str] = {}
        for rc in ranked:
            published = rc.chunk.published_at
            if not published:
                continue
            key = (rc.chunk.path, rc.chunk.symbol)
            current = newest.get(key)
            if current is None or published > current:
                newest[key] = published

        kept: list[RetrievedChunk] = []
        for rc in ranked:
            published = rc.chunk.published_at
            if not published:
                kept.append(rc)
                continue
            key = (rc.chunk.path, rc.chunk.symbol)
            if published == newest.get(key):
                kept.append(rc)
            else:
                logger.debug(
                    "Dropping stale chunk %s (published_at=%s < newest=%s).",
                    rc.chunk.id,
                    published,
                    newest.get(key),
                )
        return kept

    # -- dedupe --------------------------------------------------------------

    @staticmethod
    def _dedupe(ranked: list[RetrievedChunk]) -> list[RetrievedChunk]:
        """Drop duplicate ``(path, symbol)`` entries, keeping the best-scored.

        Because ``ranked`` is expected best-first, the first occurrence of a
        ``(path, symbol)`` key wins. Chunks with no path *and* no symbol are
        deduped by chunk id instead so distinct free-text chunks survive.
        """
        seen: set[tuple[str | None, str | None]] = set()
        seen_ids: set[str] = set()
        out: list[RetrievedChunk] = []
        for rc in ranked:
            path, symbol = rc.chunk.path, rc.chunk.symbol
            if path is None and symbol is None:
                if rc.chunk.id in seen_ids:
                    continue
                seen_ids.add(rc.chunk.id)
                out.append(rc)
                continue
            key = (path, symbol)
            if key in seen:
                continue
            seen.add(key)
            out.append(rc)
        return out

    @staticmethod
    def _sort_key(rc: RetrievedChunk) -> tuple[float, str]:
        """Deterministic best-first sort: highest ``final_score``, id tiebreak."""
        return (-rc.final_score, rc.chunk.id)


__all__ = ["HybridRetriever", "query_asks_for_history"]
