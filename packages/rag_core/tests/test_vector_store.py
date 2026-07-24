"""Vector-store round-trip tests (RAG_CONTRACT.md § *Tests*).

Exercises :class:`~rag_core.vector_store.QdrantVectorStore` in in-process
``:memory:`` mode: collection creation, upsert, nearest-neighbour search with
full payload round-trip, count, and metadata filtering. Fully hermetic — no
Qdrant server, no Docker.
"""

from __future__ import annotations

import pytest

from rag_core.config import RagSettings
from rag_core.domains import REPOSITORY_CODE
from rag_core.embeddings import HashEmbedder
from rag_core.models import Chunk
from rag_core.vector_store import QdrantVectorStore


@pytest.fixture
def mem_store() -> QdrantVectorStore:
    return QdrantVectorStore(RagSettings(qdrant_url="", rag_qdrant_local_path=""))


def _chunk(idx: int, text: str, *, source_type: str = "CODE", path: str | None = None) -> Chunk:
    path = path if path is not None else f"pkg/mod_{idx}.py"
    return Chunk(
        id=Chunk.make_id(REPOSITORY_CODE, "acme/repo", path, idx, idx + 5),
        domain=REPOSITORY_CODE,
        text=text,
        source_id="acme/repo",
        source_type=source_type,
        path=path,
        symbol=f"symbol_{idx}",
        start_line=idx,
        end_line=idx + 5,
        language="python",
    )


async def test_memory_store_reports_local_mode(mem_store: QdrantVectorStore) -> None:
    assert mem_store.mode == "qdrant:local"


async def test_upsert_and_search_round_trip(mem_store: QdrantVectorStore) -> None:
    embedder = HashEmbedder()
    chunks = [
        _chunk(1, "reciprocal rank fusion combines dense and sparse rankings"),
        _chunk(2, "the hash embedder is deterministic and network free"),
        _chunk(3, "qdrant stores vectors with cosine distance"),
    ]
    vectors = await embedder.embed([c.text for c in chunks])

    await mem_store.ensure_collection(REPOSITORY_CODE, embedder.dim)
    written = await mem_store.upsert(REPOSITORY_CODE, chunks, vectors)
    assert written == 3
    assert await mem_store.count(REPOSITORY_CODE) == 3

    # Query with the exact vector of chunk 1 -> chunk 1 should rank first, and
    # its payload must round-trip losslessly.
    (query_vector,) = await embedder.embed(
        ["reciprocal rank fusion combines dense and sparse rankings"]
    )
    results = await mem_store.search(REPOSITORY_CODE, query_vector, limit=3)
    assert results, "expected at least one search result"
    top_chunk, top_score = results[0]
    assert top_chunk.id == chunks[0].id
    assert top_chunk.text == chunks[0].text
    assert top_chunk.symbol == "symbol_1"
    assert top_chunk.start_line == 1 and top_chunk.end_line == 6
    assert top_chunk.source_type == "CODE"
    assert top_score > 0.0


async def test_search_missing_collection_returns_empty(mem_store: QdrantVectorStore) -> None:
    assert await mem_store.count("repository_docs") == 0
    results = await mem_store.search("repository_docs", [0.0] * 768, limit=5)
    assert results == []


async def test_filter_by_source_type(mem_store: QdrantVectorStore) -> None:
    embedder = HashEmbedder()
    code_chunk = _chunk(1, "implementation code for the parser", source_type="CODE")
    test_chunk = _chunk(2, "implementation code for the parser", source_type="TEST")
    chunks = [code_chunk, test_chunk]
    vectors = await embedder.embed([c.text for c in chunks])

    await mem_store.ensure_collection(REPOSITORY_CODE, embedder.dim)
    await mem_store.upsert(REPOSITORY_CODE, chunks, vectors)

    (query_vector,) = await embedder.embed(["implementation code for the parser"])
    only_tests = await mem_store.search(
        REPOSITORY_CODE, query_vector, limit=5, flt={"source_type": "TEST"}
    )
    assert only_tests, "filter should still return the TEST chunk"
    assert all(chunk.source_type == "TEST" for chunk, _ in only_tests)
    assert {chunk.id for chunk, _ in only_tests} == {test_chunk.id}


async def test_upsert_is_idempotent_by_id(mem_store: QdrantVectorStore) -> None:
    embedder = HashEmbedder()
    chunk = _chunk(1, "idempotent upsert by stable id")
    (vector,) = await embedder.embed([chunk.text])

    await mem_store.ensure_collection(REPOSITORY_CODE, embedder.dim)
    await mem_store.upsert(REPOSITORY_CODE, [chunk], [vector])
    await mem_store.upsert(REPOSITORY_CODE, [chunk], [vector])  # same id again
    assert await mem_store.count(REPOSITORY_CODE) == 1
