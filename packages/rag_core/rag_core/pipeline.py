"""End-to-end RAG pipeline (handbook §5.2).

:class:`RagPipeline` wires the whole subsystem together and exposes a single
:meth:`answer` coroutine that implements the contract pipeline **in exact
order**::

    QUERY -> (metadata/time/version filters)
          -> DENSE + SPARSE  (HybridRetriever)
          -> RECIPROCAL RANK FUSION (k=60)
          -> RERANK
          -> TIME/VERSION FILTER
          -> CONTEXT ASSEMBLY (top_k, dedupe)
          -> CLAIM GENERATION w/ CITATIONS (LLM if available; else extractive)
          -> CLAIM-EVIDENCE VERIFICATION (per-claim, via ClaimVerifier)
          -> ANSWER or NO-ANSWER (confidence threshold / no supported claim)

Construction is via :meth:`RagPipeline.build`, which resolves every provider
from config (embedder, vector store, reranker, verifier, retriever, indexer) so
the whole thing boots local-first with no Docker and no Ollama, degrading to the
hash embedder + in-memory Qdrant when needed. Which providers actually served a
request is surfaced on the :class:`~rag_core.models.RagAnswer`
(``used_embedder`` / ``used_vector_store``) so degradation is never silent.
"""

from __future__ import annotations

import inspect
import logging
import re
import time
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any

import httpx

from rag_core.citations import build_citations
from rag_core.config import RagSettings, get_rag_settings
from rag_core.domains import validate_domain
from rag_core.embeddings import get_embedder
from rag_core.indexer import RepositoryIndexer
from rag_core.models import (
    Chunk,
    Citation,
    Claim,
    ClaimVerdict,
    RagAnswer,
    RetrievedChunk,
)
from rag_core.rerank import get_reranker
from rag_core.retrieval import HybridRetriever
from rag_core.vector_store import QdrantVectorStore
from rag_core.verifier import ClaimVerifier

if TYPE_CHECKING:  # pragma: no cover - typing only
    from pathlib import Path

    from rag_core.embeddings import Embedder
    from rag_core.rerank import Reranker
    from rag_core.vector_store import VectorStore

logger = logging.getLogger("rag_core.pipeline")

# Sentence boundary for extractive claim splitting.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
# Citation markers embedded in an LLM answer, e.g. "[1]" or "[2]".
_MARKER_RE = re.compile(r"\[(\d+)\]")


class RagPipeline:
    """The full retrieval-augmented-generation pipeline.

    Prefer :meth:`build` to construct one; the initialiser takes fully-wired
    collaborators for tests and advanced use.
    """

    def __init__(
        self,
        *,
        settings: RagSettings,
        embedder: Embedder,
        vector_store: VectorStore,
        retriever: HybridRetriever,
        reranker: Reranker,
        verifier: ClaimVerifier,
        indexer: RepositoryIndexer,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._settings = settings
        self._embedder = embedder
        self._store = vector_store
        self._retriever = retriever
        self._reranker = reranker
        self._verifier = verifier
        self._indexer = indexer
        self._clock: Callable[[], float] = clock or time.perf_counter

    # -- construction --------------------------------------------------------

    @classmethod
    def build(
        cls,
        settings: RagSettings | None = None,
        *,
        clock: Callable[[], float] | None = None,
    ) -> RagPipeline:
        """Wire the pipeline from config, resolving every provider local-first.

        Resolves the embedder (Ollama or hash fallback), the Qdrant vector store
        (server / on-disk / in-memory), the reranker (model or lexical), the
        hybrid retriever, the claim verifier, and the repository indexer.
        """
        settings = settings or get_rag_settings()
        embedder = get_embedder(settings)
        vector_store = QdrantVectorStore(settings)
        reranker = get_reranker(settings)
        retriever = HybridRetriever(
            embedder, vector_store, settings, reranker=reranker
        )
        verifier = ClaimVerifier(settings)
        indexer = RepositoryIndexer(embedder, vector_store, retriever, settings)
        logger.info(
            "RagPipeline built: embedder=%s store=%s reranker=%s.",
            embedder.name,
            getattr(vector_store, "mode", "qdrant:local"),
            type(reranker).__name__,
        )
        return cls(
            settings=settings,
            embedder=embedder,
            vector_store=vector_store,
            retriever=retriever,
            reranker=reranker,
            verifier=verifier,
            indexer=indexer,
            clock=clock,
        )

    # -- properties / passthroughs ------------------------------------------

    @property
    def retriever(self) -> HybridRetriever:
        return self._retriever

    @property
    def indexer(self) -> RepositoryIndexer:
        return self._indexer

    @property
    def used_embedder(self) -> str:
        return self._embedder.name

    @property
    def used_vector_store(self) -> str:
        return getattr(self._store, "mode", "qdrant:local")

    async def index_repository(
        self,
        repo_path: str | Path,
        repo_id: str,
        commit: str | None = None,
    ) -> dict[str, Any]:
        """Passthrough to :meth:`RepositoryIndexer.index_repository`."""
        return await self._indexer.index_repository(repo_path, repo_id, commit)

    async def index_documents(
        self, domain: str, docs: Iterable[Chunk]
    ) -> dict[str, Any]:
        """Passthrough to :meth:`RepositoryIndexer.index_documents`."""
        return await self._indexer.index_documents(domain, docs)

    async def collections(self) -> dict[str, Any]:
        """Return per-collection counts, matching ``GET /api/v1/rag/collections``.

        ::

            {
              "collections": [ {"name": str, "count": int, "dim": int}, ... ],
              "embedder": str,
              "store": str,
            }
        """
        from rag_core.domains import DOMAINS

        entries: list[dict[str, Any]] = []
        for name in DOMAINS:
            count = await self._store.count(name)
            entries.append(
                {"name": name, "count": int(count), "dim": self._embedder.dim}
            )
        return {
            "collections": entries,
            "embedder": self._embedder.name,
            "store": self.used_vector_store,
        }

    # -- the pipeline --------------------------------------------------------

    async def answer(
        self,
        query: str,
        domain: str,
        filters: dict[str, Any] | None = None,
        top_k: int | None = None,
    ) -> RagAnswer:
        """Answer ``query`` against ``domain`` following the exact contract order.

        Returns a fully-populated :class:`RagAnswer`. ``answered=False`` denotes
        a NO-ANSWER: either the top retrieval score is below
        ``settings.rag_min_score`` or the verifier found no supported claim.
        """
        validate_domain(domain)
        started = self._clock()
        k = top_k if top_k is not None else self._settings.rag_top_k

        # (1) filters -> (2) dense+sparse -> (3) RRF -> (4) rerank ->
        # (5) time/version filter — all handled by the retriever, in order.
        retrieved = await self._retriever.retrieve(
            query, domain, filters, self._settings.rag_top_n
        )

        # NO-ANSWER: nothing retrieved, or top score below the min threshold.
        if not retrieved:
            return self._no_answer(
                query, domain, retrieved, "No chunks retrieved for the query.", started
            )
        top_score = max(rc.final_score for rc in retrieved)
        if top_score < self._settings.rag_min_score:
            return self._no_answer(
                query,
                domain,
                retrieved,
                (
                    f"Top score {top_score:.3f} is below the confidence "
                    f"threshold {self._settings.rag_min_score:.3f}."
                ),
                started,
            )

        # (6) CONTEXT ASSEMBLY: top_k (already deduped/ordered by the retriever).
        context = retrieved[:k]

        # Build citations over the assembled context (marker order == context order).
        citations = self._citations_for(context)
        marker_to_chunk_id = {c.marker: c.chunk_id for c in citations}
        chunk_by_id = {rc.chunk.id: rc.chunk for rc in context}

        # (7) CLAIM GENERATION w/ CITATIONS: LLM if available, else extractive.
        answer_md, claims = await self._generate(query, context, citations)

        # (8) CLAIM-EVIDENCE VERIFICATION: verify each claim vs its cited chunks.
        verdicts = await self._verify_claims(claims, marker_to_chunk_id, chunk_by_id)

        # (9) ANSWER or NO-ANSWER: require at least one supported claim.
        answered = any(v.supported for v in verdicts)
        if not answered:
            return self._no_answer(
                query,
                domain,
                retrieved,
                "No generated claim was supported by its cited evidence.",
                started,
                claims=claims,
                citations=citations,
                verdicts=verdicts,
            )

        return RagAnswer(
            query=query,
            domain=domain,
            answered=True,
            answer_markdown=answer_md,
            claims=claims,
            citations=citations,
            verdicts=verdicts,
            retrieved=retrieved,
            no_answer_reason=None,
            used_embedder=self.used_embedder,
            used_vector_store=self.used_vector_store,
            latency_ms=self._elapsed_ms(started),
        )

    # -- claim generation ----------------------------------------------------

    async def _generate(
        self,
        query: str,
        context: list[RetrievedChunk],
        citations: list[Citation],
    ) -> tuple[str, list[Claim]]:
        """Generate a grounded markdown answer + claims for ``context``.

        Uses a low-temperature Ollama completion when ``rag_llm_model`` is set
        and reachable; otherwise composes an extractive answer straight from the
        context. Either way, every claim carries the citation markers of the
        chunks that back it. Falls back to extractive on any LLM failure.
        """
        model = (self._settings.rag_llm_model or "").strip()
        if model:
            generated = await self._generate_with_llm(query, context, citations, model)
            if generated is not None:
                return generated
            logger.info("LLM generation unavailable/failed; using extractive answer.")
        return self._generate_extractive(context, citations)

    def _generate_extractive(
        self,
        context: list[RetrievedChunk],
        citations: list[Citation],
    ) -> tuple[str, list[Claim]]:
        """Compose an answer directly from the top chunks with citation markers.

        Each context chunk contributes one claim (its most salient sentence),
        tagged with that chunk's citation marker. Deterministic and offline.
        """
        marker_by_chunk = {c.chunk_id: c.marker for c in citations}
        lines: list[str] = []
        claims: list[Claim] = []
        for rc in context:
            marker = marker_by_chunk.get(rc.chunk.id)
            if marker is None:
                continue
            sentence = self._salient_sentence(rc.chunk.text)
            if not sentence:
                continue
            claim_text = f"{sentence} {marker}"
            lines.append(f"- {claim_text}")
            claims.append(Claim(text=sentence, citation_markers=[marker]))
        if not lines:
            # Nothing quotable; still emit a minimal grounded pointer.
            first = context[0]
            marker = marker_by_chunk.get(first.chunk.id, "[1]")
            snippet = self._salient_sentence(first.chunk.text) or first.chunk.text.strip()
            claims = [Claim(text=snippet, citation_markers=[marker])]
            lines = [f"- {snippet} {marker}"]
        answer_md = "\n".join(lines)
        return answer_md, claims

    async def _generate_with_llm(
        self,
        query: str,
        context: list[RetrievedChunk],
        citations: list[Citation],
        model: str,
    ) -> tuple[str, list[Claim]] | None:
        """Ask Ollama for a grounded markdown answer citing ``[n]`` markers.

        Returns ``None`` on any failure so the caller falls back to extractive.
        Claims are derived from the returned answer's sentences and the markers
        they contain.
        """
        context_block = self._format_context(context, citations)
        prompt = (
            "You are a precise technical assistant. Answer the QUESTION using ONLY "
            "the CONTEXT below. Every sentence that makes a factual claim MUST end "
            "with the bracketed citation marker(s) of the context passage(s) that "
            "support it, e.g. [1] or [2][3]. Do not invent citations or facts. If "
            "the context does not answer the question, say so plainly.\n\n"
            f"QUESTION:\n{query}\n\n"
            f"CONTEXT:\n{context_block}\n\n"
            "ANSWER (markdown, with [n] citation markers):"
        )
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1},
        }
        base = self._settings.ollama_url.rstrip("/")
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{base}/api/generate",
                    json=payload,
                    timeout=self._settings.http_timeout_seconds,
                )
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.info("Ollama generate request failed (%s).", exc)
            return None

        text = data.get("response")
        if not isinstance(text, str) or not text.strip():
            logger.info("Ollama generate returned empty response.")
            return None

        answer_md = text.strip()
        valid_markers = {c.marker for c in citations}
        claims = self._claims_from_answer(answer_md, valid_markers)
        if not claims:
            # The model produced prose but no usable citations; fall back so we
            # never surface an uncitable answer.
            logger.info("LLM answer contained no valid citation markers.")
            return None
        return answer_md, claims

    @staticmethod
    def _claims_from_answer(
        answer_md: str, valid_markers: set[str]
    ) -> list[Claim]:
        """Split an LLM answer into claims, attaching the markers each contains."""
        claims: list[Claim] = []
        for raw in _SENTENCE_SPLIT_RE.split(answer_md):
            sentence = raw.strip().lstrip("-*").strip()
            if not sentence:
                continue
            markers = [f"[{m}]" for m in _MARKER_RE.findall(sentence)]
            markers = [m for m in markers if m in valid_markers]
            if not markers:
                continue
            # Strip the markers from the claim text so verification sees prose.
            claim_text = _MARKER_RE.sub("", sentence).strip()
            if not claim_text:
                continue
            claims.append(
                Claim(text=claim_text, citation_markers=sorted(set(markers)))
            )
        return claims

    # -- verification --------------------------------------------------------

    async def _verify_claims(
        self,
        claims: list[Claim],
        marker_to_chunk_id: dict[str, str],
        chunk_by_id: dict[str, Chunk],
    ) -> list[ClaimVerdict]:
        """Verify each claim against exactly the chunks its markers cite."""
        verdicts: list[ClaimVerdict] = []
        for claim in claims:
            cited_chunks: list[Chunk] = []
            for marker in claim.citation_markers:
                chunk_id = marker_to_chunk_id.get(marker)
                if chunk_id is None:
                    continue
                chunk = chunk_by_id.get(chunk_id)
                if chunk is not None:
                    cited_chunks.append(chunk)
            verdict = await self._verifier.verify(claim.text, cited_chunks)
            verdicts.append(verdict)
        return verdicts

    # -- citations -----------------------------------------------------------

    def _citations_for(self, context: list[RetrievedChunk]) -> list[Citation]:
        """Build ``[1..n]`` citations for the assembled context.

        Delegates to :func:`rag_core.citations.build_citations` (Track A),
        adapting to its exact signature; if that yields nothing usable, builds
        contract-compliant citations directly so the pipeline never emits an
        answer without provenance.
        """
        built = self._call_build_citations(context)
        if built:
            return built
        return self._fallback_citations(context)

    def _call_build_citations(
        self, context: list[RetrievedChunk]
    ) -> list[Citation]:
        """Invoke ``build_citations`` defensively across plausible signatures."""
        chunks = [rc.chunk for rc in context]
        candidate_args: tuple[tuple[Any, ...], ...] = (
            (context,),
            (chunks,),
        )
        for args in candidate_args:
            try:
                result = build_citations(*args)
            except TypeError:
                continue
            except Exception as exc:  # pragma: no cover - Track A dependent
                logger.warning("build_citations failed (%s); using fallback.", exc)
                return []
            if inspect.isawaitable(result):  # tolerate an async implementation
                logger.debug("build_citations returned awaitable; using fallback.")
                return []
            citations = self._coerce_citations(result)
            if citations:
                return citations
        return []

    @staticmethod
    def _coerce_citations(result: Any) -> list[Citation]:
        """Accept a list of :class:`Citation` (or dicts) from ``build_citations``."""
        if result is None:
            return []
        try:
            items = list(result)
        except TypeError:
            return []
        out: list[Citation] = []
        for item in items:
            if isinstance(item, Citation):
                out.append(item)
            elif isinstance(item, dict):
                try:
                    out.append(Citation(**item))
                except Exception:  # pragma: no cover - defensive
                    return []
            else:
                return []
        return out

    @staticmethod
    def _fallback_citations(context: list[RetrievedChunk]) -> list[Citation]:
        """Contract-compliant citations built directly from chunk provenance."""
        citations: list[Citation] = []
        for idx, rc in enumerate(context, start=1):
            chunk = rc.chunk
            snippet = chunk.text.strip()
            if len(snippet) > 280:
                snippet = snippet[:280].rstrip() + " …"
            citations.append(
                Citation(
                    marker=f"[{idx}]",
                    chunk_id=chunk.id,
                    source_type=chunk.source_type,
                    canonical_url=chunk.canonical_url,
                    path=chunk.path,
                    symbol=chunk.symbol,
                    start_line=chunk.start_line,
                    end_line=chunk.end_line,
                    version=chunk.version,
                    snippet=snippet,
                )
            )
        return citations

    # -- helpers -------------------------------------------------------------

    def _no_answer(
        self,
        query: str,
        domain: str,
        retrieved: list[RetrievedChunk],
        reason: str,
        started: float,
        *,
        claims: list[Claim] | None = None,
        citations: list[Citation] | None = None,
        verdicts: list[ClaimVerdict] | None = None,
    ) -> RagAnswer:
        logger.info("NO-ANSWER for query=%r domain=%s: %s", query, domain, reason)
        return RagAnswer(
            query=query,
            domain=domain,
            answered=False,
            answer_markdown=None,
            claims=claims or [],
            citations=citations or [],
            verdicts=verdicts or [],
            retrieved=retrieved,
            no_answer_reason=reason,
            used_embedder=self.used_embedder,
            used_vector_store=self.used_vector_store,
            latency_ms=self._elapsed_ms(started),
        )

    def _elapsed_ms(self, started: float) -> int:
        return max(0, int(round((self._clock() - started) * 1000.0)))

    @staticmethod
    def _salient_sentence(text: str) -> str:
        """First non-trivial sentence of ``text`` (extractive answer material)."""
        stripped = text.strip()
        if not stripped:
            return ""
        for sentence in _SENTENCE_SPLIT_RE.split(stripped):
            candidate = sentence.strip()
            if len(candidate) >= 12:
                return candidate if len(candidate) <= 400 else candidate[:400].rstrip() + " …"
        # No sentence boundary: return a bounded prefix of the whole text.
        one_line = " ".join(stripped.split())
        return one_line if len(one_line) <= 400 else one_line[:400].rstrip() + " …"

    @staticmethod
    def _format_context(
        context: list[RetrievedChunk], citations: list[Citation]
    ) -> str:
        """Render the assembled context as numbered, marker-tagged passages."""
        marker_by_chunk = {c.chunk_id: c.marker for c in citations}
        blocks: list[str] = []
        for rc in context:
            chunk = rc.chunk
            marker = marker_by_chunk.get(chunk.id, "")
            locus = chunk.path or chunk.canonical_url or chunk.source_id or "source"
            if chunk.symbol:
                locus = f"{locus}:{chunk.symbol}"
            body = chunk.text.strip()
            if len(body) > 1500:
                body = body[:1500].rstrip() + " …"
            blocks.append(f"{marker} ({locus})\n{body}")
        return "\n\n".join(blocks)


__all__ = ["RagPipeline"]
