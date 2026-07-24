# CareerForge AI — Known Issues & Limitations

> An honest list of the limitations of the flagship vertical slice. None of these are bugs
> to hide — they are the deliberate boundary between what this slice proves and what a later
> phase builds. See [`IMPLEMENTATION_STATUS.md`](IMPLEMENTATION_STATUS.md) for the full
> REAL/SIMULATED/NOT-YET-WIRED map and [`NEXT_PHASE.md`](NEXT_PHASE.md) for how each is
> resolved.

---

## Mission & analysis

- **The mission is a scripted simulation.** `POST /repositories/analyze` does not clone or
  analyze the URL you provide. It runs a deterministic, pre-authored event sequence. Any
  repo URL produces the same findings and candidates (the repo slug is substituted into
  labels/paths for realism). The event *shapes* are contract-accurate; the *analysis* is
  not real.
- **No real model calls.** No LLM or embedding model is invoked. The Model Gateway is
  specced but not wired; `/system/health` reports `ollama: "mock"`.
- **Findings are not derived from code.** They are illustrative (an unpinned dependency, a
  high-complexity untested function) chosen to exercise the full UI, including a HIGH-severity
  finding and both an ACCEPTED and a REJECTED candidate.
- **No real runtime reproduction.** `reproduction_status: "REPRODUCED"` in the demo is
  scripted; no sandbox executes anything. `repository_execution` is `false`.

## Persistence & state

- **In-memory store only.** Missions live in process memory. Restarting the backend loses
  all missions; there is no PostgreSQL persistence yet. SSE replay works within a process
  lifetime, not across restarts.
- **No multi-user auth.** There is a single seeded demo profile (Ada Lovelace). There is no
  authentication, no accounts, and no true per-user data isolation enforced by a database —
  the per-mission scoping exists in the store surface but is not persisted.
- **Resource gauges are host-derived, not per-mission.** `/system/resources` reports real
  host CPU/RAM via psutil plus a derived active-agent count; it is not a precise accounting
  of simulated agent work.

## Integrations not present

- **No RAG / Qdrant.** No vector store, embeddings, or retrieval. Findings do not cite
  retrieved context.
- **No real GitHub client.** No clone, no issues/PR reads, and (by design) no writes. The
  approval flow only saves a draft locally; `github_write` is always `false`.
- **No LangGraph / Temporal.** Orchestration is simulated; there is no durable workflow, no
  restart-survivability, and no real human-approval timer.
- **No observability sinks.** Langfuse/Prometheus/Grafana are provided only in the optional
  `docker-compose.yml`; nothing traces or scrapes in demo mode.

## Frontend

- **3D constellation requires WebGL.** The Skill Constellation uses React-Three-Fiber. On
  machines without WebGL (or with Performance Mode enabled) it falls back to an accessible
  table — this is intended, but the 3D experience is unavailable there.
- **Fallback mock can mask backend outages.** If the backend is unreachable, the frontend
  quietly uses the bundled client-side mock so the UI is never dead. This is deliberate for
  demos but means a stopped backend may not be obvious from the UI alone (check
  `/system/health`).
- **Heavy motion.** The design is intentionally motion-rich. Users sensitive to motion should
  rely on `prefers-reduced-motion` (honored) and Performance Mode.

## Platform & tooling

- **`make` is Unix-oriented.** The `Makefile` targets assume a POSIX shell and `.venv/bin`.
  Windows users should use `scripts/setup.ps1` and `scripts/dev.ps1` instead.
- **PowerShell execution policy.** `scripts/*.ps1` may be blocked by the default execution
  policy; run them with `-ExecutionPolicy Bypass` (documented in the README).
- **The optional docker-compose stack is not integration-tested here.** Image tags are
  pinned for reproducibility, but the full stack is a scaffold for future phases, not a
  currently-wired dependency, and Ollama is intentionally excluded (run it natively).
- **Ports are fixed by convention.** Backend `8000`, frontend `3000`. If those ports are in
  use, override `CAREERFORGE_PORT` (backend) and use `next dev -p <port>` (frontend); the
  frontend's `NEXT_PUBLIC_API_BASE` must then point at the backend's URL.

## Testing

- **21 backend tests, no frontend/e2e tests.** The backend has a contract-focused test suite
  (health, profile, full mission flow). There is no automated frontend unit/e2e test suite
  in this slice; the UI is verified manually against the live backend.
