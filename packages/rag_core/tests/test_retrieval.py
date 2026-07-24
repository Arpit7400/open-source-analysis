"""Hybrid-retrieval tests (RAG_CONTRACT.md § *Retrieval pipeline* / § *Tests*).

Covers:

* Reciprocal Rank Fusion (``k=60``) fuses dense + sparse rankings and ranks a
  chunk appearing high in both above chunks appearing in only one.
* End-to-end :meth:`HybridRetriever.retrieve` over a tiny indexed corpus surfaces
  a planted relevant chunk at the top.
* An irrelevant query returns no lexically-relevant chunk (final scores drop to
  zero under the lexical reranker), so the pipeline can NO-ANSWER on it.

Hermetic: :class:`HashEmbedder` + Qdrant ``:memory:`` + lexical reranker.
"""

from __future__ import annotations

from rag_core.domains import REPOSITORY_DOCS
from rag_core.models import Chunk, RetrievedChunk
from rag_core.retrieval import HybridRetriever


def _doc(cid: str, text: str, *, path: str) -> Chunk:
    return Chunk(id=cid, domain=REPOSITORY_DOCS, text=text, source_type="DOC", path=path)


def test_rrf_ranks_chunk_present_in_both_rankings_first(
    retriever: HybridRetriever,
) -> None:
    a = _doc("a", "alpha", path="a.md")
    b = _doc("b", "beta", path="b.md")
    c = _doc("c", "gamma", path="c.md")

    # ``b`` is rank-1 dense and rank-1 sparse; ``a`` and ``c`` each appear in only
    # one list. RRF (score = Σ 1/(k+rank)) must put ``b`` on top.
    dense = [(b, 0.9), (a, 0.8)]
    sparse = [(b, 3.2), (c, 1.1)]

    fused = retriever._reciprocal_rank_fusion(dense, sparse)
    by_id = {rc.chunk.id: rc for rc in fused}

    assert fused[0].chunk.id == "b"
    # b: 1/(60+1) + 1/(60+1); a: 1/(60+2); c: 1/(60+2)
    assert by_id["b"].fused_score > by_id["a"].fused_score
    assert by_id["b"].fused_score > by_id["c"].fused_score
    # Raw per-retriever scores are preserved for transparency.
    assert by_id["b"].dense_score == 0.9
    assert by_id["b"].sparse_score == 3.2


def test_rrf_uses_k_of_60(retriever: HybridRetriever) -> None:
    a = _doc("a", "alpha", path="a.md")
    fused = retriever._reciprocal_rank_fusion([(a, 1.0)], [])
    # A single rank-1 dense contribution is exactly 1/(60+1).
    assert abs(fused[0].fused_score - 1.0 / 61.0) < 1e-12


async def test_retrieve_surfaces_planted_relevant_chunk_top(
    embedder,
    store,
    retriever: HybridRetriever,
) -> None:
    planted = _doc(
        "planted",
        "Reciprocal rank fusion combines dense vector search with sparse BM25 "
        "retrieval using the constant k equal to sixty.",
        path="rag/fusion.md",
    )
    distractors = [
        _doc("d1", "The user profile brain tracks verified skills over time.", path="profile.md"),
        _doc("d2", "Industry pulse ranks arXiv papers by momentum and relevance.", path="pulse.md"),
        _doc("d3", "The approval gate keeps a human in the loop before any write.", path="approval.md"),
    ]
    corpus = [planted, *distractors]

    vectors = await embedder.embed([c.text for c in corpus])
    await store.ensure_collection(REPOSITORY_DOCS, embedder.dim)
    await store.upsert(REPOSITORY_DOCS, corpus, vectors)
    retriever.register_chunks(REPOSITORY_DOCS, corpus)

    results = await retriever.retrieve(
        "How does reciprocal rank fusion combine dense and sparse retrieval?",
        REPOSITORY_DOCS,
    )
    assert results, "expected retrieval to return chunks"
    assert results[0].chunk.id == "planted"
    assert results[0].final_score > 0.0


async def test_irrelevant_query_has_no_relevant_chunk(
    embedder,
    store,
    retriever: HybridRetriever,
) -> None:
    corpus = [
        _doc("planted", "Reciprocal rank fusion combines dense and sparse rankings.", path="rag/fusion.md"),
        _doc("d1", "The approval gate keeps a human in the loop.", path="approval.md"),
    ]
    vectors = await embedder.embed([c.text for c in corpus])
    await store.ensure_collection(REPOSITORY_DOCS, embedder.dim)
    await store.upsert(REPOSITORY_DOCS, corpus, vectors)
    retriever.register_chunks(REPOSITORY_DOCS, corpus)

    results = await retriever.retrieve(
        "photosynthesis chlorophyll mitochondria botany",
        REPOSITORY_DOCS,
    )
    # The lexical reranker scores every unrelated chunk 0.0, so the best final
    # score is 0.0 — which the pipeline treats as a NO-ANSWER.
    top = max((rc.final_score for rc in results), default=0.0)
    assert top == 0.0


def test_dedupe_keeps_best_by_path_symbol(retriever: HybridRetriever) -> None:
    same = _doc("x1", "first", path="dup.md")
    same_again = Chunk(
        id="x2", domain=REPOSITORY_DOCS, text="second", source_type="DOC", path="dup.md"
    )
    ranked = [
        RetrievedChunk(chunk=same, fused_score=0.5, final_score=0.5),
        RetrievedChunk(chunk=same_again, fused_score=0.4, final_score=0.4),
    ]
    deduped = retriever._dedupe(ranked)
    # Both share (path=dup.md, symbol=None); the first (best) survives.
    assert len(deduped) == 1
    assert deduped[0].chunk.id == "x1"
