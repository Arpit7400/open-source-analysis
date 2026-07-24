# CareerForge AI — Shared API Contract (v1)

> **This file is the single source of truth for the frontend/backend boundary.**
> Every agent building `apps/api` or `apps/web` MUST honor these shapes exactly.
> Base URL: `http://localhost:8000`. All JSON. All timestamps ISO-8601 UTC.

## Conventions

- REST prefix: `/api/v1`
- Streaming: Server-Sent Events (SSE) at `/api/v1/events/stream?mission_id=...`
- IDs are UUID strings.
- Enums are UPPER_SNAKE strings.
- Errors: `{ "error": { "code": string, "message": string, "detail": any } }` with appropriate HTTP status.

---

## Enums

```
VerificationLevel  = SELF_DECLARED | AI_INFERRED | TOOL_VERIFIED | HUMAN_REVIEWED | EXTERNALLY_VALIDATED
AgentState         = WAITING | RUNNING | COMPLETED | VERIFYING | BLOCKED | FAILED | REJECTED
Severity           = INFO | LOW | MEDIUM | HIGH | CRITICAL
FindingCategory    = ARCHITECTURE | CODE_QUALITY | DOCS_DRIFT | DEPENDENCY | TEST_QUALITY | TYPING | API_CONSISTENCY | SECURITY_SMELL | DEPRECATION | RUNTIME
ReproductionStatus = NOT_REQUIRED | PENDING | REPRODUCED | NOT_REPRODUCED
MissionStatus      = QUEUED | PLANNING | RUNNING | AWAITING_APPROVAL | COMPLETED | FAILED | CANCELLED
CandidateVerdict   = ACCEPTED | REJECTED | NO_SUBMISSION | PENDING
RiskLevel          = SAFE | LOW | MEDIUM | HIGH | BLOCKED
```

---

## System

### `GET /api/v1/system/health`
```json
{
  "status": "ok",
  "version": "1.0.0",
  "services": {
    "api": "up",
    "database": "up|down|mock",
    "qdrant": "up|down|mock",
    "redis": "up|down|mock",
    "ollama": "up|down|mock",
    "temporal": "up|down|mock"
  },
  "hardware_profile": "CPU_LOW|VRAM_8_12|VRAM_16_24|WORKSTATION",
  "flags": { "github_writes": false, "repository_execution": false }
}
```

### `GET /api/v1/system/resources`
```json
{ "cpu_percent": 34.2, "ram_used_mb": 8123, "ram_total_mb": 32768, "active_agents": 3, "max_agents": 4 }
```

---

## Profile Brain

### `GET /api/v1/profile`
```json
{
  "user_id": "uuid",
  "name": "Ada Lovelace",
  "headline": "Backend & ML engineer",
  "goals": ["Merge 3 OSS PRs", "Master RAG systems"],
  "verified_skill_count": 12,
  "merged_prs": 4,
  "evidence_count": 37
}
```

### `GET /api/v1/skills`
```json
{
  "skills": [
    {
      "id": "uuid",
      "name": "Python",
      "category": "language",
      "confidence": 0.86,
      "evidence_strength": 0.79,
      "recency": 0.9,
      "complexity": 0.7,
      "independence": 0.8,
      "verification_level": "TOOL_VERIFIED",
      "evidence_ids": ["uuid", "uuid"],
      "last_updated": "2026-07-24T10:00:00Z",
      "last_change_reason": "3 passing tests added in linked repo",
      "related_skill_ids": ["uuid"]
    }
  ]
}
```

### `GET /api/v1/skills/{id}/evidence`
```json
{ "skill_id":"uuid", "evidence": [
  { "id":"uuid","type":"COMMIT|TEST|DOC|PR|PROJECT","summary":"...","source_url":"...","verification_level":"TOOL_VERIFIED","created_at":"..." }
]}
```

### `POST /api/v1/profile/ingest-resume`  (multipart or `{ "text": "..." }`)
Returns extracted skill claims **as claims, never auto-verified**:
```json
{ "claims": [ { "skill":"Python","evidence_level":"SELF_DECLARED","raw_span":"..." } ] }
```

---

## Repositories & Analysis (the flagship flow)

### `POST /api/v1/repositories/analyze`
Request: `{ "repo_url": "https://github.com/owner/name" }`
Response: `{ "mission_id": "uuid", "status": "QUEUED" }`
> Kicks off the multi-agent mission. Client then subscribes to the SSE stream.

### `GET /api/v1/missions/{mission_id}`
```json
{
  "mission_id":"uuid",
  "repo_url":"https://github.com/owner/name",
  "status":"RUNNING",
  "created_at":"...",
  "plan": { "goal":"...", "assumptions":["..."], "success_criteria":["..."] },
  "agents": [ /* AgentNode[] */ ],
  "edges": [ /* GraphEdge[] */ ],
  "findings": [ /* Finding[] */ ],
  "candidates": [ /* Candidate[] */ ],
  "approval": { "required": true, "granted": false, "draft": { /* Draft */ } } | null
}
```

### `AgentNode`
```json
{
  "id":"static.security",
  "label":"Security Smell Agent",
  "group":"STATIC|RUNTIME|INTAKE|DUPLICATE|FIX|VERIFY|CONTROL|AGGREGATE",
  "state":"RUNNING",
  "progress":0.42,
  "result_count":3,
  "started_at":"...",
  "detail":"scanning subprocess calls",
  "verifier_of":"fix.a" | null
}
```

### `GraphEdge`
```json
{ "id":"e1", "source":"control.mission", "target":"static.security", "animated":true }
```

### `Finding`
```json
{
  "finding_id":"uuid",
  "category":"SECURITY_SMELL",
  "severity":"HIGH",
  "confidence":0.82,
  "summary":"Unpinned dependency with known advisory",
  "evidence":[ { "repo":"owner/name","commit":"abc123","path":"setup.py","start_line":10,"end_line":14,"snippet":"..." } ],
  "reproduction_required":true,
  "reproduction_status":"REPRODUCED",
  "duplicate_search_terms":["..."],
  "suggested_next_step":"Pin dependency to >=x",
  "limitations":["Only static analysis; no runtime confirmation"],
  "agent_id":"static.security"
}
```

### `Candidate`
```json
{
  "candidate_id":"uuid",
  "title":"Pin vulnerable dependency",
  "author_agent":"fix.a",
  "verdict":"ACCEPTED|REJECTED|NO_SUBMISSION|PENDING",
  "root_cause":"...",
  "risk_level":"LOW",
  "scope_files_changed":1,
  "unrelated_changes":false,
  "diff": [ { "path":"setup.py", "old":"requests==2.0", "new":"requests>=2.31", "hunk":"@@ ... @@" } ],
  "verification": [
    { "check":"regression_tests","status":"PASS|FAIL|SKIP","detail":"142 passed","verifier_agent":"verify.regression" },
    { "check":"lint","status":"PASS","detail":"ruff clean","verifier_agent":"verify.lint" }
  ],
  "verification_summary":"3/4 checks passed by independent verifiers"
}
```

### `Draft` (issue/PR draft — never auto-submitted)
```json
{ "kind":"ISSUE|PR", "title":"...", "body_markdown":"...", "target_repo":"owner/name", "submittable":false, "reason_not_submittable":"GitHub writes disabled" }
```

### `POST /api/v1/approvals/{mission_id}`
Request: `{ "decision":"APPROVE|REJECT", "note":"..." }`
Response: `{ "ok": true, "action_taken":"DRAFT_SAVED_LOCALLY", "github_write": false }`

---

## Industry Pulse

### `GET /api/v1/pulse`
```json
{ "items": [
  { "id":"uuid","title":"...","source":"arXiv|GitHub|Blog|Advisory","technology":"...",
    "published_at":"...","momentum":0.8,"personal_relevance":0.6,"actionability":0.7,
    "why_it_matters":"...","skill_gap":"...","suggested_action":"...","canonical_url":"..." }
]}
```

---

## SSE Event Stream

`GET /api/v1/events/stream?mission_id=uuid`  → `text/event-stream`

Each event: `event: <type>\ndata: <json>\n\n`

Event types & payloads:
```
mission.status   -> { "mission_id":"uuid", "status":"RUNNING" }
agent.update     -> AgentNode  (full node, replace by id)
edge.update      -> GraphEdge
finding.new      -> Finding
candidate.update -> Candidate
log              -> { "ts":"...", "level":"INFO|WARN|ERROR", "agent_id":"...", "message":"..." }
resource         -> { "cpu_percent":..,"ram_used_mb":.., "active_agents":.. }
approval.required-> { "mission_id":"uuid", "draft": Draft }
mission.complete -> { "mission_id":"uuid", "status":"COMPLETED" }
```

Client reconnect: SSE `Last-Event-ID` header supported; server replays from event id.

---

## Demo / Mock Mode

`APP_ENV=demo` (default when no DB/services): the backend runs a **scripted, realistic mission simulation** so the whole flow is live without Docker/Ollama. Same shapes, same SSE, deterministic-but-timed. This is what makes the flagship demo runnable cross-platform (Windows included) with just Python + Node.
