# rag_core

The **real** RAG + code-indexing subsystem for **CareerForge AI** (handbook
Phases 2 & 4): genuine embeddings + vector search + AST code indexing + hybrid
retrieval + reranking + citations + claim verification. It replaces the
simulated retrieval with a fully working, local-first pipeline.

See [`../../docs/RAG_CONTRACT.md`](../../docs/RAG_CONTRACT.md) for the **fixed**
interfaces, core types, collection names, config keys, and pipeline order that
this package implements.

## What it is

A single coroutine — `RagPipeline.answer(query, domain, filters, top_k)` — runs
the contract pipeline **in exact order**:

```
QUERY -> (metadata/time/version filters)
      -> DENSE (embed + vector search) + SPARSE (BM25)
      -> RECIPROCAL RANK FUSION (k=60)
      -> RERANK (local reranker; fallback = lexical overlap)
      -> TIME/VERSION FILTER (drop stale unless the query asks history)
      -> CONTEXT ASSEMBLY (top_k, dedupe by symbol/path)
      -> CLAIM GENERATION w/ CITATIONS (LLM if available; else extractive)
      -> CLAIM-EVIDENCE VERIFICATION (per-claim support judgment)
      -> ANSWER or NO-ANSWER (confidence threshold)
```

It returns a fully-populated `RagAnswer` (query, `answered`, `answer_markdown`,
`claims`, `citations`, `verdicts`, `retrieved`, `no_answer_reason`, and the
`used_embedder` / `used_vector_store` degradation labels).

The six **fixed** retrieval domains (Qdrant collection names) are:
`profile_evidence`, `industry_sources`, `repository_code`, `repository_docs`,
`github_issues_prs`, `evaluation_memory`.

## Providers and fallbacks (every provider is swappable via config)

| Stage | Default provider | Fallback (graceful degradation) |
| --- | --- | --- |
| **Embeddings** | `OllamaEmbedder` (`nomic-embed-text`, 768-dim) | `HashEmbedder` — deterministic, network-free, 768-dim, used whenever Ollama is unreachable |
| **Vector store** | `QdrantVectorStore` against a reachable `CAREERFORGE_QDRANT_URL` server | in-process Qdrant: on-disk (`CAREERFORGE_RAG_QDRANT_LOCAL_PATH`) or `:memory:` — **no Docker / no server needed** |
| **Reranker** | `OllamaReranker` (when `CAREERFORGE_RAG_RERANK_MODEL` is set) | `LexicalReranker` — deterministic token-overlap + symbol/path boosts |
| **Sparse** | `BM25Index` (Okapi BM25, code-aware tokenization + exact-match boost) | always available (stdlib only) |
| **Claim gen** | Ollama `CAREERFORGE_RAG_LLM_MODEL` (low temperature) | extractive answer straight from top chunks |
| **Claim verify** | Ollama LLM judge (strict JSON) | extractive lexical-overlap baseline |

**Degradation is never silent.** Every fallback is logged, and the actually-used
providers are reported on `RagAnswer.used_embedder` / `RagAnswer.used_vector_store`
and surfaced in the API health endpoint (`services.rag` =
`"ollama+qdrant-local"` | `"hash+qdrant-local"` | `"ollama+qdrant-server"` |
`"down"`).

## Code-aware indexing

Python is parsed with the stdlib `ast` and chunked by **semantic unit**
(function / class / method / module-docstring) — never fixed token windows —
preserving `path`, `symbol`, `start_line`, `end_line`, `imports`, `language`, and
`commit`. Test code is tagged `source_type="TEST"` (via `test_*` / `tests/`
heuristics) vs `CODE`. Markdown/reST is chunked by heading section. Everything
else uses overlapping sentence windows.

## Configuration

All settings read the `CAREERFORGE_` environment prefix (see
[`rag_core/config.py`](rag_core/config.py)); field names map to env vars by
upper-casing and prefixing, so `rag_embed_model` → `CAREERFORGE_RAG_EMBED_MODEL`.

| Env var | Default | Purpose |
| --- | --- | --- |
| `CAREERFORGE_OLLAMA_URL` | `http://localhost:11434` | Ollama server (embeddings, optional LLM) |
| `CAREERFORGE_QDRANT_URL` | `http://localhost:6333` | Qdrant server; **falls back to local mode if unreachable** |
| `CAREERFORGE_RAG_EMBED_MODEL` | `nomic-embed-text` | embedding model |
| `CAREERFORGE_RAG_RERANK_MODEL` | `""` | reranker model (empty → lexical reranker) |
| `CAREERFORGE_RAG_QDRANT_LOCAL_PATH` | `""` | on-disk local Qdrant path (empty → `:memory:`) |
| `CAREERFORGE_RAG_MIN_SCORE` | `0.15` | NO-ANSWER confidence threshold |
| `CAREERFORGE_RAG_TOP_N` | `30` | per-retriever candidate pool |
| `CAREERFORGE_RAG_TOP_K` | `8` | final context size |
| `CAREERFORGE_RAG_LLM_MODEL` | `qwen2.5:7b` | claim generation/verification (optional) |

## Install

```bash
pip install -e ".[dev]"      # from packages/rag_core
```

The API app (`apps/api`) depends on this package; with `uv` it is resolved via
`[tool.uv.sources]`, and with plain pip you install it editable:
`pip install -e ../../packages/rag_core`.

## Running the tests (hermetic — no network, no Ollama, no Qdrant server)

```bash
pytest                        # from packages/rag_core
```

The suite is fully offline: it uses `HashEmbedder` + Qdrant `:memory:` + the
lexical reranker + the extractive verifier, wired by hand in `tests/conftest.py`
so no provider probing or network I/O ever happens. The only Ollama-touching
test (`test_ollama_embedder_live_dim`) is guarded by an availability probe and
**skips** when Ollama is down. Coverage:

- `test_chunking.py` — AST symbols, line ranges, imports, CODE/TEST detection, stable ids.
- `test_embeddings.py` — HashEmbedder determinism + 768-dim; Ollama fallback.
- `test_vector_store.py` — upsert/search/count/filter round-trip in `:memory:`.
- `test_retrieval.py` — RRF (k=60) ranking; planted chunk surfaces top; irrelevant query has no relevant chunk.
- `test_verifier.py` — supported claim accepted; unsupported claim rejected.
- `test_pipeline.py` — end-to-end cited+verified answer; unsupported query → `answered=False`.

## Pointing at real Ollama + Qdrant

The defaults already prefer real providers when they are reachable:

```bash
# 1) Ollama (embeddings + optional LLM). Pull the models once:
ollama pull nomic-embed-text
ollama pull qwen2.5:7b
export CAREERFORGE_OLLAMA_URL=http://localhost:11434
export CAREERFORGE_RAG_LLM_MODEL=qwen2.5:7b     # enables LLM claim gen + verify

# 2a) Persist locally with no server (embedded Qdrant on disk):
export CAREERFORGE_RAG_QDRANT_LOCAL_PATH=~/.careerforge/qdrant

# 2b) OR use a real Qdrant server (auto-detected if reachable):
export CAREERFORGE_QDRANT_URL=http://localhost:6333
```

With a reachable server the store reports `qdrant:server`; otherwise it uses the
on-disk path if set, else `:memory:`. With Ollama reachable the embedder reports
`ollama:nomic-embed-text`; otherwise it degrades to `hash-fallback`. In all
cases the pipeline runs — only the provider labels change.

## Usage

```python
from rag_core.pipeline import RagPipeline

pipeline = RagPipeline.build()                    # resolves providers local-first
await pipeline.index_repository("/path/to/repo", "owner/name", commit="abc123")
answer = await pipeline.answer(
    "Where is reciprocal rank fusion implemented?", "repository_code"
)
if answer.answered:
    print(answer.answer_markdown)
    for c in answer.citations:
        print(c.marker, c.path, c.symbol, f"{c.start_line}-{c.end_line}")
```
