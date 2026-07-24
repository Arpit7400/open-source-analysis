# CareerForge AI — RAG + Code-Indexing Contract (Phases 2 & 4)

> **Single source of truth** for the real RAG subsystem. Every agent building
> `packages/rag_core` or wiring it into `apps/api` MUST honor these interfaces exactly.
> This replaces the *simulated* retrieval with **real** embeddings + vector search +
> AST code indexing + hybrid retrieval + reranking + citations + claim verification.

## Guiding principles (from handbook §5, §6, dev-rules)

- **Local-first & replaceable.** Every provider (embedder, vector store, reranker, LLM) is
  swappable via config. Ollama is default; nothing is hard-coded.
- **Graceful degradation.** The subsystem MUST run on a machine with **no Docker and no
  running Qdrant server** by using `qdrant-client` **local/in-process mode**, and MUST run
  with **no Ollama** by falling back to a deterministic hash embedder. Degradation is
  logged, never silent, and surfaced in `/system/health`.
- **Deterministic tools first.** AST parsing (stdlib `ast`), BM25, RRF are deterministic.
  LLM is used only for the optional claim-support judgment (low temperature).
- **Citations are mandatory.** Every retrieved chunk carries exact provenance; every claim
  cites chunks; the verifier rejects unsupported claims.

## Package layout

```
packages/rag_core/
  rag_core/
    __init__.py
    config.py          # RagSettings (reads CAREERFORGE_* env; reuses ollama_url/qdrant_url)
    embeddings.py      # Embedder protocol + OllamaEmbedder + HashEmbedder (fallback)
    vector_store.py    # VectorStore protocol + QdrantVectorStore (server OR local mode)
    chunking.py        # PythonAstChunker + TextChunker + doc-section chunker
    indexer.py         # RepositoryIndexer (walk repo -> chunks -> embed -> upsert)
    bm25.py            # in-memory BM25 sparse index (deterministic)
    retrieval.py       # HybridRetriever: dense + sparse -> RRF -> rerank -> filters
    rerank.py          # Reranker protocol + CrossEncoder-ish local reranker + LexicalReranker fallback
    citations.py       # Citation building from chunk provenance
    verifier.py        # ClaimVerifier: does retrieved context support the claim?
    pipeline.py        # RagPipeline.answer(query, domain, filters) -> RagAnswer
    domains.py         # the 6 collection/domain definitions + metadata schemas
  tests/
    test_chunking.py test_embeddings.py test_retrieval.py test_pipeline.py test_verifier.py
  pyproject.toml
```

## Retrieval domains (handbook §5.1) — collection names are FIXED

```
profile_evidence   industry_sources   repository_code
repository_docs    github_issues_prs  evaluation_memory
```

## Core types (Pydantic v2)

```python
class Chunk(BaseModel):
    id: str                      # stable: sha1(domain|source_id|path|start|end)
    domain: str                  # one of the 6 collections
    text: str
    # provenance (all optional but populated where known):
    source_id: str | None        # repo "owner/name", url, or evidence id
    source_type: str | None      # CODE | DOC | ISSUE | PR | PAPER | EVIDENCE | RELEASE ...
    canonical_url: str | None
    path: str | None             # file path for code/docs
    symbol: str | None           # function/class/method name (code)
    start_line: int | None
    end_line: int | None
    language: str | None
    commit: str | None
    version: str | None
    published_at: str | None     # ISO-8601, for time/version filtering
    imports: list[str] = []      # code: imported modules
    metadata: dict[str, str] = {}

class RetrievedChunk(BaseModel):
    chunk: Chunk
    dense_score: float | None
    sparse_score: float | None
    fused_score: float          # after RRF
    rerank_score: float | None
    final_score: float

class Citation(BaseModel):
    marker: str                  # "[1]", "[2]", ...
    chunk_id: str
    source_type: str | None
    canonical_url: str | None
    path: str | None
    symbol: str | None
    start_line: int | None
    end_line: int | None
    version: str | None
    snippet: str                 # short supporting passage

class Claim(BaseModel):
    text: str
    citation_markers: list[str]  # which citations support it

class ClaimVerdict(BaseModel):
    claim: str
    supported: bool
    support_score: float         # 0..1
    reason: str
    cited_chunk_ids: list[str]

class RagAnswer(BaseModel):
    query: str
    domain: str
    answered: bool               # False => NO-ANSWER (below confidence threshold)
    answer_markdown: str | None
    claims: list[Claim]
    citations: list[Citation]
    verdicts: list[ClaimVerdict]
    retrieved: list[RetrievedChunk]
    no_answer_reason: str | None
    used_embedder: str           # "ollama:nomic-embed-text" | "hash-fallback"
    used_vector_store: str       # "qdrant:server" | "qdrant:local"
    latency_ms: int
```

## Protocols (all providers swappable)

```python
class Embedder(Protocol):
    name: str
    dim: int
    async def embed(self, texts: list[str]) -> list[list[float]]: ...

class VectorStore(Protocol):
    async def ensure_collection(self, name: str, dim: int) -> None: ...
    async def upsert(self, name: str, chunks: list[Chunk], vectors: list[list[float]]) -> int: ...
    async def search(self, name: str, vector: list[float], limit: int,
                     flt: dict | None = None) -> list[tuple[Chunk, float]]: ...
    async def count(self, name: str) -> int: ...

class Reranker(Protocol):
    async def rerank(self, query: str, chunks: list[Chunk]) -> list[float]: ...
```

## Retrieval pipeline (handbook §5.2) — exact order

```
QUERY -> (permission + metadata/time/version filters)
      -> DENSE (embed query, vector search top N) + SPARSE (BM25 top N)
      -> RECIPROCAL RANK FUSION (k=60)
      -> RERANK (local reranker; fallback = lexical overlap)
      -> TIME/VERSION FILTER (drop stale unless query asks history)
      -> CONTEXT ASSEMBLY (top K, dedupe by symbol/path)
      -> CLAIM GENERATION w/ CITATIONS (LLM if available; else extractive)
      -> CLAIM-EVIDENCE VERIFICATION (per-claim support judgment)
      -> ANSWER or NO-ANSWER (confidence threshold)
```

RRF: `score = Σ 1/(k + rank_i)` across dense & sparse rankings, `k=60`.
NO-ANSWER when top fused/rerank score < `RAG_MIN_SCORE` (default 0.15) or verifier finds no supported claim.

## Code-aware indexing (handbook §5.3)

- Parse Python with stdlib `ast` (Tree-sitter optional, guarded import).
- Chunk by **function / class / method / module-docstring / doc-section** — never fixed token windows.
- Preserve path, line range, symbol, imports, language, commit.
- Index implementation and test code with `source_type` = `CODE` vs `TEST`; link tests to
  symbols they likely cover (name heuristic `test_<symbol>` / references).
- Markdown/docs chunked by heading section.

## New API surface (extends API_CONTRACT.md)

```
POST /api/v1/rag/query
  req:  { "query": str, "domain": str, "filters"?: {..}, "top_k"?: int }
  res:  RagAnswer

POST /api/v1/rag/index/repository
  req:  { "repo_path": str, "repo_id": str, "commit"?: str }   # local path (no clone yet in P2/P4)
  res:  { "indexed_chunks": int, "collections": {domain: count}, "embedder": str, "store": str }

GET  /api/v1/rag/collections
  res:  { "collections": [ { "name": str, "count": int, "dim": int } ], "embedder": str, "store": str }
```

`/system/health` gains: `services.rag = "ollama+qdrant-local" | "hash+qdrant-local" | "ollama+qdrant-server" | "down"`.

## Config (env, `CAREERFORGE_` prefix; reuse existing where present)

```
CAREERFORGE_OLLAMA_URL           (exists) default http://localhost:11434
CAREERFORGE_QDRANT_URL           (exists) default http://localhost:6333  # if unreachable -> local mode
CAREERFORGE_RAG_EMBED_MODEL      default "nomic-embed-text"
CAREERFORGE_RAG_RERANK_MODEL     default ""  (empty -> lexical reranker)
CAREERFORGE_RAG_QDRANT_LOCAL_PATH default ""  (empty -> :memory:; else on-disk local Qdrant)
CAREERFORGE_RAG_MIN_SCORE        default 0.15
CAREERFORGE_RAG_TOP_N            default 30   (per-retriever pool)
CAREERFORGE_RAG_TOP_K            default 8    (final context)
CAREERFORGE_RAG_LLM_MODEL        default "qwen2.5:7b"  (for claim gen/verify; optional)
```

## Tests (must pass with NO server, NO Ollama — use HashEmbedder + Qdrant local)

- Chunking: a known Python file yields expected function/class chunks with correct line ranges & symbols.
- Embeddings: HashEmbedder is deterministic & correct-dim; OllamaEmbedder guarded/skipped if unreachable.
- Vector store: upsert+search round-trips in local mode; filters work.
- Retrieval: RRF fuses dense+sparse; a planted relevant chunk ranks top; irrelevant query -> NO-ANSWER.
- Pipeline: end-to-end query over a tiny indexed corpus returns a cited, verified answer; unsupported query -> answered=False.
- Verifier: a claim not supported by context is rejected.

Tests must be **hermetic** (no network): default to `HashEmbedder` + Qdrant `:memory:`; only exercise Ollama behind an availability check that skips when down.
