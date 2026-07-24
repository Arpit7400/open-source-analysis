"""Core Pydantic v2 types for the RAG subsystem.

Every model here mirrors ``docs/RAG_CONTRACT.md`` § *Core types* **exactly**:
field names, types, and defaults are load-bearing and must not drift. This
module is imported by embedders, the vector store, the retriever, the verifier,
the pipeline, and the API layer, so the names defined here are canonical.

Conventions:

* Pydantic v2 (:class:`~pydantic.BaseModel`, ``model_config`` via
  :class:`~pydantic.ConfigDict`).
* Provenance fields on :class:`Chunk` are optional but populated where known.
* :meth:`Chunk.make_id` derives a **stable** id from provenance so re-indexing
  the same span produces the same id (idempotent upserts).
"""

from __future__ import annotations

import hashlib

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    """Shared base config: ignore additive fields, allow population by name."""

    model_config = ConfigDict(
        extra="ignore",
        populate_by_name=True,
        use_enum_values=False,
    )


class Chunk(_Base):
    """A single indexed unit of content with full provenance.

    The :attr:`id` is derived deterministically from
    ``(domain, source_id, path, start_line, end_line)`` via :meth:`make_id` so
    that re-indexing an unchanged span is idempotent.
    """

    id: str
    domain: str
    text: str

    # --- provenance (all optional but populated where known) ---------------
    source_id: str | None = None
    source_type: str | None = None  # CODE | DOC | ISSUE | PR | PAPER | EVIDENCE | RELEASE | TEST ...
    canonical_url: str | None = None
    path: str | None = None
    symbol: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    language: str | None = None
    commit: str | None = None
    version: str | None = None
    published_at: str | None = None  # ISO-8601, for time/version filtering
    imports: list[str] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)

    @classmethod
    def make_id(
        cls,
        domain: str,
        source_id: str | None,
        path: str | None,
        start: int | None,
        end: int | None,
    ) -> str:
        """Return a stable ``sha1`` id for a chunk's provenance.

        Contract: ``sha1(domain|source_id|path|start|end)``. ``None`` components
        serialise to an empty string so the derivation is total and stable
        across runs and platforms.
        """
        parts = [
            domain,
            source_id or "",
            path or "",
            "" if start is None else str(start),
            "" if end is None else str(end),
        ]
        raw = "|".join(parts)
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()


class RetrievedChunk(_Base):
    """A chunk carried through the hybrid-retrieval pipeline with its scores.

    Scores are populated progressively: ``dense_score``/``sparse_score`` from
    the two retrievers, ``fused_score`` after RRF, ``rerank_score`` after the
    reranker, and ``final_score`` as the score the pipeline ranks/thresholds on.
    """

    chunk: Chunk
    dense_score: float | None = None
    sparse_score: float | None = None
    fused_score: float
    rerank_score: float | None = None
    final_score: float


class Citation(_Base):
    """Exact provenance for a passage the answer relies on."""

    marker: str  # "[1]", "[2]", ...
    chunk_id: str
    source_type: str | None = None
    canonical_url: str | None = None
    path: str | None = None
    symbol: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    version: str | None = None
    snippet: str  # short supporting passage


class Claim(_Base):
    """A single asserted statement in the answer and the citations backing it."""

    text: str
    citation_markers: list[str] = Field(default_factory=list)


class ClaimVerdict(_Base):
    """The verifier's per-claim support judgment."""

    claim: str
    supported: bool
    support_score: float  # 0..1
    reason: str
    cited_chunk_ids: list[str] = Field(default_factory=list)


class RagAnswer(_Base):
    """The full result of :meth:`rag_core.pipeline.RagPipeline.answer`.

    ``answered=False`` denotes a NO-ANSWER (below the confidence threshold or no
    supported claim). ``used_embedder`` / ``used_vector_store`` surface which
    providers actually served the request so degradation is never silent.
    """

    query: str
    domain: str
    answered: bool  # False => NO-ANSWER (below confidence threshold)
    answer_markdown: str | None = None
    claims: list[Claim] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    verdicts: list[ClaimVerdict] = Field(default_factory=list)
    retrieved: list[RetrievedChunk] = Field(default_factory=list)
    no_answer_reason: str | None = None
    used_embedder: str  # "ollama:nomic-embed-text" | "hash-fallback"
    used_vector_store: str  # "qdrant:server" | "qdrant:local"
    latency_ms: int


__all__ = [
    "Chunk",
    "Citation",
    "Claim",
    "ClaimVerdict",
    "RagAnswer",
    "RetrievedChunk",
]
