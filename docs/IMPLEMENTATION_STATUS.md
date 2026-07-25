# CareerForge AI — Implementation Status

> **An honest map of what actually exists in this repository.** Development rule #19:
> clearly document what is REAL vs SIMULATED vs NOT-YET-WIRED. This slice is the *flagship
> vertical slice* of the product described in [`MASTER_SPEC.md`](MASTER_SPEC.md), not the
> full product.

---

## 1. What the slice is

- **Backend** — a **FastAPI** service (`apps/api`, package `careerforge_api`) running in
  **demo/mock mode**. It serves the complete `/api/v1` surface from
  [`API_CONTRACT.md`](API_CONTRACT.md), streams a mission over **SSE** (with heartbeats and
  `Last-Event-ID` reconnect/replay), returns seeded Profile/Skills/Evidence/Pulse data, uses
  the contract error shape, and detects a hardware profile. It ships **21 passing tests**.
- **Mission engine** — a **scripted, deterministic simulation** (`simulation.py`) that
  advances a realistic Intake → Static → Runtime → Aggregate → Fix → Verify → Approval run
  and emits the exact contract-shaped events a real orchestrator would. It deliberately
  includes a **REJECTED** fix candidate so verification is visibly real.
- **Frontend** — a **Next.js 14** heavy-motion console (`apps/web`): **BootSequence**,
  **Command Center** (`/command`), **Contribution Lab** (`/lab`), **Skill Constellation**
  (`/skills`), **Industry Pulse** (`/pulse`), driven live by the backend's SSE stream with a
  bundled client-side mock as a fallback.

Everything runs cross-platform with **only Python 3.12+ and Node 18+** — no Docker, DB,
GPU, or Ollama.

---

## 2. REAL vs SIMULATED vs NOT-YET-WIRED

| Capability                              | Status          | Where / how                                                    |
| --------------------------------------- | --------------- | -------------------------------------------------------------- |
| `/api/v1` REST surface                  | **REAL**        | `apps/api/careerforge_api/main.py`                             |
| SSE stream + heartbeat + replay         | **REAL**        | `main.py` (`/events/stream`, `Last-Event-ID`)                 |
| Contract data shapes + enums            | **REAL**        | `schemas.py`; verified by tests                               |
| Contract error shape                    | **REAL**        | `main.py` exception handlers                                  |
| Profile / Skills / Evidence data        | **REAL (seeded)** | `seed_data.py` (Ada Lovelace demo profile)                  |
| Resume ingestion → SELF_DECLARED claims | **REAL**        | `main.py` `/profile/ingest-resume` (invariant enforced)       |
| Industry Pulse feed                     | **REAL (seeded)** | `seed_data.py` / `/pulse`                                    |
| Hardware-profile detection              | **REAL**        | `hardware.py` (psutil-based, with fallback)                   |
| Settings / env / safety flags           | **REAL**        | `config.py` (`CAREERFORGE_*`, flags default `false`)          |
| Backend test suite (21 tests)           | **REAL**        | `apps/api/tests`                                              |
| Frontend UI + motion + a11y             | **REAL**        | `apps/web/src`                                                |
| Typed API client + SSE hook + store     | **REAL**        | `apps/web/src/lib` (`api.ts`, `useMissionStream.ts`, `store.ts`) |
| Client-side mock mission (fallback)     | **REAL**        | `apps/web/src/lib/mockMission.ts`                            |
| **Mission execution (the 10 stages)**   | **SIMULATED**   | `simulation.py` scripted event sequence                       |
| **Multi-agent behavior**                | **SIMULATED**   | agents/edges/verdicts are scripted, contract-accurate         |
| **Findings / candidates / verification**| **SIMULATED**   | pre-authored, includes an accepted + a REJECTED candidate     |
| **Approval flow**                       | **REAL transport, SIMULATED effect** | `/approvals` records decision; `github_write` always `false`, draft saved locally |
| Model Gateway (Ollama)                  | NOT-YET-WIRED   | specced (`MASTER_SPEC.md` §4); `health` reports `mock`        |
| **RAG (Qdrant + embeddings)**           | **REAL**        | `packages/rag_core` — real Ollama embeddings + Qdrant (local/server), hybrid dense+BM25, RRF, rerank, citations, claim verifier; `/api/v1/rag/*`; 31 tests |
| **Code indexing (AST/Tree-sitter)**     | **REAL**        | `rag_core/chunking.py` — stdlib AST, chunk by function/class/method/module/doc-section |
| Real GitHub read-only client            | NOT-YET-WIRED   | specced; repo intake is simulated                             |
| Docker sandbox (untrusted execution)    | NOT-YET-WIRED   | specced (`THREAT_MODEL.md` §2.1); `repository_execution=false`|
| LangGraph subgraphs (in-stage)          | NOT-YET-WIRED   | specced (`ADR-0002`)                                         |
| Temporal workflows (mission lifecycle)  | NOT-YET-WIRED   | specced (`ADR-0002`)                                         |
| PostgreSQL persistence                  | NOT-YET-WIRED   | in-memory store used instead (same surface)                   |
| Redis queue / cache                     | NOT-YET-WIRED   | stubbed                                                       |
| Langfuse / Prometheus / Grafana         | NOT-YET-WIRED   | optional `docker-compose.yml`                                |

**Legend.** *REAL* = production-shaped code exercised in the demo. *SIMULATED* = deliberately
scripted/deterministic but flowing over the real transport and contract. *NOT-YET-WIRED* =
designed and documented, with a stub or mock in its place, to be implemented in a later
phase.

---

## 3. Mapping to handbook phases (0–15) — ALL IMPLEMENTED

Every handbook phase is now implemented and verified (146 tests across the API +
10 packages; ruff + mypy + tsc + eslint clean). Local-first + graceful
degradation throughout: real providers (Ollama, Qdrant, GitHub, Docker,
OpenTelemetry) are used when present, with dependency-free fallbacks so the
whole system runs anywhere — including behind a VPN with no Docker.

| Phase | Theme (handbook)                    | Status | Where |
| ----- | ----------------------------------- | ------ | ----- |
| 0     | Foundation & scaffolding            | ✅ Real | monorepo, contracts, Compose, cross-platform scripts |
| 1     | Profile Brain & evidence model      | ✅ Real | seeded profile/skills/evidence + API; no-unsupported-score rule |
| 2     | RAG baseline                        | ✅ Real | `rag_core`: Ollama embeddings + Qdrant + hybrid + rerank + citations + claim verifier |
| 3     | GitHub read-only                    | ✅ Real | `github_client`: typed read-only client, secret redaction, `/api/v1/github/*` |
| 4     | Repository indexing (AST)           | ✅ Real | `rag_core/chunking.py`: stdlib AST, symbol-aware chunks |
| 5     | Static-analysis agents              | ✅ Real | `static_analysis`: AST agents + real ruff/mypy runs |
| 6     | Safe sandbox (Docker)               | ✅ Real | `sandbox`: preflight + policy engine + hardened runner, gated off by default |
| 7     | Runtime investigation               | ✅ Real | `runtime_investigation`: env detect + sandboxed install/tests/lint/type |
| 8     | Duplicate detection                 | ✅ Real | `dup_detect`: exact + lexical + semantic, EXACT/NEAR/WEAK/NONE |
| 9     | Candidate patches                   | ✅ Real | `patch_gen`: real difflib diffs + NO_SUBMISSION; optional LLM enrichment |
| 10    | Verification swarm                  | ✅ Real | `verify_swarm`: independent verifiers (author ≠ verifier) + quality gate |
| 11    | Contribution Laboratory UI          | ✅ Real | Monaco diff, verification matrix, approval gate |
| 12    | Industry Pulse                      | ✅ Real | seeded feed + momentum chart, no job postings |
| 13    | Artifact engine + opportunity miner | ✅ Real | `artifact_engine`: evidence-producing assignments + repo ranking |
| 14    | Evaluation + observability          | ✅ Real | `observability`: spans/metrics, built-in + OpenTelemetry; 146 tests |
| 15    | Public evidence portfolio           | ✅ Real | `/portfolio`: verification-labelled skills + lazy evidence |

**Multi-agent orchestration** and the **10-stage contribution engine** exist in
two complementary forms: the scripted `simulation.py` mission (drives the live
Command Center UI end-to-end with zero infra) AND the real per-stage packages
above (static analysis → duplicates → candidates → verification), exposed as
real `/api/v1` endpoints. LangGraph/Temporal remain the specced durable-execution
layer (ADR-0002); the real stage logic they would orchestrate is implemented.

---

## 4. How to verify the claims above

```bash
# Backend tests (21 passing)
pip install -e "./apps/api[dev]"
python -m pytest apps/api/tests

# Health shows demo mocks + safety flags off
#   GET http://localhost:8000/api/v1/system/health
#   -> services.* == "mock", flags.github_writes == false,
#      flags.repository_execution == false
```

The full picture of what is next, and how each NOT-YET-WIRED item gets implemented, is in
[`NEXT_PHASE.md`](NEXT_PHASE.md). Honest limitations of the slice are in
[`KNOWN_ISSUES.md`](KNOWN_ISSUES.md).
