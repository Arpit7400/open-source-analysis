"""rag_core — the real RAG + code-indexing subsystem for CareerForge AI.

Public surface (per ``docs/RAG_CONTRACT.md``):

Types
    :class:`Chunk`, :class:`RetrievedChunk`, :class:`Citation`, :class:`Claim`,
    :class:`ClaimVerdict`, :class:`RagAnswer`.
Config
    :class:`RagSettings`, :func:`get_rag_settings`.
Embedders
    :class:`Embedder`, :class:`OllamaEmbedder`, :class:`HashEmbedder`,
    :func:`get_embedder`.
Pipeline & providers (owned by other tracks)
    :class:`RagPipeline` plus provider classes are imported **lazily** via
    :pep:`562` module ``__getattr__`` so that importing :mod:`rag_core` never
    fails or forms an import cycle if a downstream module is mid-build. They
    still appear in :data:`__all__` and resolve on first attribute access.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

# Eagerly export the foundation surface owned by this track — these modules
# have no cross-track dependencies and are always importable.
from rag_core.config import RagSettings, get_rag_settings
from rag_core.embeddings import (
    Embedder,
    HashEmbedder,
    OllamaEmbedder,
    get_embedder,
)
from rag_core.models import (
    Chunk,
    Citation,
    Claim,
    ClaimVerdict,
    RagAnswer,
    RetrievedChunk,
)

if TYPE_CHECKING:  # import only for type checkers; avoids runtime cycles
    from rag_core.pipeline import RagPipeline as RagPipeline

# Map of lazily-resolved public names → (module, attribute). These belong to
# other tracks; resolving them lazily keeps ``import rag_core`` cheap and
# cycle-free while still exposing them on the package.
_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "RagPipeline": ("rag_core.pipeline", "RagPipeline"),
    "VectorStore": ("rag_core.vector_store", "VectorStore"),
    "QdrantVectorStore": ("rag_core.vector_store", "QdrantVectorStore"),
    "Reranker": ("rag_core.rerank", "Reranker"),
    "LexicalReranker": ("rag_core.rerank", "LexicalReranker"),
    "HybridRetriever": ("rag_core.retrieval", "HybridRetriever"),
    "RepositoryIndexer": ("rag_core.indexer", "RepositoryIndexer"),
    "ClaimVerifier": ("rag_core.verifier", "ClaimVerifier"),
    "BM25Index": ("rag_core.bm25", "BM25Index"),
    "PythonAstChunker": ("rag_core.chunking", "PythonAstChunker"),
    "TextChunker": ("rag_core.chunking", "TextChunker"),
}


def __getattr__(name: str) -> Any:
    """Lazily import cross-track members on first access (:pep:`562`)."""
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = target
    from importlib import import_module

    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value  # cache so subsequent access is direct
    return value


def __dir__() -> list[str]:
    """Include lazily-exported names in ``dir(rag_core)``."""
    return sorted(set(globals()) | set(_LAZY_EXPORTS))


__all__ = [
    # Config
    "RagSettings",
    "get_rag_settings",
    # Embedders
    "Embedder",
    "OllamaEmbedder",
    "HashEmbedder",
    "get_embedder",
    # Core types
    "Chunk",
    "RetrievedChunk",
    "Citation",
    "Claim",
    "ClaimVerdict",
    "RagAnswer",
    # Pipeline & providers (lazy; owned by other tracks)
    "RagPipeline",
    "VectorStore",
    "QdrantVectorStore",
    "Reranker",
    "LexicalReranker",
    "HybridRetriever",
    "RepositoryIndexer",
    "ClaimVerifier",
    "BM25Index",
    "PythonAstChunker",
    "TextChunker",
]
