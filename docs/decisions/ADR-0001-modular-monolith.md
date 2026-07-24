# ADR-0001 — Modular monolith over microservices

- **Status:** Accepted
- **Date:** 2026-07-24
- **Deciders:** CareerForge AI core
- **Tags:** architecture, packaging, boundaries

## Context

CareerForge AI is a **local-first** platform: the default target is a single developer's
machine running the whole system with just Python + Node. At the same time the product has
clearly separable concerns — Model Gateway, Profile Brain, Industry Pulse, Contribution
Engine, orchestration, RAG, persistence, transport (modules A–H in
[`ARCHITECTURE.md`](../ARCHITECTURE.md)). We must decide how to structure the codebase and
deployment: a set of independently deployed microservices, or a single deployable with
strong internal module boundaries.

Forces:

- Local-first + cross-platform (Windows/macOS/Linux) demand a low operational footprint.
- The demo must run with **no orchestration infrastructure** (rule #3).
- The domains are separable and will grow; we don't want a big ball of mud.
- A small team building in parallel tracks needs clear ownership seams, not network APIs
  between every module.

## Decision

Build a **modular monolith**: one backend deployable (`apps/api`, package
`careerforge_api`) and one frontend deployable (`apps/web`), with **strong internal module
boundaries** enforced by typed interfaces rather than process/network boundaries.

- Modules communicate through typed interfaces, **not shared mutable state**.
- The transport layer (`main.py`) owns HTTP + SSE only; domain logic lives in dedicated
  sibling modules (`schemas`, `config`, `hardware`, `simulation`, `seed_data`).
- Heavier capabilities (Ollama, Qdrant, Postgres, Redis, Temporal, sandbox) are **optional
  dependencies behind interfaces**, each with a mock/stub so demo mode always runs.
- The monorepo keeps `apps/api` and `apps/web` together with shared contracts in `docs/`.

## Consequences

**Positive**
- The whole system boots with two processes and no infrastructure — ideal for local-first
  and for the demo.
- Clear module seams give parallel tracks disjoint ownership without inter-service plumbing.
- Refactoring across module boundaries is a code change, not a distributed-systems problem.
- Optional-dependency-behind-interface makes the REAL→wired transition incremental (see
  [`NEXT_PHASE.md`](../NEXT_PHASE.md)) without breaking demo mode.

**Negative / trade-offs**
- No independent scaling of a single hot module; the whole backend scales together.
- Discipline is required to keep module boundaries clean (a monolith can rot into a big
  ball of mud). We mitigate with typed interfaces, no shared mutable state, and ADRs.
- Very long-running durable workflows still need Temporal (a separate concern), so we are
  not purely single-process forever — but that is orchestration, not a microservice split
  of the domain.

## Alternatives considered

- **Microservices per module.** Rejected: the operational cost (service discovery,
  inter-service auth, per-service deploys) directly contradicts the local-first, run-with-
  Python+Node requirement, for no benefit at this scale.
- **Serverless functions.** Rejected: cold starts, no good local-first story, and a poor fit
  for the long-lived streaming mission and SSE.

## Related

- [`ADR-0002`](ADR-0002-langgraph-temporal-boundary.md) — orchestration inside the monolith.
- [`ARCHITECTURE.md`](../ARCHITECTURE.md), [`MASTER_SPEC.md`](../MASTER_SPEC.md) §3.
