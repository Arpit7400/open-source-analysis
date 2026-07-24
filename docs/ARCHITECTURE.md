# CareerForge AI — Architecture

> Companion to [`MASTER_SPEC.md`](MASTER_SPEC.md). This document describes the module map
> (A–H), the technology boundary table, the **LangGraph vs Temporal** boundary, the
> high-level request/mission flow, the monorepo structure, and the parallel-repository
> development workflow. It also states clearly **what is REAL vs SIMULATED** in this slice.

---

## 1. System at a glance

```
        ┌──────────────────────────────────────────────────────────────────┐
        │                        Browser (Next.js :3000)                     │
        │  BootSequence · Command Center · Contribution Lab · Constellation  │
        │  · Industry Pulse   —   React Flow · R3F · Monaco · ECharts        │
        │  Zustand (live mission state) · TanStack Query · typed API client  │
        └───────────────┬──────────────────────────────────▲────────────────┘
             REST /api/v1 │                                  │ SSE /events/stream
                          ▼                                  │ (Last-Event-ID replay)
        ┌──────────────────────────────────────────────────────────────────┐
        │                     H · Transport (FastAPI :8000)                  │
        │  routes · CORS · SSE generator · contract error handler            │
        └───────────────┬──────────────────────────────────────────────────┘
                        │  typed interfaces (no shared mutable state)
   ┌──────────┬─────────┼──────────┬───────────┬───────────┬────────────────┐
   ▼          ▼         ▼          ▼           ▼           ▼                ▼
┌───────┐ ┌────────┐ ┌────────┐ ┌─────────┐ ┌────────┐ ┌────────────┐ ┌──────────┐
│ A     │ │ B      │ │ C      │ │ D       │ │ E      │ │ F          │ │ G        │
│ Model │ │Profile │ │Industry│ │Contrib. │ │Multi-  │ │ RAG        │ │Persist.  │
│Gateway│ │ Brain  │ │ Pulse  │ │ Engine  │ │agent   │ │(Qdrant)    │ │(Postgres)│
└───┬───┘ └────────┘ └────────┘ └────┬────┘ │orches. │ └────────────┘ └──────────┘
    │                                │      └───┬────┘
    ▼ (Ollama)                       ▼          ▼
  local models              10-stage pipeline  LangGraph (in-stage)
                                               Temporal (across stages)
```

In **demo mode** (the default) modules A, F, G and the LangGraph/Temporal orchestration are
**mocked or scripted** — the Contribution Engine (D) runs a deterministic simulation and
the transport layer (H) streams it over the real SSE contract. B, C, and H are exercised
for real against seeded data.

---

## 2. Modules A–H

### A · Model Gateway
The single choke point for all LLM/embedding calls. Provider routing (Ollama-first),
hardware-aware model selection, `chat()`/`embed()`/`structured()` calls, seedable
determinism, size/limit enforcement, and per-call Langfuse tracing. Nothing else in the
system contacts a model directly. **Demo: not exercised (mission is scripted).**

### B · Profile Brain
The evidence-backed skill model and its five-level verification ladder
(`SELF_DECLARED → AI_INFERRED → TOOL_VERIFIED → HUMAN_REVIEWED → EXTERNALLY_VALIDATED`).
Owns `Profile`, `Skill`, `Evidence`, scored skill dimensions, and the `last_change_reason`
audit trail. Enforces the invariant that resume ingestion only ever produces
`SELF_DECLARED` claims. **Demo: REAL over seeded data.**

### C · Industry Pulse
Momentum ingestion, relevance scoring against the current profile, and skill-gap synthesis;
produces feed items with `momentum` / `personal_relevance` / `actionability` and a
`why_it_matters` / `skill_gap` / `suggested_action` rationale. **Demo: REAL over seeded data.**

### D · Contribution Engine
The 10-stage repository analysis pipeline (Intake → Planning → Static → Runtime →
Aggregation → Duplicate search → Fix generation → Independent verification → Quality gate →
Approval draft). Emits contract-shaped events. **Demo: SIMULATED (scripted, deterministic).**

### E · Multi-agent orchestration
Agent taxonomy (`CONTROL/INTAKE/STATIC/RUNTIME/DUPLICATE/AGGREGATE/FIX/VERIFY`), the agent
state machine, structural independence of verifiers (`verifier_of`), and the
LangGraph/Temporal split. **Demo: SIMULATED (the scripted engine plays the agents).**

### F · RAG
Structural chunking, embeddings via the Model Gateway, Qdrant collections (code/docs/
evidence/pulse), and per-agent scoped hybrid retrieval with provenance. **Demo:
NOT-YET-WIRED (stubbed).**

### G · Persistence
PostgreSQL schema (see [`MASTER_SPEC.md` §10](MASTER_SPEC.md)) plus the append-only
`mission_events` log that powers SSE replay. **Demo: NOT-YET-WIRED — replaced by an
in-memory store with the same surface.**

### H · Transport & Observability
FastAPI app (routes, CORS, contract error shape), the SSE generator with heartbeats and
`Last-Event-ID` reconnect/replay, plus Langfuse/Prometheus/Grafana hooks. **Demo:
transport is REAL; observability sinks are NOT-YET-WIRED (optional docker-compose).**

---

## 3. Technology boundary table

| Concern                 | Technology            | REAL in demo? | Notes                                   |
| ----------------------- | --------------------- | ------------- | --------------------------------------- |
| HTTP + SSE transport    | FastAPI, sse-starlette| **Yes**       | Full `/api/v1` surface, SSE replay      |
| Data shapes / validation| Pydantic v2           | **Yes**       | Enforces the contract                   |
| Profile / Skills / Pulse| seed data module      | **Yes**       | Seeded, contract-accurate               |
| Mission engine          | scripted simulator    | Simulated     | Same events a real orchestrator emits   |
| Local models            | Ollama (Model Gateway)| No            | `health` reports `mock`                 |
| Vector store / RAG      | Qdrant                | No            | Stubbed                                 |
| Relational store        | PostgreSQL            | No            | In-memory store used instead            |
| Queue / cache           | Redis                 | No            | Stubbed                                 |
| In-stage orchestration  | LangGraph             | No            | Specced; simulator plays the graph      |
| Durable workflows       | Temporal              | No            | Specced; simulator plays the lifecycle  |
| Untrusted execution     | Docker sandbox        | No            | `repository_execution=false`            |
| Observability           | Langfuse / Prom / Grafana | No        | Optional docker-compose                 |
| Frontend                | Next.js 14 + TS       | **Yes**       | Live UI against the real backend        |

---

## 4. The LangGraph vs Temporal boundary

Both are orchestration tools; they operate at **different granularities**. See
[`ADR-0002`](decisions/ADR-0002-langgraph-temporal-boundary.md) for the full rationale.

```
   Temporal  (coarse, durable, long-lived)
   ┌──────────────────────────────────────────────────────────────────────┐
   │  Mission workflow                                                      │
   │                                                                        │
   │   Intake ─► Static ─► Runtime ─► Aggregate ─► Fix ─► Verify ─► Approval │
   │     │         │          │           │         │        │         │    │
   │     ▼         ▼          ▼           ▼         ▼        ▼         ▼    │
   │  ┌──────┐ ┌──────┐  ┌──────┐   ┌──────┐  ┌──────┐ ┌──────┐  (human    │
   │  │ Lang │ │ Lang │  │ Lang │   │ Lang │  │ Lang │ │ Lang │   wait —    │
   │  │Graph │ │Graph │  │Graph │   │Graph │  │Graph │ │Graph │   may span  │
   │  │  ▲▼  │ │  ▲▼  │  │  ▲▼  │   │  ▲▼  │  │  ▲▼  │ │  ▲▼  │   hours)     │
   │  └──────┘ └──────┘  └──────┘   └──────┘  └──────┘ └──────┘             │
   └──────────────────────────────────────────────────────────────────────┘
         (each box = a cyclic, in-memory multi-agent graph for that stage)
```

- **LangGraph — inside a stage.** Fast, stateful, cyclic agent reasoning within a single
  stage (e.g. the Fix stage's competing agents + their scratchpads). In-process, low
  latency, no durability requirement beyond the stage.
- **Temporal — across stages and over time.** The durable mission lifecycle: sequencing
  stages, retries, timeouts, and — critically — the **human-approval wait**, which may
  span hours or days and must survive process restarts. Temporal owns the mission's
  authoritative status transitions (`MissionStatus`).

**Rule of thumb: inside a stage → LangGraph; across stages and over time → Temporal.**

In this slice both are simulated: the scripted engine produces exactly the event sequence
this boundary would yield.

---

## 5. High-level flow (a mission)

1. Browser `POST /api/v1/repositories/analyze { repo_url }` → `{ mission_id, status:"QUEUED" }`.
2. Browser opens SSE `GET /api/v1/events/stream?mission_id=…`.
3. Backend (demo: the scripted engine; real: Temporal) advances the mission, appending
   contract-shaped events to the append-only event log.
4. SSE streams `mission.status`, `agent.update`, `edge.update`, `finding.new`,
   `candidate.update`, `log`, `resource`, and finally `approval.required`.
5. The UI folds events into Zustand state (replace-by-id) to render the live agent graph,
   event log, findings, and candidate diffs.
6. At the approval gate the human `POST /api/v1/approvals/{mission_id} { decision }`.
   The draft is saved locally; `github_write` is always `false`.
7. `mission.complete` ends the stream. On reconnect the client sends `Last-Event-ID` and
   the server replays everything after it.

---

## 6. Monorepo structure

```
careerforge-ai/
├── apps/
│   ├── api/                     FastAPI backend (Python package: careerforge_api)
│   │   ├── careerforge_api/
│   │   │   ├── main.py          transport: app, routes, SSE, error handler
│   │   │   ├── __main__.py      `python -m careerforge_api` entrypoint (:8000)
│   │   │   ├── config.py        pydantic-settings (CAREERFORGE_* env vars)
│   │   │   ├── schemas.py       Pydantic models + enums (the contract)
│   │   │   ├── hardware.py      hardware-profile detection + live resources
│   │   │   ├── simulation.py    MissionSimulator + MissionStore (scripted engine)
│   │   │   └── seed_data.py     profile / skills / evidence / pulse seeds
│   │   ├── tests/               21 passing tests
│   │   └── pyproject.toml
│   └── web/                     Next.js 14 frontend (package: careerforge-web)
│       ├── src/app/             App Router routes: /command /lab /skills /pulse
│       ├── src/components/      command · lab · pulse · skills · ui + BootSequence
│       └── src/lib/             api client · types · SSE hook · Zustand store · mock
├── docs/                        specs, architecture, threat model, ADRs, status
├── scripts/                     dev.sh · setup.sh · dev.ps1 · setup.ps1
├── docker-compose.yml           OPTIONAL real-services stack (not needed for demo)
├── Makefile                     dev/api/web/test/lint (Windows: use scripts/*.ps1)
├── package.json                 root convenience scripts
└── .env.example                 demo-friendly defaults
```

---

## 7. Parallel repository development workflow

The system is built by multiple tracks working in parallel against two fixed contracts —
[`API_CONTRACT.md`](API_CONTRACT.md) (the frontend/backend boundary) and
[`DESIGN_SYSTEM.md`](DESIGN_SYSTEM.md) (the UI). Contracts-first means tracks can integrate
without collisions.

```
                     ┌───────────────────────────────────────┐
                     │        Contracts (source of truth)      │
                     │   API_CONTRACT.md  ·  DESIGN_SYSTEM.md   │
                     └───────────────┬───────────────┬─────────┘
                                     │ read-only      │ read-only
        ┌────────────────────────────┼───────────────┼────────────────────────────┐
        ▼                            ▼                ▼                            ▼
  ┌───────────┐              ┌───────────┐     ┌───────────┐              ┌───────────┐
  │ Backend   │              │ Frontend  │     │ Frontend  │              │ Infra +   │
  │ tracks    │              │ Command   │     │ Lab /     │              │ Docs +    │
  │ (apps/api)│              │ Center    │     │ Skills /  │              │ scripts   │
  │           │              │ track     │     │ Pulse     │              │ (this     │
  │           │              │           │     │ tracks    │              │ track)    │
  └─────┬─────┘              └─────┬─────┘     └─────┬─────┘              └─────┬─────┘
        │ owns apps/api            │ owns command/    │ owns lab,skills,        │ owns docs,
        │ only                     │ only             │ pulse only              │ scripts, root
        └──────────────────────────┴─────────┬────────┴─────────────────────────┘
                                              ▼
                              ┌───────────────────────────────┐
                              │  Orchestrator merges + verifies │
                              │  (installs, typechecks, tests)  │
                              └───────────────────────────────┘
```

- **File ownership is disjoint** — each track writes only its assigned files, so tracks
  never collide.
- **The contracts are read-only** to every track; they are the only shared surface.
- **The orchestrator** integrates the tracks and runs installs/typechecks/tests
  afterward — individual tracks do not run servers or installs.
