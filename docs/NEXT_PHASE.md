# CareerForge AI — Next Phase (wiring real services)

> Concrete, ordered steps to replace each NOT-YET-WIRED component from
> [`IMPLEMENTATION_STATUS.md`](IMPLEMENTATION_STATUS.md) with a real implementation, while
> keeping the [`API_CONTRACT.md`](API_CONTRACT.md) shapes and the demo mode intact. The
> guiding constraint: **demo mode must keep working with just Python + Node** at every step
> (development rule #3). Each service is introduced behind `APP_ENV=local` so demo mode is
> never broken.

---

## 0. Ground rules for the transition

- Keep `APP_ENV=demo` as the default. New integrations activate only under `APP_ENV=local`
  (or a per-service flag), and each has a mock fallback so the demo never breaks.
- Every real integration must preserve the exact contract shapes and enum spellings. Add
  contract tests before wiring, so the real path is checked against the same expectations
  as the simulation.
- Bring services up incrementally with the optional `docker-compose.yml` (subset up, e.g.
  `docker compose up -d postgres qdrant redis`).
- Reflect each service's real availability in `GET /api/v1/system/health` (`up|down|mock`).

---

## 1. Ollama Model Gateway (Phase 1, Module A)

**Goal:** a single `ModelGateway` mediating all `chat()`, `embed()`, `structured()` calls.

1. Add a `careerforge_api/gateway/` package with a `ModelGateway` protocol and an
   `OllamaGateway` implementation (async `httpx` against `CAREERFORGE_OLLAMA_URL`).
2. Select the model from the detected hardware profile (`CPU_LOW` → small model;
   `WORKSTATION` → larger). Use `CAREERFORGE_OLLAMA_MODEL` / `CAREERFORGE_EMBEDDING_MODEL`.
3. Implement `structured()` via schema-constrained decoding (JSON schema / grammar) so agent
   outputs are typed.
4. Make it seedable for determinism (so eval + a "live" demo stay reproducible).
5. Report `ollama: "up"` in `/system/health` when reachable; keep `"mock"` in demo.
6. **Verify:** run Ollama natively (`ollama serve`, `ollama pull qwen2.5-coder:7b`), set
   `APP_ENV=local`, confirm a single agent step calls the gateway (traced, see §7).

---

## 2. Qdrant RAG (Phase 4, Module F)

**Goal:** real retrieval-augmented context for agents.

1. `docker compose up -d qdrant`. Add a `careerforge_api/rag/` package: chunker, embedder
   (via the Model Gateway), and a `QdrantStore` wrapper (async client on
   `CAREERFORGE_QDRANT_URL`).
2. Create per-corpus collections: `code`, `docs`, `evidence`, `pulse`. Store provenance and
   an untrusted-source flag on every chunk (see [`THREAT_MODEL.md`](THREAT_MODEL.md) T8).
3. Implement structural chunking (function/class/heading aware) and hybrid (dense + keyword)
   retrieval with per-agent scoping.
4. Wire retrieval into the static/fix agents so findings cite retrieved evidence with
   file/line provenance.
5. Report `qdrant: "up"` in health. **Verify:** index a small repo, confirm retrieval returns
   provenance-tagged chunks.

---

## 3. Real GitHub read-only client (Phase 9, Module D intake)

**Goal:** replace simulated intake with a real read-only clone/index — no writes.

1. Add `careerforge_api/github/` with a read-only client (REST + shallow clone). Use
   `CAREERFORGE_GITHUB_TOKEN` (**read-only scope only**); never request write scopes.
2. Enforce the staged permission model (`THREAT_MODEL.md` §2.3): stage 0 read-only is the
   only path enabled here. Draft submission stays gated behind human approval + the
   `github_writes` flag.
3. Apply intake safety limits (file size/count, symlink refusal) from `THREAT_MODEL.md` T1.
4. Keep the approval endpoint returning `github_write: false` until Phase "stage 3".
5. **Verify:** analyze a real public repo; confirm no write API is ever called (assert in a
   test that the write client is never constructed while `github_writes=false`).

---

## 4. Docker sandbox for untrusted execution (Phase 7, Module D runtime)

**Goal:** enable runtime reproduction safely behind `repository_execution=true`.

1. Add `careerforge_api/sandbox/` with a `DockerSandbox` runner. Container flags:
   `--network none`, `--cap-drop ALL`, `--security-opt no-new-privileges`, `--read-only`
   (+ small `tmpfs`), non-root user, CPU/memory/PID limits, and a wall-clock timeout.
2. Fresh, ephemeral container per reproduction; destroyed after; repo mounted read-only.
3. Gate strictly on `CAREERFORGE_FLAG_REPOSITORY_EXECUTION`; refuse to run if `false`.
4. Move reproduced findings from `PENDING`/`NOT_REPRODUCED` to `REPRODUCED` only on real
   sandbox evidence.
5. **Verify:** a network-exfiltration attempt inside the sandbox fails (no route out);
   resource-limit + timeout tests pass; with the flag off, the sandbox path is never taken.

---

## 5. LangGraph subgraphs — in-stage orchestration (Phase 10, Module E)

**Goal:** real cyclic multi-agent reasoning inside each stage.

1. Add `careerforge_api/agents/` with a LangGraph graph per stage (Static, Fix, Verify,
   …). Nodes call the Model Gateway (§1) and RAG (§2); a shared scratchpad holds in-stage
   state.
2. Keep verifier independence **structural**: verifier nodes are distinct from fix nodes and
   carry `verifier_of`. A fix node cannot mark its own candidate verified.
3. Emit the same contract-shaped events (`agent.update`, `edge.update`, `finding.new`,
   `candidate.update`, `log`) the simulator emits, so the UI is unchanged.
4. **Verify:** a golden mission's LangGraph run produces the same event *types/shapes* as the
   simulation; the seeded bad candidate is still `REJECTED` by the scope guard.

---

## 6. Temporal durable workflows — mission lifecycle (Phase 11, Module E)

**Goal:** durable, restart-surviving mission orchestration across stages, including the
human-approval wait.

1. `docker compose up -d temporal temporal-ui`. Add `careerforge_api/workflows/` with a
   Temporal `MissionWorkflow` sequencing the stages, each stage an activity that runs its
   LangGraph subgraph (§5).
2. Model the **human-approval wait** as a Temporal signal/timer so a mission can pause for
   hours/days and survive restarts. Authoritative `MissionStatus` transitions live here.
3. Persist the append-only event log to Postgres (§8) so SSE replay survives restarts.
4. **Verify:** kill and restart the worker mid-mission; the mission resumes and the SSE
   `Last-Event-ID` replay is intact.

---

## 7. Observability — Langfuse, Prometheus, Grafana (Phase 13, Module H)

1. `docker compose up -d langfuse prometheus grafana`. Trace every Model Gateway call to
   Langfuse (prompt, tools, tokens, latency, cost, mission/agent ids).
2. Expose a Prometheus metrics endpoint on the API (request latency, active agents, mission
   throughput, sandbox usage) and add a scrape config.
3. Import Grafana dashboards over the Prometheus data source.
4. **Verify:** a live mission shows spans in Langfuse and moving series in Grafana.

---

## 8. PostgreSQL persistence (supporting, Module G)

1. `docker compose up -d postgres`. Add async SQLAlchemy models for the tables in
   [`MASTER_SPEC.md` §10](MASTER_SPEC.md), plus Alembic migrations.
2. Swap the in-memory mission store for a Postgres-backed store with the **same surface**
   (`create/exists/append/events_since/snapshot/...`) so `main.py` is unchanged.
3. Keep the in-memory store as the demo-mode implementation.
4. **Verify:** the 21 existing tests still pass against the in-memory store; a new suite
   runs them against Postgres under `APP_ENV=local`.

---

## Suggested order

```
1 Model Gateway  →  8 Postgres  →  2 Qdrant RAG  →  5 LangGraph  →
9(§3) GitHub RO  →  7(§4) Sandbox  →  6 Temporal  →  §7 Observability
```

Model Gateway and Postgres first (everything depends on them); the untrusted-execution
sandbox before enabling any real runtime reproduction; Temporal once stages are real so it
has something durable to orchestrate. At each step, run `python -m pytest apps/api/tests`
and confirm `APP_ENV=demo` still boots with just Python + Node.
