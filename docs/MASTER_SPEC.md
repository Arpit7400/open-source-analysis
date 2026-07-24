# CareerForge AI — Master Specification

> **Status:** permanent product specification (the "constitution").
> **Scope:** the entire product vision. This repository implements a *flagship vertical
> slice* of it (see [`IMPLEMENTATION_STATUS.md`](IMPLEMENTATION_STATUS.md)).
> **Precedence:** the [`API_CONTRACT.md`](API_CONTRACT.md) and
> [`DESIGN_SYSTEM.md`](DESIGN_SYSTEM.md) are binding for the frontend/backend boundary and
> the UI respectively; this document governs everything else. Where they conflict, the
> contract wins for shapes, this spec wins for intent.

---

## 1. Product objectives

CareerForge AI is a **local-first, multi-agent career-intelligence platform**. It exists
to answer three questions with *evidence*, not vibes:

1. **What can this person actually do?** — a continuously updated, evidence-backed skill
   model (the **Profile Brain**), where every skill carries a verification level and the
   artifacts that justify it.
2. **How can they credibly grow and contribute?** — a multi-agent **Contribution Engine**
   that analyzes real repositories, finds real problems, drafts real fixes, and has those
   fixes independently verified before a human decides whether to act.
3. **What is worth their attention right now?** — an **Industry Pulse** that fuses
   external momentum signals with the person's own skill gaps into concrete next actions.

### Non-negotiable product principles

- **Evidence over assertion.** Nothing is claimed without traceable evidence. Skills are
  never silently promoted; every change records a reason.
- **Verification over trust.** Every fix candidate is checked by an *independent* verifier
  agent. The system is designed to *reject* bad work, and the demo proves it does.
- **Human-in-the-loop for side effects.** No code execution and no external write (GitHub,
  filesystem outside the workspace) happens without an explicit, gated human decision.
- **Local-first.** The platform can run entirely on a developer's machine — local models
  (Ollama), local vector store (Qdrant), local database. No data leaves the box unless the
  operator opts in.
- **Safe by default.** It analyzes *untrusted* repositories. Sandboxing, prompt-injection
  defense, and least-privilege tool access are foundational, not bolted on.

---

## 2. Mandatory tech direction

| Layer                | Technology (fixed)                                                        |
| -------------------- | ------------------------------------------------------------------------- |
| Backend              | **Python 3.12+**, **FastAPI**, **Server-Sent Events** (SSE), Pydantic v2  |
| Frontend             | **Next.js 14** (App Router), **TypeScript**, Tailwind, shadcn/ui          |
| Motion / viz         | framer-motion, **@xyflow/react** (React Flow), **@react-three/fiber**/drei, **@monaco-editor/react**, echarts-for-react |
| Client state / data  | **TanStack Query**, **Zustand**, a typed API client matching the contract |
| Local models         | **Ollama** (chat + embeddings) via a **Model Gateway** abstraction        |
| Vector store / RAG   | **Qdrant**                                                                |
| Relational store     | **PostgreSQL** (async SQLAlchemy)                                          |
| Queue / cache        | **Redis**                                                                 |
| Agent orchestration  | **LangGraph** (in-process agent graphs) + **Temporal** (durable workflows)|
| Sandbox              | **Docker** container isolation for any untrusted execution                |
| Observability        | **Langfuse** (LLM tracing), **Prometheus** + **Grafana** (metrics)        |
| Packaging            | pip/hatchling (backend), npm (frontend), docker-compose (optional stack)  |

Cross-platform is mandatory: Windows, macOS, and Linux are all first-class. The demo runs
with **only Python + Node** — every heavier dependency is optional and degrades to a mock.

---

## 3. Architecture boundaries

The system is a **modular monolith** with clean module seams (see
[`ADR-0001`](decisions/ADR-0001-modular-monolith.md)). Modules communicate through typed
interfaces, not shared mutable state. The transport layer (FastAPI app) owns HTTP + SSE
only; domain logic lives in dedicated modules.

Modules (detailed in [`ARCHITECTURE.md`](ARCHITECTURE.md)):

- **A — Model Gateway**: the single choke point for all LLM/embedding calls.
- **B — Profile Brain**: the skill/evidence model and its verification state machine.
- **C — Industry Pulse**: momentum ingestion, relevance scoring, gap synthesis.
- **D — Contribution Engine**: the 10-stage repository analysis pipeline.
- **E — Multi-agent orchestration**: LangGraph subgraphs + Temporal workflows.
- **F — RAG**: chunking, embedding, retrieval over Qdrant.
- **G — Persistence**: PostgreSQL schema + repositories.
- **H — Transport & Observability**: FastAPI, SSE, Langfuse, Prometheus.

**The LangGraph / Temporal boundary** (see
[`ADR-0002`](decisions/ADR-0002-langgraph-temporal-boundary.md)): LangGraph orchestrates
the *fine-grained, in-memory agent graph within a single stage* (fast, stateful, cyclic
reasoning). Temporal orchestrates the *coarse-grained, long-lived, durable mission
lifecycle across stages* (retries, timeouts, human-approval waits that may span hours).
The rule of thumb: **inside a stage → LangGraph; across stages and over time → Temporal.**

---

## 4. Model Gateway (Module A)

A single abstraction (`ModelGateway`) mediates **all** model access. Nothing else in the
system talks to Ollama, an embedding model, or any hosted API directly.

Responsibilities:

- **Provider routing**: local (Ollama) first; optional remote providers behind the same
  interface. Selection informed by the detected **hardware profile**
  (`CPU_LOW | VRAM_8_12 | VRAM_16_24 | WORKSTATION`).
- **Uniform calls**: `chat()`, `embed()`, `structured()` (schema-constrained output).
- **Resource awareness**: never oversubscribe the machine; respects
  `max_agent_concurrency`; degrades model size on low-VRAM hosts.
- **Determinism hooks**: seedable, so evaluation and the demo simulation are reproducible.
- **Cost/latency accounting**: every call is traced to Langfuse with tokens and timing.
- **Safety**: enforces prompt/response size limits and strips tool-call injection attempts.

In demo mode the gateway is not exercised — the mission is scripted — but the interface is
the seam a real implementation slots into (see [`NEXT_PHASE.md`](NEXT_PHASE.md)).

---

## 5. Profile Brain (Module B)

The Profile Brain is the evidence-backed model of a person's capabilities.

**Entities**: a `Profile`, a set of `Skill`s, and `Evidence` items linked to skills.

Each `Skill` carries a **five-level verification ladder** (exact enum spellings from the
contract):

```
SELF_DECLARED → AI_INFERRED → TOOL_VERIFIED → HUMAN_REVIEWED → EXTERNALLY_VALIDATED
```

- **SELF_DECLARED** — the person said so (e.g. a resume claim). Never trusted as fact.
- **AI_INFERRED** — a model inferred it from artifacts (e.g. router modules detected).
- **TOOL_VERIFIED** — a deterministic tool confirmed it (e.g. tests pass, types check).
- **HUMAN_REVIEWED** — a human explicitly reviewed and endorsed the evidence.
- **EXTERNALLY_VALIDATED** — an external authority confirmed it (e.g. merged PR upstream).

Each skill also carries scored dimensions used by the Skill Constellation and ranking:
`confidence`, `evidence_strength`, `recency`, `complexity`, `independence`, a
`verification_level`, `evidence_ids`, `related_skill_ids`, and a **`last_change_reason`**
(the audit trail — why the skill last moved).

**Invariant:** resume ingestion (`POST /profile/ingest-resume`) returns *claims* only, each
`SELF_DECLARED`, never auto-verified. Promotion up the ladder requires evidence produced by
a tool, a human, or an external authority — never by the ingestion step itself.

---

## 6. Industry Pulse (Module C)

A personalized signal feed. Each pulse item has a `source`
(`arXiv | GitHub | Blog | Advisory`), a `technology`, a `published_at`, and three scores:
`momentum` (how fast the topic is moving), `personal_relevance` (fit to *this* profile's
skills and goals), and `actionability` (how concretely the person can act now). Each item
explains **`why_it_matters`**, names the **`skill_gap`**, and proposes a
**`suggested_action`**, with a `canonical_url` back to the source.

The engine ranks by a blend of the three scores, favoring high-actionability items that
target a real gap in the current profile.

---

## 7. Contribution Engine — the 10 stages (Module D)

The flagship flow. Given a repository URL, the engine runs a mission through ten stages.
Every finding is evidence-backed (file, line, snippet); every fix is independently verified;
no side effect happens without human approval.

1. **Intake** — read-only clone/index of the repository (never executes its code at intake).
2. **Planning** — Mission Control decomposes the goal into an agent graph with explicit
   assumptions and success criteria.
3. **Static analysis** — parallel agents scan for security smells, code-quality issues,
   docs drift, dependency risk, typing gaps, API inconsistencies, and deprecations
   (matching the `FindingCategory` enum).
4. **Runtime reproduction** — for findings that require it, reproduce the issue inside a
   **sandbox** (Docker, no host network) to move it from *suspected* to *reproduced*
   (`reproduction_status`).
5. **Aggregation / dedup** — merge duplicate findings across agents; assign confidence.
6. **Duplicate search** — check whether the issue is already reported upstream (using each
   finding's `duplicate_search_terms`) to avoid noise.
7. **Fix generation** — multiple **competing** fix agents draft candidate diffs, each with
   a root cause, scope, and risk level.
8. **Independent verification** — *separate* verifier agents run regression tests, lint,
   and a scope guard against each candidate. Verifiers can and do **reject** candidates
   (e.g. out-of-scope changes). A candidate's `verdict` is `ACCEPTED | REJECTED |
   NO_SUBMISSION | PENDING`.
9. **Quality gate** — only candidates that pass all required checks and stay in scope may
   proceed to a draft.
10. **Approval draft** — a human-reviewable issue/PR `Draft` is prepared. It is
    **never auto-submitted**; `submittable` is `false` while `github_writes` is off. A
    human APPROVE/REJECT is required; on APPROVE the draft is saved *locally only*.

Throughout, the mission emits contract-shaped SSE events (`mission.status`, `agent.update`,
`edge.update`, `finding.new`, `candidate.update`, `log`, `resource`, `approval.required`,
`mission.complete`) so the Command Center renders it live.

---

## 8. Multi-agent orchestration (Module E)

- **Agent taxonomy** (matches `AgentNode.group`): `CONTROL`, `INTAKE`, `STATIC`,
  `RUNTIME`, `DUPLICATE`, `AGGREGATE`, `FIX`, `VERIFY`.
- **Agent state machine** (matches `AgentState`): `WAITING → RUNNING → VERIFYING →
  COMPLETED`, with `BLOCKED`, `FAILED`, and `REJECTED` as terminal/blocking states.
- **Independent verification**: verifier agents are distinct nodes with `verifier_of`
  pointing at the fix agent they check. Independence is structural — a fix agent cannot
  verify its own work.
- **Orchestration mechanics**: LangGraph runs the in-stage agent graph (cyclic reasoning,
  shared scratchpad); Temporal owns the durable mission lifecycle, retries, timeouts, and
  the human-approval wait (see [`ADR-0002`](decisions/ADR-0002-langgraph-temporal-boundary.md)).
- **Concurrency**: capped by `max_agent_concurrency`; the resource gauges reflect live
  active-agent counts.

---

## 9. RAG (Module F)

Retrieval-augmented context for agents:

- **Chunking**: repository files, docs, and prior findings are chunked with structural
  awareness (function/class boundaries, headings).
- **Embedding**: via the Model Gateway's `embed()` (local embedding model by default).
- **Store**: **Qdrant** collections per corpus (code, docs, evidence, pulse).
- **Retrieval**: hybrid (dense + keyword) with per-agent scoping so an agent only sees the
  context relevant to its task. Retrieved chunks carry provenance so findings can cite
  exact file/line evidence.

---

## 10. Database tables (Module G)

PostgreSQL schema (async SQLAlchemy). Canonical tables:

| Table                 | Purpose                                                          |
| --------------------- | ---------------------------------------------------------------- |
| `profiles`            | user profile: name, headline, goals, aggregate counters          |
| `skills`              | skill rows with scores + verification_level + last_change_reason  |
| `evidence`            | evidence items (type, summary, source_url, verification_level)    |
| `skill_evidence`      | many-to-many link between skills and evidence                     |
| `skill_relations`     | related-skill edges for the constellation                         |
| `missions`            | repository analysis missions (repo_url, status, plan, timestamps) |
| `agents`              | agent nodes per mission (group, state, progress, verifier_of)     |
| `mission_edges`       | agent-graph edges (source, target, animated)                      |
| `findings`            | findings (category, severity, confidence, evidence, reproduction) |
| `candidates`          | fix candidates (verdict, risk, diff, scope)                       |
| `verifications`       | per-candidate verification checks (check, status, verifier_agent) |
| `drafts`              | issue/PR drafts (kind, body_markdown, submittable, target_repo)   |
| `approvals`           | human decisions (decision, note, action_taken, github_write)      |
| `pulse_items`         | industry pulse feed items with scores + rationale                 |
| `mission_events`      | append-only event log (id, type, payload) — powers SSE replay     |

All timestamps are ISO-8601 UTC. IDs are UUID strings. The append-only `mission_events`
table is the source of truth for SSE `Last-Event-ID` reconnect/replay.

---

## 11. Frontend screens (Module H — UI)

Bound by [`DESIGN_SYSTEM.md`](DESIGN_SYSTEM.md). Dark technical command-center aesthetic.

1. **BootSequence** — fake-but-real terminal boot log on first load, then reveals the app.
2. **Command Center** (`/command`) — the hero: live mission list + animated resource
   gauges, a **React Flow live agent graph** with animated edges and state-colored nodes,
   a streaming virtualized **event log**, and a phase pipeline
   (Intake → Static → Runtime → Aggregate → Fix → Verify → Approval).
3. **Contribution Lab** (`/lab`) — findings (severity-coded, evidence + reproduction
   badges), **Monaco candidate diffs**, a **Verification Matrix** (checks × verdicts) that
   includes a **REJECTED** candidate, a risk panel, and the **Approval Panel** with the
   prominent "GitHub writes DISABLED" banner.
4. **Skill Constellation** (`/skills`) — a **React-Three-Fiber** 3D skill graph
   (size = evidence, glow = confidence, pulse = recency, edges = relationships), lazy-loaded
   with an accessible table fallback and non-WebGL detection.
5. **Industry Pulse** (`/pulse`) — an ECharts momentum timeline with relevance overlays and
   skill-gap cards.

All screens honor `prefers-reduced-motion`, keyboard navigation, visible focus, ARIA live
regions for SSE, a high-contrast toggle, and a user-selectable Performance Mode.

---

## 12. Observability

- **Langfuse** traces every Model Gateway call: prompt, tools, tokens, latency, cost, and
  the agent/mission that issued it.
- **Prometheus** scrapes API and worker metrics (request latency, active agents, mission
  throughput, sandbox usage). **Grafana** dashboards visualize them.
- **Structured logs**: every agent emits contract-shaped `log` events
  (`INFO | WARN | ERROR`) surfaced live in the event log.
- **Mission audit**: the append-only `mission_events` log is the durable record of what
  happened, in order.

---

## 13. Evaluation

- **Golden missions**: a fixed set of repositories with known issues; the engine's findings
  are scored against a labeled ground truth (precision/recall per `FindingCategory`).
- **Verifier soundness**: seeded bad candidates (out-of-scope, regression-breaking) that
  MUST be rejected; seeded good candidates that MUST be accepted. The demo's REJECTED
  candidate is a live instance of this.
- **Determinism**: seedable Model Gateway + scripted demo make runs reproducible for CI.
- **Regression suite**: the backend ships **21 passing tests** covering health, profile,
  and the full mission flow, run in CI on every change.

---

## 14. Security

Summarized here; enumerated with mitigations in [`THREAT_MODEL.md`](THREAT_MODEL.md).

- **Two hard safety flags**, both default `false`: `github_writes` and
  `repository_execution`. Surfaced in `GET /system/health.flags`.
- **Untrusted-code sandbox**: any repository execution runs only inside a locked-down
  Docker container (no host network, dropped capabilities, read-only root FS, strict
  CPU/memory/time limits). Never enable `repository_execution` without it.
- **Prompt-injection defense**: repository content is treated as *data, never
  instructions*; agent tool access is least-privilege; tool-call injection is stripped at
  the Model Gateway.
- **GitHub permission model**: staged — read-only by default; writes gated behind a human
  approval AND the `github_writes` flag; the approval endpoint always returns
  `github_write: false` in this slice.
- **Token handling**: secrets live only in env/`.env` (git-ignored), never logged, never
  sent to models.
- **Data isolation**: per-user/per-mission scoping in the store and in RAG retrieval.

---

## 15. The 20 development rules

1. **The API contract is law.** Match [`API_CONTRACT.md`](API_CONTRACT.md) shapes and enum
   spellings exactly. When in doubt, the contract wins.
2. **Cross-platform always.** Windows, macOS, Linux. No bash-only assumptions in code.
3. **Demo mode must always run** with just Python + Node — no Docker, DB, or GPU required.
4. **Safety flags default off.** `github_writes` and `repository_execution` are `false`
   unless an operator explicitly enables them.
5. **Never execute untrusted code** outside a hardened sandbox.
6. **No auto-submission.** Every external side effect is behind a human approval gate.
7. **Evidence or it didn't happen.** Every finding cites file/line/snippet; every skill
   cites evidence.
8. **Independent verification.** A fix agent never verifies its own candidate.
9. **Model access only via the Model Gateway.** Nothing else calls a model directly.
10. **Strict typing.** Strict TypeScript on the frontend; strict mypy + Pydantic v2 on the
    backend.
11. **Complete, runnable files.** No TODOs, placeholders, or elisions in shipped code.
12. **Deterministic where it matters.** Seedable models; scripted demo; reproducible CI.
13. **Least-privilege tools.** Agents get the minimum tool scope for their task.
14. **Secrets stay in env.** Never commit or log tokens; `.env` is git-ignored.
15. **Accessibility is required.** Reduced-motion, keyboard, ARIA, non-WebGL fallbacks.
16. **Performance budget.** 60fps UI target; animate transform/opacity, never layout on
    many nodes.
17. **Observability by default.** Trace model calls; emit structured logs; expose metrics.
18. **Modular seams.** Modules talk through typed interfaces, not shared mutable state.
19. **Honest status.** Clearly document what is REAL vs SIMULATED vs NOT-YET-WIRED.
20. **Every decision is recorded.** Significant choices are captured as ADRs.

---

## 16. Initial vertical slice

This repository is the **flagship vertical slice**: it proves the whole story end-to-end
with the *thinnest real backend that honors the full contract*.

- **Real**: FastAPI backend in **demo mode** with the complete `/api/v1` surface, an SSE
  stream with reconnect/replay, seeded Profile/Skills/Evidence/Pulse data, contract-shaped
  error handling, hardware-profile detection, and **21 passing tests**.
- **Real UI**: Next.js 14 heavy-motion console — BootSequence, Command Center (React Flow
  agent graph, event log, resource gauges, phase pipeline), Contribution Lab (Monaco diffs,
  verification matrix with a REJECTED candidate, approval panel), Skill Constellation
  (R3F + table fallback), Industry Pulse (ECharts).
- **Simulated**: the mission itself is a scripted, deterministic simulation over the real
  SSE transport — same shapes a real orchestrator would emit.
- **Not yet wired (specced/stubbed)**: Ollama Model Gateway, Qdrant RAG, real GitHub
  read-only client, Docker sandbox, LangGraph subgraphs, Temporal workflows, Langfuse /
  Prometheus / Grafana.

The mapping to concrete work items is in [`IMPLEMENTATION_STATUS.md`](IMPLEMENTATION_STATUS.md)
and [`NEXT_PHASE.md`](NEXT_PHASE.md).

---

## 17. Deliverables

- A runnable monorepo: `apps/api` (backend) + `apps/web` (frontend).
- The binding [`API_CONTRACT.md`](API_CONTRACT.md) and [`DESIGN_SYSTEM.md`](DESIGN_SYSTEM.md).
- This master spec, plus [`ARCHITECTURE.md`](ARCHITECTURE.md),
  [`THREAT_MODEL.md`](THREAT_MODEL.md), [`IMPLEMENTATION_STATUS.md`](IMPLEMENTATION_STATUS.md),
  [`NEXT_PHASE.md`](NEXT_PHASE.md), [`KNOWN_ISSUES.md`](KNOWN_ISSUES.md), and ADRs.
- Cross-platform setup/dev scripts (`scripts/*.sh` + `scripts/*.ps1`), a root
  `package.json`, a `Makefile`, an optional `docker-compose.yml`, and `.env.example`.
- A backend regression suite (**21 passing tests**).
