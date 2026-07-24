"""Claim-verifier tests (RAG_CONTRACT.md § *Tests*).

The :class:`~rag_core.verifier.ClaimVerifier` extractive baseline is
deterministic and network-free. These tests force the extractive path
(``llm=False``) so no Ollama call is ever attempted, keeping them hermetic.

Covered:

* A claim whose content is grounded in the cited chunk is **supported**.
* A claim unsupported by the cited evidence is **rejected**.
* A claim with no cited chunks is rejected with a zero score.
"""

from __future__ import annotations

from rag_core.config import RagSettings
from rag_core.domains import REPOSITORY_DOCS
from rag_core.models import Chunk
from rag_core.verifier import ClaimVerifier


def _verifier() -> ClaimVerifier:
    # Empty rag_llm_model + llm=False guarantees the extractive baseline only.
    return ClaimVerifier(RagSettings(rag_llm_model="", qdrant_url=""), llm=False)


def _chunk(text: str) -> Chunk:
    return Chunk(id="c1", domain=REPOSITORY_DOCS, text=text, source_type="DOC", path="doc.md")


async def test_supported_claim_is_accepted() -> None:
    verifier = _verifier()
    evidence = _chunk(
        "Reciprocal rank fusion combines dense vector retrieval and sparse BM25 "
        "retrieval using the constant sixty."
    )
    verdict = await verifier.verify(
        "Reciprocal rank fusion combines dense and sparse retrieval.", [evidence]
    )
    assert verdict.supported is True
    assert verdict.support_score >= verifier.threshold
    assert verdict.cited_chunk_ids == ["c1"]


async def test_unsupported_claim_is_rejected() -> None:
    verifier = _verifier()
    evidence = _chunk(
        "Reciprocal rank fusion combines dense vector retrieval and sparse BM25 retrieval."
    )
    verdict = await verifier.verify(
        "The mitochondria is the powerhouse of the cell during photosynthesis.",
        [evidence],
    )
    assert verdict.supported is False
    assert verdict.support_score < verifier.threshold
    assert verdict.cited_chunk_ids == ["c1"]


async def test_claim_with_no_evidence_is_rejected() -> None:
    verifier = _verifier()
    verdict = await verifier.verify("Any claim at all.", [])
    assert verdict.supported is False
    assert verdict.support_score == 0.0
    assert verdict.cited_chunk_ids == []


async def test_verifier_accepts_retrieved_chunk_wrapper() -> None:
    from rag_core.models import RetrievedChunk

    verifier = _verifier()
    chunk = _chunk("hybrid retrieval reranking citations verification pipeline")
    wrapped = RetrievedChunk(chunk=chunk, fused_score=0.5, final_score=0.5)
    verdict = await verifier.verify(
        "The pipeline performs hybrid retrieval, reranking, and verification.",
        [wrapped],
    )
    assert verdict.cited_chunk_ids == ["c1"]
    assert verdict.supported is True
