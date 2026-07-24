# ADR-0002 — The LangGraph / Temporal orchestration boundary

- **Status:** Accepted
- **Date:** 2026-07-24
- **Deciders:** CareerForge AI core
- **Tags:** orchestration, agents, workflows, durability

## Context

A mission is a long-lived, multi-stage process (Intake → Static → Runtime → Aggregate →
Fix → Verify → Approval) in which each stage is itself a **cyclic multi-agent computation**
(agents reasoning, calling tools, and revising within a shared scratchpad). Two very
different orchestration needs collide:

1. **In-stage:** fast, stateful, cyclic agent reasoning with a shared scratchpad. Low
   latency; no durability requirement beyond the stage; graph may loop.
2. **Across stages / over time:** durable sequencing, retries, timeouts, and a
   **human-approval wait** that can span hours or days and MUST survive process restarts.
   This is the authoritative mission lifecycle (`MissionStatus`).

Using one tool for both is a poor fit. A durable workflow engine is clumsy for tight cyclic
agent loops; an in-memory agent framework has no durability, no human-in-the-loop timers,
and no restart-survivability.

## Decision

Adopt a **two-layer orchestration** with a clear boundary:

- **LangGraph orchestrates within a single stage.** Each stage is a LangGraph subgraph:
  custom agent nodes, cyclic edges, a shared scratchpad, tool calls via the Model Gateway
  and RAG. Verifier independence is **structural** — verifier nodes are distinct from fix
  nodes and carry `verifier_of`; a fix node cannot verify its own candidate.
- **Temporal orchestrates the mission across stages and over time.** A `MissionWorkflow`
  sequences the stages (each stage is an activity that runs its LangGraph subgraph), owns
  retries/timeouts, persists the append-only event log, and models the **human-approval
  wait** as a durable signal/timer. Temporal owns the authoritative `MissionStatus`
  transitions.

**Rule of thumb: inside a stage → LangGraph; across stages and over time → Temporal.**

In the current vertical slice both layers are **simulated** by the scripted engine
(`simulation.py`), which emits exactly the contract-shaped events this boundary would
produce, so the UI and contract are already correct for the real implementation.

## Consequences

**Positive**
- Each tool is used where it is strong: LangGraph for cyclic in-memory agent reasoning,
  Temporal for durable long-lived orchestration and human-in-the-loop waits.
- The human-approval gate can pause a mission indefinitely and survive restarts.
- Event shapes are identical whether the engine is simulated or real, so wiring the real
  layers (see [`NEXT_PHASE.md`](../NEXT_PHASE.md) §5–6) does not change the frontend.
- Clean testability: LangGraph subgraphs are unit-testable in-process; the Temporal
  workflow is testable with its test framework.

**Negative / trade-offs**
- Two orchestration technologies to learn and operate (Temporal needs a server;
  `docker-compose.yml` provides it). Mitigated by demo mode requiring neither.
- The stage/subgraph seam must be kept clean so a stage's internal cycles don't leak into
  the durable layer. The boundary rule above is the guardrail.
- Slight duplication of "state" concepts (in-stage scratchpad vs durable workflow state);
  we resolve this by making the durable event log the single source of truth for anything
  the UI or a restart depends on.

## Alternatives considered

- **Temporal for everything (including in-stage agent loops).** Rejected: activities and
  signals are too coarse and high-latency for tight cyclic agent reasoning.
- **LangGraph for everything (including the mission lifecycle).** Rejected: no durability,
  no restart-survivability, and no first-class long human-wait timer.
- **A hand-rolled state machine + queue.** Rejected: reinvents retries, timeouts, and
  durable timers that Temporal already provides correctly.

## Related

- [`ADR-0001`](ADR-0001-modular-monolith.md), [`ADR-0003`](ADR-0003-demo-simulation-mode.md).
- [`ARCHITECTURE.md`](../ARCHITECTURE.md) §4, [`MASTER_SPEC.md`](../MASTER_SPEC.md) §8.
