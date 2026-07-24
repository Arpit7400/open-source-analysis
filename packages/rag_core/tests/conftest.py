"""Shared, fully-hermetic fixtures for the ``rag_core`` test suite.

These fixtures wire every collaborator by hand from the deterministic
:class:`~rag_core.embeddings.HashEmbedder` and an in-process Qdrant ``:memory:``
store, bypassing the provider-probing in :meth:`RagPipeline.build`. That keeps
the whole suite offline and reproducible on any machine with no Ollama, no
Qdrant server, and no Docker (RAG_CONTRACT.md § *Tests*).

Key choices for hermeticity:

* ``rag_qdrant_local_path=""`` and an unreachable ``qdrant_url`` scheme so the
  store selects ``:memory:`` without a network probe.
* ``rag_llm_model=""`` so neither claim generation nor verification ever calls
  Ollama — the pipeline uses the extractive answerer and the extractive
  verifier baseline, both deterministic.
"""

from __future__ import annotations

import pytest

from rag_core.config import RagSettings
from rag_core.embeddings import HashEmbedder
from rag_core.indexer import RepositoryIndexer
from rag_core.pipeline import RagPipeline
from rag_core.rerank import LexicalReranker
from rag_core.retrieval import HybridRetriever
from rag_core.vector_store import QdrantVectorStore
from rag_core.verifier import ClaimVerifier


@pytest.fixture
def settings() -> RagSettings:
    """RagSettings forcing hash embedder + in-memory Qdrant + no LLM.

    ``qdrant_url`` is set to an empty string so the store never probes a server
    and falls straight through to ``:memory:``; ``rag_llm_model`` is empty so no
    Ollama call is ever attempted for generation or verification.
    """
    return RagSettings(
        ollama_url="http://127.0.0.1:0",  # unused: no embedder/LLM calls network
        qdrant_url="",  # empty -> skip server, no probe
        rag_qdrant_local_path="",  # empty -> :memory:
        rag_embed_model="nomic-embed-text",
        rag_rerank_model="",  # empty -> lexical reranker
        rag_llm_model="",  # empty -> extractive gen + extractive verify
        rag_min_score=0.0001,  # tiny: RRF scores are ~1/61, keep genuine hits
        rag_top_n=30,
        rag_top_k=8,
    )


@pytest.fixture
def embedder() -> HashEmbedder:
    """A deterministic, network-free 768-dim hash embedder."""
    return HashEmbedder()


@pytest.fixture
def store(settings: RagSettings) -> QdrantVectorStore:
    """An in-process Qdrant ``:memory:`` vector store."""
    return QdrantVectorStore(settings)


@pytest.fixture
def retriever(
    embedder: HashEmbedder,
    store: QdrantVectorStore,
    settings: RagSettings,
) -> HybridRetriever:
    """A hybrid retriever with a lexical reranker (no model, no network)."""
    return HybridRetriever(
        embedder, store, settings, reranker=LexicalReranker()
    )


@pytest.fixture
def pipeline(
    settings: RagSettings,
    embedder: HashEmbedder,
    store: QdrantVectorStore,
    retriever: HybridRetriever,
) -> RagPipeline:
    """A fully-wired, hermetic :class:`RagPipeline` (no probing, no network)."""
    reranker = LexicalReranker()
    verifier = ClaimVerifier(settings, llm=False)
    indexer = RepositoryIndexer(embedder, store, retriever, settings)
    return RagPipeline(
        settings=settings,
        embedder=embedder,
        vector_store=store,
        retriever=retriever,
        reranker=reranker,
        verifier=verifier,
        indexer=indexer,
    )
