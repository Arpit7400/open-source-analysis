# CareerForge AI

> A local-first, multi-agent **career-intelligence** platform. This repository is the
> **flagship vertical slice**: a heavy-motion engineering operations console driven by a
> real FastAPI backend running a scripted, deterministic mission simulation.

CareerForge AI turns raw engineering activity — repositories, commits, tests, docs — into
an evidence-backed picture of what you can actually do, and then uses a fleet of
cooperating AI agents to find real, verifiable ways to improve a codebase and grow your
skills. It is **local-first** (your data and models can stay on your machine),
**verification-obsessed** (nothing is claimed without evidence; every fix is checked by an
*independent* verifier), and **human-in-the-loop** (no code is executed and nothing is
written to GitHub without an explicit, gated human decision).

This slice runs end-to-end with **only Python and Node** — no Docker, no GPU, no database,
no Ollama required. Windows, macOS, and Linux are all first-class.

---

## 1. What CareerForge AI is

CareerForge AI is built around four ideas:

1. **Profile Brain** — a living model of your skills, each with a *verification level*
   (self-declared → AI-inferred → tool-verified → human-reviewed → externally-validated)
   and the evidence that backs it. Skills are never silently promoted; every change has a
   reason.
2. **Contribution Engine** — a multi-agent mission that analyzes a repository across
   static, runtime, aggregation, fix, and verification stages, produces evidence-backed
   findings, drafts fix candidates, and has *independent verifier agents* accept or reject
   each candidate on its own merits.
3. **Industry Pulse** — a personalized momentum feed that maps what is moving in the
   industry to your specific skill gaps and turns it into concrete next actions.
4. **Skill Constellation** — a 3D visualization of your skills where size encodes evidence
   strength, glow encodes confidence, and edges encode relationships.

### The flagship demo story

Ada Lovelace (the seeded demo profile) wants to merge three OSS pull requests and master
RAG systems. She points CareerForge AI at a public GitHub repository. The **Command
Center** lights up: Mission Control decomposes the goal into an agent graph, a Repo Intake
agent clones the repository read-only, Static agents surface a **HIGH-severity unpinned
dependency** and a high-complexity untested function, a Runtime agent reproduces the
advisory in an isolated environment, and an Aggregator deduplicates the findings.

Two **Fix Agents** then compete. Fix Agent A drafts a tight, one-file dependency pin. Fix
Agent B attempts a sprawling nine-file refactor. **Independent verifier agents** run the
regression suite, lint, and a scope guard — they **accept** Fix Agent A and **reject** Fix
Agent B for out-of-scope changes. Finally, an **Approval Gate** presents a
human-reviewable PR draft behind a prominent **"GitHub writes DISABLED"** banner. Nothing
is submitted. Ada reviews, approves, and the draft is saved locally.

The whole run streams live over Server-Sent Events into a React Flow agent graph, a
virtualized event log, and animated resource gauges.

---

## 2. Prerequisites

| Tool         | Version    | Notes                                              |
| ------------ | ---------- | -------------------------------------------------- |
| **Node.js**  | 18+        | 20 LTS recommended. Ships with `npm`.              |
| **Python**   | 3.12+      | Required by the backend (`careerforge_api`).       |
| **Docker**   | *optional* | Only for the full real-services stack (see below). |

You do **not** need Docker, a GPU, a database, Qdrant, or Ollama to run the demo.

---

## 3. Quick start (demo mode)

Two processes: the **backend** on port `8000` and the **frontend** on port `3000`. Start
the backend first. Copy `.env.example` to `.env` if you want to change defaults — the
committed defaults already select demo mode.

> **One-command shortcut:** `scripts/setup.*` installs everything and `scripts/dev.*`
> boots both processes. See section 4. The manual steps below show exactly what those
> scripts do.

### macOS / Linux

```bash
# --- 1. Backend (terminal 1) ---
python3 -m venv .venv
source .venv/bin/activate
pip install -e ./apps/api
python -m careerforge_api            # serves http://localhost:8000  (docs at /docs)

# --- 2. Frontend (terminal 2) ---
cd apps/web
npm install
npm run dev                          # serves http://localhost:3000
```

### Windows (PowerShell)

```powershell
# --- 1. Backend (terminal 1) ---
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .\apps\api
python -m careerforge_api            # serves http://localhost:8000  (docs at /docs)

# --- 2. Frontend (terminal 2) ---
cd apps\web
npm install
npm run dev                          # serves http://localhost:3000
```

Then open **http://localhost:3000**. On first load a BootSequence "boots the system", then
the Command Center appears. Paste any GitHub URL (e.g. `https://github.com/owner/name`) and
watch the mission run.

> If PowerShell blocks script activation, run
> `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in that session first.

---

## 4. Convenience scripts

Cross-platform helpers live in `scripts/`. From the repo root:

| Task                         | macOS / Linux           | Windows (PowerShell)          |
| ---------------------------- | ----------------------- | ----------------------------- |
| One-time install             | `bash scripts/setup.sh` | `powershell scripts/setup.ps1`|
| Start backend + frontend     | `bash scripts/dev.sh`   | `powershell scripts/dev.ps1`  |

Root `package.json` also exposes convenience passthroughs (`npm run dev`, `npm run web`,
`npm run api`) and a `Makefile` provides `make dev / api / web / test / lint`. **Windows
users should prefer the `scripts/*.ps1` scripts** rather than `make`.

---

## 5. How demo / mock mode works

The backend defaults to `APP_ENV=demo` (`CAREERFORGE_APP_ENV=demo`). In this mode:

- Every external service (**database, Qdrant, Redis, Ollama, Temporal**) reports `"mock"`
  in `GET /api/v1/system/health` — none of them are actually contacted.
- `POST /api/v1/repositories/analyze` starts a **scripted, realistic mission simulation**:
  a deterministic sequence of contract-shaped events (`agent.update`, `edge.update`,
  `finding.new`, `candidate.update`, `log`, `approval.required`, …) is streamed over SSE
  with realistic pacing. Same JSON shapes, same enum spellings, same event stream as a
  future real orchestrator — only the *engine* is simulated.
- The two safety flags **`github_writes` and `repository_execution` are `false`**. The
  approval endpoint always returns `github_write: false` and only saves the draft locally.

The frontend has a **bundled client-side mock** (`apps/web/src/lib/mockMission.ts`) as a
fallback so the UI is never dead even if the backend is unreachable — but the preferred and
default path is the live backend simulation.

The backend ships with **21 passing tests** (`apps/api/tests`) covering health, profile,
and the full mission flow. Run them with `make test` or:

```bash
pip install -e "./apps/api[dev]"
python -m pytest apps/api/tests
```

---

## 6. Architecture overview

```
                          ┌───────────────────────────────────────────────┐
                          │                 Browser (:3000)                │
                          │  Next.js 14 App Router · React Flow · R3F ·     │
                          │  Monaco · ECharts · framer-motion · Zustand     │
                          │                                                 │
                          │  Command Center · Contribution Lab ·            │
                          │  Skill Constellation · Industry Pulse           │
                          └───────────────┬─────────────────▲───────────────┘
                                REST /api/v1 │               │ SSE /events/stream
                                             ▼               │
                          ┌───────────────────────────────────────────────┐
                          │              FastAPI backend (:8000)            │
                          │  transport (main.py) · schemas · config ·       │
                          │  hardware · seed_data                           │
                          │                                                 │
                          │        ┌──────────────────────────────┐         │
                          │        │   Mission Simulation Engine   │         │
                          │        │  Intake→Static→Runtime→        │         │
                          │        │  Aggregate→Fix→Verify→Approval │         │
                          │        └──────────────────────────────┘         │
                          └───────────────┬─────────────────────────────────┘
                                          │ (demo mode: all mocked)
        ┌──────────┬──────────┬───────────┼───────────┬──────────┬──────────┐
        ▼          ▼          ▼           ▼           ▼          ▼          ▼
    Postgres    Qdrant      Redis      Ollama     Temporal   LangGraph   Docker
    (mock)      (mock)      (mock)     (mock)      (mock)    (specced)   sandbox
                                                                        (specced)
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full module map and the
LangGraph-vs-Temporal boundary, and
[`docs/IMPLEMENTATION_STATUS.md`](docs/IMPLEMENTATION_STATUS.md) for exactly what is REAL
vs SIMULATED vs NOT-YET-WIRED in this slice.

---

## 7. Safety notes

CareerForge AI is designed to analyze **untrusted** third-party repositories. That makes
safety a first-class product concern, not an afterthought.

- **GitHub writes are DISABLED.** The `github_writes` flag is `false` by default. The
  approval flow drafts an issue/PR and saves it **locally only**; the API never calls a
  GitHub write endpoint. `github_write` in the approval response is always `false`.
- **Untrusted repository code is never executed** in this slice. `repository_execution` is
  `false`. When runtime reproduction is wired up (a future phase), it will run only inside
  a **locked-down container sandbox** — no host network, dropped capabilities, read-only
  root filesystem, strict CPU/memory/time limits.
- **Prompt-injection defense.** Repository contents (READMEs, issues, code comments) are
  treated as *data, never instructions*. Agent tool access is least-privilege.
- **No auto-submission.** Every side-effecting action is behind an explicit human approval
  gate.

The full analysis lives in [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md). Even so: only
point real analysis at repositories you trust, and never enable `repository_execution`
without a real sandbox in place.

---

## 8. Roadmap

CareerForge AI is planned in 16 phases (0–15). This repository delivers the flagship
vertical slice that spans Phase 0 and the demo-facing parts of Phases 2, 3, 5, 6, and 12.

| Phase | Theme                          | Status in this slice                                   |
| ----- | ------------------------------ | ------------------------------------------------------ |
| 0     | Foundations & scaffolding      | **Done** — monorepo, contracts, CI-ready backend + UI  |
| 1     | Model Gateway (Ollama/local)   | Specced / stubbed (`health` reports `mock`)            |
| 2     | Profile Brain & evidence model | **Demo real** — seeded profile, skills, evidence, API  |
| 3     | Contribution Engine (10 stages)| **Simulated** — full scripted mission over SSE         |
| 4     | RAG (Qdrant + embeddings)      | Specced / stubbed                                      |
| 5     | Multi-agent orchestration      | **Simulated** — agent graph, verifiers, approval gate  |
| 6     | Command Center UI              | **Done** — live graph, event log, gauges, pipeline     |
| 7     | Runtime sandbox (Docker)       | Specced (`docs/THREAT_MODEL.md`, `docs/NEXT_PHASE.md`) |
| 8     | Security & threat model        | **Done (docs)** — enforced flags, threat model         |
| 9     | GitHub read-only client        | Specced / stubbed                                      |
| 10    | LangGraph subgraphs            | Specced (`ADR-0002`)                                   |
| 11    | Temporal durable workflows     | Specced (`ADR-0002`)                                   |
| 12    | Industry Pulse                 | **Demo real** — seeded feed + momentum chart           |
| 13    | Observability (Langfuse etc.)  | Specced (`docker-compose.yml`, `docs/NEXT_PHASE.md`)   |
| 14    | Evaluation harness             | Specced (`docs/MASTER_SPEC.md`)                        |
| 15    | Hardening & packaging          | Partial — cross-platform scripts, pinned deps          |

See [`docs/MASTER_SPEC.md`](docs/MASTER_SPEC.md) for the full specification and
[`docs/NEXT_PHASE.md`](docs/NEXT_PHASE.md) for concrete next steps to wire real services.

---

## 9. What makes it stand out

- **A real backend, not a mock UI.** The demo streams from an actual FastAPI service with a
  contract-tested SSE engine and 21 passing tests — the same shapes a real orchestrator
  would emit.
- **Verification you can see fail.** The mission deliberately includes a **REJECTED** fix
  candidate so you can watch independent verifiers do their job, not just rubber-stamp.
- **Safety is visible.** The "GitHub writes DISABLED" gate and mock-service health are
  surfaced in the UI, not buried in config.
- **Serious engineering aesthetic.** A dark command-center design system, a fake-but-real
  boot sequence, a React Flow agent graph, a 3D skill constellation, and Monaco diffs —
  with full `prefers-reduced-motion`, keyboard, and non-WebGL fallbacks.
- **Runs anywhere with just Python + Node.** Windows is first-class; no Docker required.

---

## Repository layout

```
careerforge-ai/
├── apps/
│   ├── api/           FastAPI backend (careerforge_api) — 21 passing tests
│   └── web/           Next.js 14 frontend console
├── docs/              Specs, architecture, threat model, ADRs, status
├── scripts/           Cross-platform dev/setup scripts (.sh + .ps1)
├── docker-compose.yml Optional full real-services stack (NOT needed for demo)
├── Makefile           dev/api/web/test/lint targets
├── package.json       Root convenience scripts
└── .env.example       Demo-friendly defaults
```

## Author & License

**Author / copyright holder:** Arpit Sahu.

Copyright (c) 2026 Arpit Sahu. All rights reserved. Released under the
[MIT License](LICENSE) — see [`LICENSE`](LICENSE) and [`AUTHORS`](AUTHORS).
