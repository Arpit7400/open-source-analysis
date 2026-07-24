"""End-to-end pipeline tests (RAG_CONTRACT.md § *Tests*).

Drives the fully-wired-but-hermetic :class:`~rag_core.pipeline.RagPipeline`
(``pipeline`` fixture: HashEmbedder + Qdrant ``:memory:`` + lexical reranker +
extractive verifier, no Ollama) over a tiny indexed corpus and asserts:

* a relevant query yields ``answered=True`` with citations, claims, verdicts,
  and the degradation labels surfaced on the answer;
* an unrelated query yields ``answered=False`` (NO-ANSWER) with a reason;
* an unknown domain raises :class:`~rag_core.domains.UnknownDomainError`;
* ``collections()`` reports the six fixed collections with the embedder dim.
"""

from __future__ import annotations

import pytest

from rag_core.domains import DOMAINS, REPOSITORY_DOCS
from rag_core.models import Chunk
from rag_core.pipeline import RagPipeline


def _doc(cid: str, text: str, *, path: str, symbol: str | None = None) -> Chunk:
    return Chunk(
        id=cid,
        domain=REPOSITORY_DOCS,
        text=text,
        source_id="acme/repo",
        source_type="DOC",
        path=path,
        symbol=symbol,
    )


_CORPUS = [
    _doc(
        "fusion",
        "Reciprocal rank fusion combines dense vector retrieval and sparse BM25 "
        "retrieval, using the reciprocal rank fusion constant k equal to sixty.",
        path="rag/fusion.md",
        symbol="Fusion",
    ),
    _doc(
        "citations",
        "Every retrieved chunk carries exact provenance and every claim cites the "
        "chunks that support it; the verifier rejects unsupported claims.",
        path="rag/citations.md",
        symbol="Citations",
    ),
    _doc(
        "degrade",
        "The subsystem runs with no Docker and no Qdrant server by using the "
        "in-process local mode, and with no Ollama by using a hash embedder.",
        path="rag/degradation.md",
        symbol="Degradation",
    ),
]


async def _seed(pipeline: RagPipeline) -> None:
    summary = await pipeline.index_documents(REPOSITORY_DOCS, _CORPUS)
    assert summary["indexed_chunks"] == len(_CORPUS)
    assert summary["collections"] == {REPOSITORY_DOCS: len(_CORPUS)}


async def test_relevant_query_returns_cited_verified_answer(pipeline: RagPipeline) -> None:
    await _seed(pipeline)
    answer = await pipeline.answer(
        "How does reciprocal rank fusion combine dense and sparse retrieval?",
        REPOSITORY_DOCS,
    )

    assert answer.answered is True
    assert answer.answer_markdown
    assert answer.no_answer_reason is None
    assert answer.citations, "an answered response must carry citations"
    assert answer.claims, "an answered response must carry claims"
    # At least one verdict must be supported for answered=True.
    assert any(v.supported for v in answer.verdicts)
    # The top-cited chunk should be the planted fusion doc.
    top_retrieved = answer.retrieved[0]
    assert top_retrieved.chunk.id == "fusion"
    # Citation markers are sequential and provenance is carried through.
    assert answer.citations[0].marker == "[1]"
    assert answer.citations[0].path is not None
    # Degradation labels are surfaced (hermetic run => hash + local).
    assert answer.used_embedder == "hash-fallback"
    assert answer.used_vector_store == "qdrant:local"
    assert answer.latency_ms >= 0


async def test_unsupported_query_returns_no_answer(pipeline: RagPipeline) -> None:
    await _seed(pipeline)
    answer = await pipeline.answer(
        "photosynthesis chlorophyll mitochondria botany zoology",
        REPOSITORY_DOCS,
    )
    assert answer.answered is False
    assert answer.answer_markdown is None
    assert answer.no_answer_reason


async def test_empty_domain_yields_no_answer(pipeline: RagPipeline) -> None:
    # Nothing indexed into this domain -> no chunks retrieved -> NO-ANSWER.
    answer = await pipeline.answer("anything at all", "profile_evidence")
    assert answer.answered is False
    assert answer.no_answer_reason


async def test_unknown_domain_raises(pipeline: RagPipeline) -> None:
    from rag_core.domains import UnknownDomainError

    with pytest.raises(UnknownDomainError):
        await pipeline.answer("q", "not_a_real_domain")


async def test_collections_reports_six_fixed_domains(pipeline: RagPipeline) -> None:
    await _seed(pipeline)
    report = await pipeline.collections()
    names = [entry["name"] for entry in report["collections"]]
    assert names == list(DOMAINS)
    counts = {entry["name"]: entry["count"] for entry in report["collections"]}
    assert counts[REPOSITORY_DOCS] == len(_CORPUS)
    assert all(entry["dim"] == 768 for entry in report["collections"])
    assert report["embedder"] == "hash-fallback"
    assert report["store"] == "qdrant:local"
