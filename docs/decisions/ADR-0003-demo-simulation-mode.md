# ADR-0003 — Demo/simulation mode as a first-class runtime

- **Status:** Accepted
- **Date:** 2026-07-24
- **Deciders:** CareerForge AI core
- **Tags:** demo, testing, developer-experience, cross-platform

## Context

CareerForge AI's full stack is heavy: local LLMs (Ollama), a vector store (Qdrant), a
relational database (Postgres), Redis, Temporal, and a Docker sandbox. Requiring all of
that to see the product work would make the flagship experience impossible to run on a
typical laptop, impossible to demo reliably, painful to test, and hostile to Windows
users. Yet the whole point of the slice is to show the *complete* multi-agent mission flow
end-to-end.

We need a way to run the entire flow — the agent graph, findings, competing fix candidates,
independent verification (including a rejection), and the human-approval gate — with
**nothing but Python and Node**, while keeping the door open to swap in real services later
without changing the contract or the UI.

## Decision

Make **demo mode a first-class runtime**, selected by `APP_ENV=demo`
(`CAREERFORGE_APP_ENV`, the default).

- In demo mode the backend runs a **scripted, deterministic mission simulation**
  (`simulation.py`) that advances a realistic Intake → … → Approval run and emits the
  **exact contract-shaped events** (`API_CONTRACT.md`) a real orchestrator would — over the
  **real SSE transport**, with realistic pacing.
- All external services report `"mock"` in `GET /system/health`; none are contacted.
- The simulation deliberately includes a **REJECTED** fix candidate so verification is
  visibly real, not cosmetic.
- The frontend prefers the live backend simulation but ships a **bundled client-side mock**
  (`mockMission.ts`) as a fallback, so the UI is never dead.
- The safety flags `github_writes` and `repository_execution` stay `false`; the approval
  flow saves drafts locally and always returns `github_write: false`.
- Determinism makes the simulation double as a **test fixture**: the backend's 21 tests
  drive the same engine synchronously to assert contract shapes.

## Consequences

**Positive**
- The flagship demo runs anywhere with just Python + Node — Windows included — no Docker,
  DB, or GPU. This satisfies development rule #3 and the local-first principle.
- Deterministic runs give reliable demos and reproducible CI (the same engine is the test
  fixture, so tests and the demo cannot drift apart).
- Because the simulation speaks the real contract over the real transport, the UI and the
  API surface are already correct for the real orchestrator; wiring real services (see
  [`NEXT_PHASE.md`](../NEXT_PHASE.md)) is additive, not a rewrite.
- New contributors get a working system in minutes, which lowers the barrier to
  contribution.

**Negative / trade-offs**
- **Risk of mistaking the demo for real analysis.** A scripted mission can look real. We
  mitigate this with explicit honesty: `/system/health` reports `mock`, and
  [`IMPLEMENTATION_STATUS.md`](../IMPLEMENTATION_STATUS.md) + [`KNOWN_ISSUES.md`](../KNOWN_ISSUES.md)
  state plainly what is SIMULATED.
- **The simulation must be maintained alongside the contract.** If the contract changes,
  the script must change too. Mitigated by the tests, which fail if the two drift.
- **Fallback mock can mask a stopped backend** (documented in `KNOWN_ISSUES.md`); operators
  verify liveness via `/system/health`.

## Alternatives considered

- **Require the full stack to see anything.** Rejected: unrunnable on a laptop, unreliable
  for demos, and excludes Windows-first users.
- **A purely client-side mock only (no backend).** Rejected: it would not exercise the real
  SSE transport, the contract error shape, or the reconnect/replay semantics, and would give
  a false sense that the boundary works.
- **Record-and-replay real runs.** Rejected for now: needs the real stack to produce the
  recordings in the first place, defeating the purpose; may revisit for eval fixtures later.

## Related

- [`ADR-0001`](ADR-0001-modular-monolith.md), [`ADR-0002`](ADR-0002-langgraph-temporal-boundary.md).
- [`MASTER_SPEC.md`](../MASTER_SPEC.md) §16, [`API_CONTRACT.md`](../API_CONTRACT.md) "Demo / Mock Mode".
