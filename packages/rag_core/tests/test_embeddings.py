"""Embedder tests (RAG_CONTRACT.md § *Tests*).

* :class:`~rag_core.embeddings.HashEmbedder` is deterministic and correct-dim.
* :class:`~rag_core.embeddings.OllamaEmbedder` is exercised only behind an
  availability probe that **skips** when Ollama is down — the default in CI and
  on any machine without a running server, keeping the suite hermetic.
"""

from __future__ import annotations

import math

import httpx
import pytest

from rag_core.config import RagSettings
from rag_core.embeddings import (
    DEFAULT_DIM,
    HASH_FALLBACK_NAME,
    HashEmbedder,
    OllamaEmbedder,
    get_embedder,
)


async def test_hash_embedder_dim_and_name() -> None:
    embedder = HashEmbedder()
    assert embedder.dim == DEFAULT_DIM == 768
    assert embedder.name == HASH_FALLBACK_NAME
    vectors = await embedder.embed(["hello world"])
    assert len(vectors) == 1
    assert len(vectors[0]) == DEFAULT_DIM


async def test_hash_embedder_is_deterministic() -> None:
    a = HashEmbedder()
    b = HashEmbedder()
    va = await a.embed(["retrieval augmented generation", "second text"])
    vb = await b.embed(["retrieval augmented generation", "second text"])
    assert va == vb  # identical inputs -> identical vectors, across instances


async def test_hash_embedder_vectors_are_l2_normalised() -> None:
    embedder = HashEmbedder()
    (vector,) = await embedder.embed(["vector store cosine distance"])
    norm = math.sqrt(sum(component * component for component in vector))
    # Non-empty text yields a unit vector (empty-text edge case would be 0).
    assert math.isclose(norm, 1.0, rel_tol=1e-9, abs_tol=1e-9)


async def test_hash_embedder_distinct_texts_differ() -> None:
    embedder = HashEmbedder()
    v1, v2 = await embedder.embed(["alpha beta gamma", "completely different words"])
    assert v1 != v2


async def test_get_embedder_falls_back_to_hash_when_ollama_down() -> None:
    # Point at a definitely-unreachable local port so the probe fails fast and
    # the factory degrades to the hash embedder (no network egress).
    settings = RagSettings(ollama_url="http://127.0.0.1:0", qdrant_url="")
    embedder = get_embedder(settings)
    assert embedder.name == HASH_FALLBACK_NAME
    assert embedder.dim == DEFAULT_DIM


def _ollama_available(base_url: str = "http://localhost:11434") -> bool:
    try:
        resp = httpx.get(f"{base_url.rstrip('/')}/api/tags", timeout=1.0)
        resp.raise_for_status()
    except Exception:
        return False
    return True


@pytest.mark.skipif(
    not _ollama_available(), reason="Ollama not reachable; skipping live embedding test."
)
async def test_ollama_embedder_live_dim() -> None:  # pragma: no cover - env dependent
    embedder = OllamaEmbedder(model="nomic-embed-text", base_url="http://localhost:11434")
    (vector,) = await embedder.embed(["hello"])
    assert len(vector) == embedder.dim
    assert embedder.name == "ollama:nomic-embed-text"
