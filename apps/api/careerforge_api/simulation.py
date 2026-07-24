"""CareerForge AI — Scripted realistic mission-simulation engine.

This module powers the flagship multi-agent repository-analysis flow in
``APP_ENV=demo`` mode (the default when no DB / Ollama / Temporal services are
present).  It produces a *believable* multi-agent timeline — the same JSON
shapes and SSE event types defined in ``docs/API_CONTRACT.md`` — without any
external dependency, so the whole product is live and cross-platform (Windows,
macOS, Linux) with just Python + Node.

Design goals
------------
* **Deterministic per ``repo_url``** — findings, candidates, commit hashes and
  verification outcomes are derived from a hash of the repo URL, so the same
  URL always tells the same story, while different URLs vary.  We never use
  ``random`` seeded from system entropy; a private ``random.Random`` instance
  is seeded from the URL hash.
* **Realistic timing** — the mission is a strictly ordered sequence of
  ``(event_type, payload)`` steps.  The FastAPI runner appends one step at a
  time with a short delay between appends, so the SSE stream animates.  A
  convenience async generator :meth:`MissionSimulator.run` is also provided
  (with its own ``asyncio.sleep`` pacing) for direct/live consumption and tests.
* **Shared state** — a :class:`MissionStore` holds the live snapshot (agents,
  edges, findings, candidates, status, plan, approval) keyed by ``mission_id``
  so the ``GET /missions/{id}`` snapshot endpoint and the SSE stream agree.
* **Replayable** — every appended event gets a monotonic integer id so a
  reconnecting SSE client can resume from ``Last-Event-ID``.

Integration surface (consumed by ``careerforge_api.main``)
----------------------------------------------------------
``MissionStore``
    ``create(repo_url) -> mission_id``, ``exists``, ``is_complete``,
    ``mark_complete``, ``append(mission_id, event_type, payload) -> int``,
    ``events_since(mission_id, last_event_id)``, ``last_event_id``,
    ``snapshot(mission_id)``, ``set_approval(mission_id, granted)``,
    ``active_agent_count()``.
``MissionSimulator(store, mission_id, repo_url)``
    ``script()`` / ``steps()`` — synchronous list of ``(event_type, payload)``
    tuples describing the whole mission (the runner appends + paces these);
    ``run()`` — async generator that both folds events into the store and
    yields them, with built-in delays.
``build_snapshot(store, mission_id)`` / ``build_mission_snapshot(record)``
    Assemble the full Mission object for ``GET /missions/{id}``.

Everything emitted here is a plain ``dict`` matching the contract's JSON shapes
exactly, using the canonical enum *string* values.  The enums are imported from
``careerforge_api.schemas`` when available; if that sibling module has not been
created yet (tracks build in parallel) we fall back to a local mirror with
byte-identical string values so this module is always importable and runnable.
"""

from __future__ import annotations

import asyncio
import hashlib
import random
import threading
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

# ---------------------------------------------------------------------------
# Enum imports (with a byte-identical local fallback).
#
# The authoritative enums live in ``careerforge_api.schemas`` (another track).
# We import their *values* through thin string constants so the rest of this
# module never depends on the enum classes themselves — only on the exact
# UPPER_SNAKE strings, which are frozen by the contract.
# ---------------------------------------------------------------------------
try:  # pragma: no cover - exercised only when the sibling module exists
    from careerforge_api.schemas import (
        AgentState,
        CandidateVerdict,
        FindingCategory,
        MissionStatus,
        ReproductionStatus,
        RiskLevel,
        Severity,
    )

    def _v(member: Any) -> str:
        """Return the canonical string value of an enum member or raw string."""
        return str(getattr(member, "value", member))

    _HAVE_SCHEMAS = True
except Exception:  # pragma: no cover - fallback when schemas not yet present
    _HAVE_SCHEMAS = False

    def _v(member: Any) -> str:
        return str(member)

    class AgentState:  # type: ignore
        WAITING = "WAITING"
        RUNNING = "RUNNING"
        COMPLETED = "COMPLETED"
        VERIFYING = "VERIFYING"
        BLOCKED = "BLOCKED"
        FAILED = "FAILED"
        REJECTED = "REJECTED"

    class Severity:  # type: ignore
        INFO = "INFO"
        LOW = "LOW"
        MEDIUM = "MEDIUM"
        HIGH = "HIGH"
        CRITICAL = "CRITICAL"

    class FindingCategory:  # type: ignore
        ARCHITECTURE = "ARCHITECTURE"
        CODE_QUALITY = "CODE_QUALITY"
        DOCS_DRIFT = "DOCS_DRIFT"
        DEPENDENCY = "DEPENDENCY"
        TEST_QUALITY = "TEST_QUALITY"
        TYPING = "TYPING"
        API_CONSISTENCY = "API_CONSISTENCY"
        SECURITY_SMELL = "SECURITY_SMELL"
        DEPRECATION = "DEPRECATION"
        RUNTIME = "RUNTIME"

    class ReproductionStatus:  # type: ignore
        NOT_REQUIRED = "NOT_REQUIRED"
        PENDING = "PENDING"
        REPRODUCED = "REPRODUCED"
        NOT_REPRODUCED = "NOT_REPRODUCED"

    class MissionStatus:  # type: ignore
        QUEUED = "QUEUED"
        PLANNING = "PLANNING"
        RUNNING = "RUNNING"
        AWAITING_APPROVAL = "AWAITING_APPROVAL"
        COMPLETED = "COMPLETED"
        FAILED = "FAILED"
        CANCELLED = "CANCELLED"

    class CandidateVerdict:  # type: ignore
        ACCEPTED = "ACCEPTED"
        REJECTED = "REJECTED"
        NO_SUBMISSION = "NO_SUBMISSION"
        PENDING = "PENDING"

    class RiskLevel:  # type: ignore
        SAFE = "SAFE"
        LOW = "LOW"
        MEDIUM = "MEDIUM"
        HIGH = "HIGH"
        BLOCKED = "BLOCKED"


# ---------------------------------------------------------------------------
# SSE event-type constants (mirror the contract exactly).
# ---------------------------------------------------------------------------
EVT_MISSION_STATUS = "mission.status"
EVT_AGENT_UPDATE = "agent.update"
EVT_EDGE_UPDATE = "edge.update"
EVT_FINDING_NEW = "finding.new"
EVT_CANDIDATE_UPDATE = "candidate.update"
EVT_LOG = "log"
EVT_RESOURCE = "resource"
EVT_APPROVAL_REQUIRED = "approval.required"
EVT_MISSION_COMPLETE = "mission.complete"


# Agent groups (mirror the AgentNode.group union in the contract).
GROUP_CONTROL = "CONTROL"
GROUP_INTAKE = "INTAKE"
GROUP_STATIC = "STATIC"
GROUP_RUNTIME = "RUNTIME"
GROUP_AGGREGATE = "AGGREGATE"
GROUP_DUPLICATE = "DUPLICATE"
GROUP_FIX = "FIX"
GROUP_VERIFY = "VERIFY"


def _now() -> str:
    """Current UTC time as an ISO-8601 string with a trailing ``Z``."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _short_hash(*parts: str) -> str:
    """Deterministic short hex digest for ids / commit shas."""
    return hashlib.sha1("::".join(parts).encode("utf-8")).hexdigest()


def _uuid_like(rng: random.Random) -> str:
    """A deterministic UUID-v4-shaped string from a seeded RNG.

    We build the 32 hex chars from the seeded RNG so ids are stable per
    ``repo_url`` (real ``uuid4`` would break determinism).
    """
    hexchars = "0123456789abcdef"
    raw = [rng.choice(hexchars) for _ in range(32)]
    # Force version 4 and RFC-4122 variant so it looks like a real UUID.
    raw[12] = "4"
    raw[16] = rng.choice("89ab")
    s = "".join(raw)
    return f"{s[0:8]}-{s[8:12]}-{s[12:16]}-{s[16:20]}-{s[20:32]}"


def _repo_slug(repo_url: str) -> str:
    """Extract ``owner/name`` from a GitHub-style URL, defensively."""
    cleaned = repo_url.strip().rstrip("/")
    if cleaned.endswith(".git"):
        cleaned = cleaned[: -len(".git")]
    parts = [p for p in cleaned.replace("https://", "").replace("http://", "").split("/") if p]
    # parts like ["github.com", "owner", "name"]
    if len(parts) >= 3:
        return f"{parts[-2]}/{parts[-1]}"
    if len(parts) == 2:
        return f"{parts[-2]}/{parts[-1]}"
    if parts:
        return f"unknown/{parts[-1]}"
    return "unknown/repository"


# ---------------------------------------------------------------------------
# In-memory, thread- & async-safe mission store with a per-mission replay
# buffer.  The public method names mirror what ``careerforge_api.main`` calls.
# ---------------------------------------------------------------------------
class MissionRecord:
    """Live state for a single mission plus its ordered event buffer."""

    def __init__(self, mission_id: str, repo_url: str, created_at: str) -> None:
        self.mission_id = mission_id
        self.repo_url = repo_url
        self.created_at = created_at
        self.status: str = _v(MissionStatus.QUEUED)
        self.plan: dict[str, Any] | None = None
        # Ordered dicts keyed by id so re-emits replace by id (contract note).
        self.agents: dict[str, dict[str, Any]] = {}
        self.edges: dict[str, dict[str, Any]] = {}
        self.findings: dict[str, dict[str, Any]] = {}
        self.candidates: dict[str, dict[str, Any]] = {}
        self.approval: dict[str, Any] | None = None
        # Replay buffer: list of (event_id:int, event_type:str, payload:dict).
        self.buffer: list[tuple[int, str, dict[str, Any]]] = []
        self.counter: int = 0
        self.complete: bool = False


class MissionStore:
    """Process-wide, thread- & async-safe registry of missions.

    ``main`` runs the simulation from a background ``asyncio`` task while REST
    handlers and the SSE generator read concurrently.  All mutation and reads go
    through a single ``threading.RLock`` (works whether called from an event
    loop or a worker thread, e.g. the sync test helper).
    """

    def __init__(self) -> None:
        self._missions: dict[str, MissionRecord] = {}
        self._lock = threading.RLock()

    # -- lifecycle ---------------------------------------------------------
    def create(self, repo_url: str, mission_id: str | None = None) -> str:
        """Create a mission, returning its (generated) id.

        ``mission_id`` may be supplied for deterministic tests; otherwise a
        fresh UUID string is generated.
        """
        with self._lock:
            mid = mission_id or str(uuid.uuid4())
            self._missions[mid] = MissionRecord(mid, repo_url, _now())
            return mid

    # Alias kept for symmetry with older callers.
    def create_mission(self, mission_id: str, repo_url: str) -> MissionRecord:
        with self._lock:
            record = MissionRecord(mission_id, repo_url, _now())
            self._missions[mission_id] = record
            return record

    def exists(self, mission_id: str) -> bool:
        with self._lock:
            return mission_id in self._missions

    def is_complete(self, mission_id: str) -> bool:
        with self._lock:
            record = self._missions.get(mission_id)
            return bool(record and record.complete)

    def mark_complete(self, mission_id: str) -> None:
        with self._lock:
            record = self._missions.get(mission_id)
            if record is not None:
                record.complete = True

    def get(self, mission_id: str) -> MissionRecord | None:
        with self._lock:
            return self._missions.get(mission_id)

    def repo_url(self, mission_id: str) -> str | None:
        with self._lock:
            record = self._missions.get(mission_id)
            return record.repo_url if record is not None else None

    # -- events ------------------------------------------------------------
    def append(self, mission_id: str, event_type: str, payload: dict[str, Any]) -> int:
        """Fold an event into live state and buffer it; return its id.

        The assigned id is a monotonic integer (per mission) so the SSE layer
        can serialize it as ``Last-Event-ID`` and replay deterministically.
        """
        with self._lock:
            record = self._missions.get(mission_id)
            if record is None:
                raise KeyError(f"Unknown mission_id: {mission_id}")
            record.counter += 1
            event_id = record.counter
            record.buffer.append((event_id, event_type, payload))
            self._apply(record, event_type, payload)
            return event_id

    def events_since(
        self, mission_id: str, last_event_id: int
    ) -> list[tuple[int, str, dict[str, Any]]]:
        """Return buffered events with id strictly greater than ``last_event_id``."""
        with self._lock:
            record = self._missions.get(mission_id)
            if record is None:
                return []
            return [e for e in record.buffer if e[0] > last_event_id]

    def last_event_id(self, mission_id: str) -> int:
        with self._lock:
            record = self._missions.get(mission_id)
            return record.counter if record is not None else 0

    # -- snapshot ----------------------------------------------------------
    def snapshot(self, mission_id: str) -> dict[str, Any] | None:
        """Return the full Mission object (contract shape) or ``None``."""
        with self._lock:
            record = self._missions.get(mission_id)
            if record is None:
                return None
            return build_mission_snapshot(record)

    def set_approval(self, mission_id: str, granted: bool) -> None:
        with self._lock:
            record = self._missions.get(mission_id)
            if record is None or record.approval is None:
                return
            record.approval = {
                "required": True,
                "granted": granted,
                "draft": record.approval.get("draft"),
            }
            # Move the mission to a terminal state once a human decides.
            record.status = _v(MissionStatus.COMPLETED) if granted else _v(MissionStatus.CANCELLED)
            record.complete = True

    def set_plan(self, mission_id: str, plan: dict[str, Any]) -> None:
        with self._lock:
            record = self._missions.get(mission_id)
            if record is not None:
                record.plan = plan

    def active_agent_count(self) -> int:
        """Number of RUNNING/VERIFYING agents across all in-flight missions."""
        active_states = {_v(AgentState.RUNNING), _v(AgentState.VERIFYING)}
        with self._lock:
            total = 0
            for record in self._missions.values():
                for agent in record.agents.values():
                    if agent.get("state") in active_states:
                        total += 1
            return total

    # -- internal fold -----------------------------------------------------
    def _apply(self, record: MissionRecord, event_type: str, payload: dict[str, Any]) -> None:
        if event_type == EVT_MISSION_STATUS:
            record.status = payload["status"]
        elif event_type == EVT_MISSION_COMPLETE:
            record.status = payload["status"]
            record.complete = True
        elif event_type == EVT_AGENT_UPDATE:
            record.agents[payload["id"]] = payload
        elif event_type == EVT_EDGE_UPDATE:
            record.edges[payload["id"]] = payload
        elif event_type == EVT_FINDING_NEW:
            record.findings[payload["finding_id"]] = payload
        elif event_type == EVT_CANDIDATE_UPDATE:
            record.candidates[payload["candidate_id"]] = payload
        elif event_type == EVT_APPROVAL_REQUIRED:
            record.approval = {
                "required": True,
                "granted": False,
                "draft": payload["draft"],
            }
        # ``log`` and ``resource`` events carry no persistent snapshot state;
        # they live only in the replay buffer.


# Process-wide singleton store.
_STORE: MissionStore | None = None


def get_store() -> MissionStore:
    """Return the process-wide :class:`MissionStore` singleton."""
    global _STORE
    if _STORE is None:
        _STORE = MissionStore()
    return _STORE


# ---------------------------------------------------------------------------
# Deterministic content generation (findings + candidates) per repo_url.
# ---------------------------------------------------------------------------
# A small library of realistic Python-repo finding templates.  The simulator
# picks a deterministic subset per repo so different URLs surface a believable
# but varied analysis.  Each template renders like a real static/runtime pass.
_FINDING_TEMPLATES: list[dict[str, Any]] = [
    {
        "key": "unpinned_requests",
        "category": _v(FindingCategory.DEPENDENCY),
        "severity": _v(Severity.HIGH),
        "confidence": 0.88,
        "agent_id": "static.dependency",
        "summary": "Unpinned `requests` dependency exposes build to a known advisory (GHSA-j8r2-6x86-q33q).",
        "path": "setup.py",
        "start_line": 22,
        "end_line": 27,
        "snippet": ('install_requires=[\n    "requests",\n    "click>=8.0",\n    "pyyaml",\n],'),
        "reproduction_required": True,
        "reproduction_status": _v(ReproductionStatus.REPRODUCED),
        "duplicate_search_terms": [
            "requests unpinned",
            "GHSA-j8r2-6x86-q33q",
            "install_requires requests",
        ],
        "suggested_next_step": "Pin to `requests>=2.32.0` in setup.py / pyproject and regenerate the lockfile.",
        "limitations": ["Static dependency scan; advisory reachability not confirmed at runtime."],
    },
    {
        "key": "subprocess_shell",
        "category": _v(FindingCategory.SECURITY_SMELL),
        "severity": _v(Severity.HIGH),
        "confidence": 0.83,
        "agent_id": "static.security_smell",
        "summary": "`subprocess.run(..., shell=True)` with an interpolated argument enables shell injection.",
        "path": "src/pipeline/runner.py",
        "start_line": 74,
        "end_line": 79,
        "snippet": (
            'cmd = f"git clone {repo_url} {dest}"\n'
            "subprocess.run(cmd, shell=True, check=True)\n"
            "# NOTE: repo_url originates from an HTTP request body"
        ),
        "reproduction_required": True,
        "reproduction_status": _v(ReproductionStatus.REPRODUCED),
        "duplicate_search_terms": [
            "subprocess shell=True",
            "shell injection git clone",
            "runner.py subprocess",
        ],
        "suggested_next_step": "Pass an argv list (`shell=False`) and validate/allowlist the URL before use.",
        "limitations": [
            "Taint traced statically; only reproduced in the isolated sandbox, not production config."
        ],
    },
    {
        "key": "bare_except",
        "category": _v(FindingCategory.CODE_QUALITY),
        "severity": _v(Severity.MEDIUM),
        "confidence": 0.76,
        "agent_id": "static.code_quality",
        "summary": "Bare `except:` swallows `KeyboardInterrupt`/`SystemExit` and hides real failures in the ingest loop.",
        "path": "src/ingest/loader.py",
        "start_line": 118,
        "end_line": 123,
        "snippet": (
            "try:\n    record = parse(line)\nexcept:\n    continue  # silently drop malformed rows"
        ),
        "reproduction_required": False,
        "reproduction_status": _v(ReproductionStatus.NOT_REQUIRED),
        "duplicate_search_terms": [
            "bare except",
            "except: continue loader",
            "swallow exception ingest",
        ],
        "suggested_next_step": "Catch `Exception` (not bare) and log the dropped row with context; re-raise on control-flow signals.",
        "limitations": ["Ruff E722 heuristic; runtime frequency of malformed rows unknown."],
    },
    {
        "key": "mypy_optional",
        "category": _v(FindingCategory.TYPING),
        "severity": _v(Severity.MEDIUM),
        "confidence": 0.71,
        "agent_id": "static.typing",
        "summary": "`Optional[str]` return dereferenced without a None-guard — mypy `--strict` reports 3 errors here.",
        "path": "src/config/settings.py",
        "start_line": 41,
        "end_line": 46,
        "snippet": (
            "def token(self) -> Optional[str]:\n"
            '    return os.environ.get("CF_TOKEN")\n'
            "\n"
            'headers = {"Authorization": "Bearer " + settings.token()}'
        ),
        "reproduction_required": False,
        "reproduction_status": _v(ReproductionStatus.NOT_REQUIRED),
        "duplicate_search_terms": [
            "mypy optional none",
            "Bearer token None concat",
            "settings.token strict",
        ],
        "suggested_next_step": "Guard for None (raise a clear config error) or narrow the type before concatenation.",
        "limitations": ["Only surfaces under `mypy --strict`; default config passes."],
    },
    {
        "key": "readme_drift",
        "category": _v(FindingCategory.DOCS_DRIFT),
        "severity": _v(Severity.LOW),
        "confidence": 0.69,
        "agent_id": "runtime.docs",
        "summary": "README quickstart references a removed `--legacy` CLI flag; documented command exits non-zero.",
        "path": "README.md",
        "start_line": 63,
        "end_line": 66,
        "snippet": ("```bash\ncf-cli analyze --legacy ./repo\n```"),
        "reproduction_required": True,
        "reproduction_status": _v(ReproductionStatus.REPRODUCED),
        "duplicate_search_terms": [
            "README --legacy flag",
            "docs drift cli flag",
            "quickstart exit code",
        ],
        "suggested_next_step": "Update the quickstart to the current `cf-cli analyze ./repo` invocation and add a docs CI smoke test.",
        "limitations": [
            "Runtime doc check executed in sandbox; other doc pages not exhaustively run."
        ],
    },
    {
        "key": "deprecation_utcnow",
        "category": _v(FindingCategory.DEPRECATION),
        "severity": _v(Severity.MEDIUM),
        "confidence": 0.80,
        "agent_id": "runtime.deprecation",
        "summary": "`datetime.utcnow()` is deprecated in Python 3.12+ and emits a DeprecationWarning at runtime.",
        "path": "src/core/clock.py",
        "start_line": 9,
        "end_line": 11,
        "snippet": ("def now() -> datetime:\n    return datetime.utcnow()  # naive, deprecated"),
        "reproduction_required": True,
        "reproduction_status": _v(ReproductionStatus.REPRODUCED),
        "duplicate_search_terms": [
            "datetime.utcnow deprecated",
            "DeprecationWarning utcnow",
            "timezone.utc migration",
        ],
        "suggested_next_step": "Use `datetime.now(timezone.utc)` and make timestamps timezone-aware.",
        "limitations": [
            "Warning captured under `-W error::DeprecationWarning` in the sandbox run."
        ],
    },
    {
        "key": "flaky_test",
        "category": _v(FindingCategory.TEST_QUALITY),
        "severity": _v(Severity.MEDIUM),
        "confidence": 0.66,
        "agent_id": "runtime.test",
        "summary": "`test_scheduler_ordering` is order-dependent — fails under `pytest -p no:randomly` reversal.",
        "path": "tests/test_scheduler.py",
        "start_line": 88,
        "end_line": 94,
        "snippet": (
            "def test_scheduler_ordering():\n"
            "    # relies on GLOBAL_QUEUE mutated by a previous test\n"
            '    assert GLOBAL_QUEUE.pop() == "task-a"'
        ),
        "reproduction_required": True,
        "reproduction_status": _v(ReproductionStatus.NOT_REPRODUCED),
        "duplicate_search_terms": [
            "flaky test order dependent",
            "GLOBAL_QUEUE shared state",
            "pytest randomly",
        ],
        "suggested_next_step": "Isolate state with a fixture and remove the module-level `GLOBAL_QUEUE` mutation.",
        "limitations": [
            "Could not reproduce deterministically in 20 sandbox runs; suspected timing-sensitive."
        ],
    },
    {
        "key": "layering_violation",
        "category": _v(FindingCategory.ARCHITECTURE),
        "severity": _v(Severity.MEDIUM),
        "confidence": 0.72,
        "agent_id": "static.architecture",
        "summary": "Domain layer imports the web framework — `models.py` imports `fastapi`, inverting the dependency rule.",
        "path": "src/domain/models.py",
        "start_line": 3,
        "end_line": 5,
        "snippet": (
            "from fastapi import HTTPException  # domain should not know transport\n"
            "\n"
            "class Skill(BaseModel): ..."
        ),
        "reproduction_required": False,
        "reproduction_status": _v(ReproductionStatus.NOT_REQUIRED),
        "duplicate_search_terms": [
            "domain imports fastapi",
            "layering violation HTTPException",
            "dependency inversion",
        ],
        "suggested_next_step": "Raise a domain-specific error and translate to HTTP in the transport layer.",
        "limitations": ["Import-graph heuristic; a few dynamic imports were not resolved."],
    },
    {
        "key": "api_inconsistency",
        "category": _v(FindingCategory.API_CONSISTENCY),
        "severity": _v(Severity.LOW),
        "confidence": 0.64,
        "agent_id": "static.api_consistency",
        "summary": "Endpoint mixes `snake_case` and `camelCase` keys in the response body vs. the rest of the API.",
        "path": "src/api/routes/reports.py",
        "start_line": 55,
        "end_line": 60,
        "snippet": (
            "return {\n"
            '    "reportId": rid,        # camelCase\n'
            '    "created_at": ts,       # snake_case elsewhere\n'
            "}"
        ),
        "reproduction_required": False,
        "reproduction_status": _v(ReproductionStatus.NOT_REQUIRED),
        "duplicate_search_terms": [
            "camelCase snake_case mix",
            "reportId inconsistent",
            "api naming convention",
        ],
        "suggested_next_step": "Normalize to snake_case (or add a response model with aliases) and add a schema lint check.",
        "limitations": ["Sampled 12 endpoints; not a full OpenAPI diff."],
    },
]


def _pick_findings(rng: random.Random, repo_slug: str) -> list[dict[str, Any]]:
    """Deterministically select and materialize 4-6 findings for a repo."""
    templates = list(_FINDING_TEMPLATES)
    rng.shuffle(templates)
    count = rng.randint(4, 6)
    chosen = templates[:count]
    findings: list[dict[str, Any]] = []
    for tmpl in chosen:
        commit = _short_hash(repo_slug, tmpl["key"])[:10]
        finding_id = _uuid_like(rng)
        findings.append(
            {
                "finding_id": finding_id,
                "category": tmpl["category"],
                "severity": tmpl["severity"],
                "confidence": tmpl["confidence"],
                "summary": tmpl["summary"],
                "evidence": [
                    {
                        "repo": repo_slug,
                        "commit": commit,
                        "path": tmpl["path"],
                        "start_line": tmpl["start_line"],
                        "end_line": tmpl["end_line"],
                        "snippet": tmpl["snippet"],
                    }
                ],
                "reproduction_required": tmpl["reproduction_required"],
                "reproduction_status": tmpl["reproduction_status"],
                "duplicate_search_terms": tmpl["duplicate_search_terms"],
                "suggested_next_step": tmpl["suggested_next_step"],
                "limitations": tmpl["limitations"],
                "agent_id": tmpl["agent_id"],
                # Internal bookkeeping (not part of the wire shape but harmless).
                "_key": tmpl["key"],
            }
        )
    return findings


def _build_candidates(
    rng: random.Random, repo_slug: str, findings: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Deterministically build 2-3 candidates.

    Guarantees at least one ACCEPTED (ends AWAITING_APPROVAL with a draft) and
    at least one REJECTED (by an independent verifier), optionally a
    NO_SUBMISSION from the NO_FIX critic.
    """
    by_key = {f["_key"]: f for f in findings}

    def _first_present(keys: list[str]) -> dict[str, Any] | None:
        for k in keys:
            if k in by_key:
                return by_key[k]
        return None

    candidates: list[dict[str, Any]] = []

    # ---- ACCEPTED candidate (prefer the dependency-pinning fix) ----
    dep = _first_present(["unpinned_requests", "deprecation_utcnow", "bare_except"])
    if dep is None:
        dep = findings[0]
    accepted = _make_accepted_candidate(rng, repo_slug, dep)
    candidates.append(accepted)

    # ---- REJECTED candidate (a fix that breaks the build / over-reaches) ----
    rej_source = _first_present(
        ["subprocess_shell", "flaky_test", "layering_violation", "readme_drift"]
    )
    if rej_source is None or rej_source is dep:
        others = [f for f in findings if f is not dep]
        rej_source = others[0] if others else dep
    rejected = _make_rejected_candidate(rng, repo_slug, rej_source)
    candidates.append(rejected)

    # ---- Optional NO_SUBMISSION from the NO_FIX critic ----
    if rng.random() < 0.7:
        critic_source = _first_present(["flaky_test", "api_inconsistency", "mypy_optional"])
        if critic_source is None:
            critic_source = findings[-1]
        candidates.append(_make_no_submission_candidate(rng, repo_slug, critic_source))

    return candidates


def _make_accepted_candidate(
    rng: random.Random, repo_slug: str, finding: dict[str, Any]
) -> dict[str, Any]:
    key = finding["_key"]
    if key == "unpinned_requests":
        title = "Pin `requests` to a patched release"
        root_cause = (
            "`requests` was declared without a version specifier, so builds could resolve to a "
            "release affected by GHSA-j8r2-6x86-q33q."
        )
        diff = [
            {
                "path": "setup.py",
                "old": '    "requests",',
                "new": '    "requests>=2.32.0",',
                "hunk": "@@ -22,7 +22,7 @@ install_requires=[",
            }
        ]
    elif key == "deprecation_utcnow":
        title = "Replace deprecated `datetime.utcnow()` with timezone-aware call"
        root_cause = (
            "`datetime.utcnow()` returns a naive datetime and is deprecated on Python 3.12+, "
            "emitting a DeprecationWarning."
        )
        diff = [
            {
                "path": "src/core/clock.py",
                "old": "    return datetime.utcnow()  # naive, deprecated",
                "new": "    return datetime.now(timezone.utc)",
                "hunk": "@@ -9,3 +9,3 @@ def now() -> datetime:",
            }
        ]
    else:  # bare_except or any fallback
        title = "Narrow bare `except:` and log dropped rows"
        root_cause = (
            "A bare `except:` swallowed all exceptions (including control-flow signals) and "
            "silently discarded malformed input."
        )
        diff = [
            {
                "path": "src/ingest/loader.py",
                "old": "    except:\n        continue  # silently drop malformed rows",
                "new": (
                    "    except Exception as exc:\n"
                    '        logger.warning("dropping malformed row: %s", exc)\n'
                    "        continue"
                ),
                "hunk": "@@ -118,4 +118,5 @@ for line in stream:",
            }
        ]

    verification = [
        {
            "check": "regression_tests",
            "status": "PASS",
            "detail": "142 passed, 0 failed (pytest -q)",
            "verifier_agent": "verify.regression",
        },
        {
            "check": "lint",
            "status": "PASS",
            "detail": "ruff clean (0 findings)",
            "verifier_agent": "verify.lint",
        },
        {
            "check": "type_check",
            "status": "PASS",
            "detail": "mypy: no new errors introduced",
            "verifier_agent": "verify.types",
        },
        {
            "check": "scope_guard",
            "status": "PASS",
            "detail": "single-file, no unrelated changes detected",
            "verifier_agent": "verify.scope",
        },
    ]
    passed = sum(1 for v in verification if v["status"] == "PASS")
    return {
        "candidate_id": _uuid_like(rng),
        "title": title,
        "author_agent": "fix.a",
        "verdict": _v(CandidateVerdict.ACCEPTED),
        "root_cause": root_cause,
        "risk_level": _v(RiskLevel.LOW),
        "scope_files_changed": 1,
        "unrelated_changes": False,
        "diff": diff,
        "verification": verification,
        "verification_summary": f"{passed}/{len(verification)} checks passed by independent verifiers.",
        "_finding_key": key,
        "_source_finding_id": finding["finding_id"],
    }


def _make_rejected_candidate(
    rng: random.Random, repo_slug: str, finding: dict[str, Any]
) -> dict[str, Any]:
    key = finding["_key"]
    if key == "subprocess_shell":
        title = "Refactor subprocess call to argv list"
        root_cause = (
            "`shell=True` with an interpolated URL allowed shell injection; the fix switched to an "
            "argv list but also refactored unrelated argument handling."
        )
        diff = [
            {
                "path": "src/pipeline/runner.py",
                "old": '    cmd = f"git clone {repo_url} {dest}"\n    subprocess.run(cmd, shell=True, check=True)',
                "new": '    subprocess.run(["git", "clone", repo_url, dest], check=True)\n    _rewrite_arg_parser()  # unrelated',
                "hunk": "@@ -74,6 +74,7 @@ def clone(repo_url: str, dest: str) -> None:",
            }
        ]
        fail_detail = (
            "2 failed: test_clone_retry, test_arg_parser (unrelated refactor broke retry path)"
        )
    else:
        title = f"Speculative fix for: {finding['summary'][:48]}"
        root_cause = (
            "The candidate attempted a broad rewrite that touched multiple modules and changed "
            "public behavior beyond the reported finding."
        )
        diff = [
            {
                "path": finding["evidence"][0]["path"],
                "old": finding["evidence"][0]["snippet"].split("\n")[0],
                "new": "# rewritten (over-scoped, touches 3 unrelated files)",
                "hunk": f"@@ -{finding['evidence'][0]['start_line']},4 +{finding['evidence'][0]['start_line']},6 @@",
            }
        ]
        fail_detail = "3 failed in unrelated suites after refactor"

    verification = [
        {
            "check": "regression_tests",
            "status": "FAIL",
            "detail": fail_detail,
            "verifier_agent": "verify.regression",
        },
        {
            "check": "lint",
            "status": "PASS",
            "detail": "ruff clean (0 findings)",
            "verifier_agent": "verify.lint",
        },
        {
            "check": "scope_guard",
            "status": "FAIL",
            "detail": "touched 3 files; unrelated changes detected",
            "verifier_agent": "verify.scope",
        },
        {
            "check": "type_check",
            "status": "SKIP",
            "detail": "skipped: regression gate failed first",
            "verifier_agent": "verify.types",
        },
    ]
    passed = sum(1 for v in verification if v["status"] == "PASS")
    return {
        "candidate_id": _uuid_like(rng),
        "title": title,
        "author_agent": "fix.b",
        "verdict": _v(CandidateVerdict.REJECTED),
        "root_cause": root_cause,
        "risk_level": _v(RiskLevel.HIGH),
        "scope_files_changed": 3,
        "unrelated_changes": True,
        "diff": diff,
        "verification": verification,
        "verification_summary": (
            f"{passed}/{len(verification)} checks passed — REJECTED by verify.regression "
            "and verify.scope (independent of author fix.b)."
        ),
        "_finding_key": key,
        "_source_finding_id": finding["finding_id"],
    }


def _make_no_submission_candidate(
    rng: random.Random, repo_slug: str, finding: dict[str, Any]
) -> dict[str, Any]:
    return {
        "candidate_id": _uuid_like(rng),
        "title": f"NO_FIX: insufficient evidence to safely fix — {finding['category']}",
        "author_agent": "fix.critic",
        "verdict": _v(CandidateVerdict.NO_SUBMISSION),
        "root_cause": (
            "The NO_FIX critic determined the finding is real but not confidently auto-fixable: the "
            "reproduction was not deterministic, so any patch would be speculative. Recommending a "
            "human-authored change instead of an automated candidate."
        ),
        "risk_level": _v(RiskLevel.MEDIUM),
        "scope_files_changed": 0,
        "unrelated_changes": False,
        "diff": [],
        "verification": [
            {
                "check": "reproduction_gate",
                "status": "FAIL",
                "detail": "finding not reproduced deterministically; auto-fix withheld",
                "verifier_agent": "verify.reproduction",
            }
        ],
        "verification_summary": "No submission: reproduction gate not satisfied; deferred to human review.",
        "_finding_key": finding["_key"],
        "_source_finding_id": finding["finding_id"],
    }


def _build_draft(repo_slug: str, candidate: dict[str, Any]) -> dict[str, Any]:
    """Build a submittable:false PR draft for an accepted candidate."""
    diff_blocks = []
    for d in candidate["diff"]:
        diff_blocks.append(
            f"**`{d['path']}`**\n\n```diff\n{d['hunk']}\n- {d['old']}\n+ {d['new']}\n```"
        )
    verification_rows = "\n".join(
        f"| `{v['check']}` | {v['status']} | {v['detail']} | `{v['verifier_agent']}` |"
        for v in candidate["verification"]
    )
    body = (
        f"## {candidate['title']}\n\n"
        f"**Root cause.** {candidate['root_cause']}\n\n"
        f"**Risk level.** `{candidate['risk_level']}` · "
        f"Files changed: {candidate['scope_files_changed']} · "
        f"Unrelated changes: {'yes' if candidate['unrelated_changes'] else 'no'}\n\n"
        f"### Proposed change\n\n"
        + "\n\n".join(diff_blocks)
        + "\n\n### Independent verification\n\n"
        "| Check | Status | Detail | Verifier |\n"
        "| --- | --- | --- | --- |\n"
        f"{verification_rows}\n\n"
        f"_{candidate['verification_summary']}_\n\n"
        "---\n"
        "> Generated by CareerForge AI. Verification was performed by agents independent of the "
        "fix author. **GitHub writes are disabled**, so this draft is for human review only."
    )
    return {
        "kind": "PR",
        "title": candidate["title"],
        "body_markdown": body,
        "target_repo": repo_slug,
        "submittable": False,
        "reason_not_submittable": "GitHub writes disabled",
    }


# ---------------------------------------------------------------------------
# Agent topology.  Defines the DAG the React Flow graph renders.
# ---------------------------------------------------------------------------
def _agent_topology() -> tuple[list[dict[str, str]], list[tuple[str, str]]]:
    """Return (nodes, edges) as static topology descriptors.

    Each node descriptor: {id, label, group}.
    Each edge: (source_id, target_id).
    """
    nodes: list[dict[str, str]] = [
        # Control / planning.
        {"id": "control.mission", "label": "Mission Control", "group": GROUP_CONTROL},
        {"id": "control.planner", "label": "Planning Agent", "group": GROUP_CONTROL},
        # Intake + preflight.
        {"id": "intake.repo", "label": "Repo Intake Agent", "group": GROUP_INTAKE},
        {"id": "intake.safety", "label": "Static Safety Preflight", "group": GROUP_INTAKE},
        # Parallel static swarm.
        {"id": "static.architecture", "label": "Architecture Agent", "group": GROUP_STATIC},
        {"id": "static.code_quality", "label": "Code Quality Agent", "group": GROUP_STATIC},
        {"id": "static.docs_drift", "label": "Docs Drift Agent", "group": GROUP_STATIC},
        {"id": "static.dependency", "label": "Dependency Agent", "group": GROUP_STATIC},
        {"id": "static.test_quality", "label": "Test Quality Agent", "group": GROUP_STATIC},
        {"id": "static.typing", "label": "Typing Agent", "group": GROUP_STATIC},
        {"id": "static.api_consistency", "label": "API Consistency Agent", "group": GROUP_STATIC},
        {"id": "static.security_smell", "label": "Security Smell Agent", "group": GROUP_STATIC},
        # History + build/test plan.
        {"id": "intake.history", "label": "GitHub History Agent", "group": GROUP_INTAKE},
        {"id": "intake.build_plan", "label": "Build / Test Plan Agent", "group": GROUP_INTAKE},
        # Isolated runtime swarm.
        {"id": "runtime.test", "label": "Runtime Test Agent", "group": GROUP_RUNTIME},
        {"id": "runtime.docs", "label": "Runtime Docs Agent", "group": GROUP_RUNTIME},
        {"id": "runtime.deprecation", "label": "Deprecation Agent", "group": GROUP_RUNTIME},
        # Aggregate + duplicate.
        {"id": "aggregate.evidence", "label": "Evidence Aggregator", "group": GROUP_AGGREGATE},
        {"id": "duplicate.detector", "label": "Duplicate Detector", "group": GROUP_DUPLICATE},
        # Fix swarm.
        {"id": "fix.a", "label": "Fix Agent A", "group": GROUP_FIX},
        {"id": "fix.b", "label": "Fix Agent B", "group": GROUP_FIX},
        {"id": "fix.critic", "label": "NO_FIX Critic", "group": GROUP_FIX},
        # Independent verification swarm.
        {"id": "verify.regression", "label": "Verifier · Regression", "group": GROUP_VERIFY},
        {"id": "verify.lint", "label": "Verifier · Lint", "group": GROUP_VERIFY},
        {"id": "verify.types", "label": "Verifier · Types", "group": GROUP_VERIFY},
        {"id": "verify.scope", "label": "Verifier · Scope", "group": GROUP_VERIFY},
        {"id": "verify.reproduction", "label": "Verifier · Reproduction", "group": GROUP_VERIFY},
    ]

    static_ids = [
        "static.architecture",
        "static.code_quality",
        "static.docs_drift",
        "static.dependency",
        "static.test_quality",
        "static.typing",
        "static.api_consistency",
        "static.security_smell",
    ]
    runtime_ids = ["runtime.test", "runtime.docs", "runtime.deprecation"]
    fix_ids = ["fix.a", "fix.b", "fix.critic"]
    verify_ids = [
        "verify.regression",
        "verify.lint",
        "verify.types",
        "verify.scope",
        "verify.reproduction",
    ]

    edges: list[tuple[str, str]] = []
    edges.append(("control.mission", "control.planner"))
    edges.append(("control.planner", "intake.repo"))
    edges.append(("intake.repo", "intake.safety"))
    # Preflight fans out to the static swarm.
    for sid in static_ids:
        edges.append(("intake.safety", sid))
    # History + build plan run off intake too.
    edges.append(("intake.repo", "intake.history"))
    edges.append(("intake.history", "intake.build_plan"))
    # Runtime swarm depends on the build/test plan.
    for rid in runtime_ids:
        edges.append(("intake.build_plan", rid))
    # Everything feeds the aggregator.
    for sid in static_ids:
        edges.append((sid, "aggregate.evidence"))
    for rid in runtime_ids:
        edges.append((rid, "aggregate.evidence"))
    # Aggregate -> duplicate -> fix swarm.
    edges.append(("aggregate.evidence", "duplicate.detector"))
    for fid in fix_ids:
        edges.append(("duplicate.detector", fid))
    # Fix authors -> verifier swarm (verifiers are DIFFERENT agents).
    edges.append(("fix.a", "verify.regression"))
    edges.append(("fix.a", "verify.lint"))
    edges.append(("fix.a", "verify.types"))
    edges.append(("fix.a", "verify.scope"))
    edges.append(("fix.b", "verify.regression"))
    edges.append(("fix.b", "verify.scope"))
    edges.append(("fix.critic", "verify.reproduction"))
    # Verifiers report back up to mission control (approval gate).
    for vid in verify_ids:
        edges.append((vid, "control.mission"))

    return nodes, edges


# ``verifier_of`` mapping so the UI can badge verifiers against fix authors.
_VERIFIER_OF: dict[str, str] = {
    "verify.regression": "fix.a",
    "verify.lint": "fix.a",
    "verify.types": "fix.a",
    "verify.scope": "fix.b",
    "verify.reproduction": "fix.critic",
}


def _agent_node(
    node_id: str,
    label: str,
    group: str,
    state: str,
    progress: float,
    result_count: int = 0,
    started_at: str | None = None,
    detail: str = "",
) -> dict[str, Any]:
    """Construct an AgentNode dict matching the contract exactly."""
    return {
        "id": node_id,
        "label": label,
        "group": group,
        "state": state,
        "progress": round(progress, 3),
        "result_count": result_count,
        "started_at": started_at,
        "detail": detail,
        "verifier_of": _VERIFIER_OF.get(node_id),
    }


def _edge_payload(source: str, target: str, animated: bool) -> dict[str, Any]:
    return {
        "id": f"e:{source}->{target}",
        "source": source,
        "target": target,
        "animated": animated,
    }


# ---------------------------------------------------------------------------
# The simulator.
# ---------------------------------------------------------------------------
class MissionSimulator:
    """Build the scripted mission for ``repo_url`` and expose it two ways.

    * :meth:`script` / :meth:`steps` — a synchronous, fully materialized list of
      ``(event_type, payload)`` tuples.  ``careerforge_api.main`` appends these
      to the store one at a time with a small delay, which is what animates the
      SSE stream.  Because the list is deterministic per ``repo_url`` the demo
      is byte-stable.
    * :meth:`run` — an async generator that folds each event into the shared
      :class:`MissionStore` *and* yields it, pacing itself with
      ``asyncio.sleep`` (~150-500ms) so it can drive the UI directly.

    Both consume the same internal :meth:`_script_events` builder, so the story
    is identical regardless of how it is played back.
    """

    def __init__(
        self,
        store: MissionStore,
        mission_id: str,
        repo_url: str,
        *,
        speed: float = 1.0,
    ) -> None:
        self.store = store
        self.mission_id = mission_id
        self.repo_url = repo_url
        self.repo_slug = _repo_slug(repo_url)
        # ``speed`` scales the async ``run()`` sleeps (higher = faster).
        self.speed = max(0.05, speed)
        # Deterministic RNG seeded from the URL hash (NOT system randomness).
        seed = int(hashlib.sha256(repo_url.encode("utf-8")).hexdigest(), 16) % (2**32)
        self.rng = random.Random(seed)
        self._nodes, self._topo_edges = _agent_topology()
        self._node_by_id = {n["id"]: n for n in self._nodes}
        # Track per-agent started_at across the script for stable timestamps.
        self._started_at: dict[str, str] = {}
        # Pre-compute deterministic findings + candidates.
        self._findings = _pick_findings(self.rng, self.repo_slug)
        self._candidates = _build_candidates(self.rng, self.repo_slug, self._findings)
        # Materialize the full ordered event list once.
        self._events: list[tuple[str, dict[str, Any]]] = self._script_events()

    # -- public playback API ----------------------------------------------
    def script(self) -> list[tuple[str, dict[str, Any]]]:
        """Return the full ordered ``(event_type, payload)`` list (synchronous)."""
        return list(self._events)

    # Alias expected by some callers.
    def steps(self) -> list[tuple[str, dict[str, Any]]]:
        return self.script()

    async def run(self) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        """Async generator: fold each scripted event into the store, then yield.

        Paces itself with ``asyncio.sleep`` so it can drive the UI directly.
        The plan is registered on the store on the first status event.
        """
        self.store.set_plan(self.mission_id, self._plan())
        for event_type, payload in self._events:
            self.store.append(self.mission_id, event_type, payload)
            yield event_type, payload
            await asyncio.sleep(self._delay_for(event_type) / self.speed)
        self.store.mark_complete(self.mission_id)

    @staticmethod
    def _delay_for(event_type: str) -> float:
        """Per-event-type delay (seconds) used by :meth:`run`."""
        if event_type in (EVT_FINDING_NEW, EVT_CANDIDATE_UPDATE, EVT_APPROVAL_REQUIRED):
            return 0.32
        if event_type in (EVT_MISSION_STATUS, EVT_MISSION_COMPLETE):
            return 0.28
        if event_type == EVT_LOG:
            return 0.16
        if event_type == EVT_RESOURCE:
            return 0.18
        return 0.2  # agent.update / edge.update

    # -- deterministic content helpers ------------------------------------
    def _plan(self) -> dict[str, Any]:
        return {
            "goal": f"Analyze {self.repo_slug} for correctness, security, quality and drift; "
            "propose independently verified, minimal fixes for human review.",
            "assumptions": [
                "Repository is a Python project using setup.py/pyproject and pytest.",
                "GitHub write access is disabled; deliverables are drafts only.",
                "Runtime analysis executes in an isolated, network-restricted sandbox.",
            ],
            "success_criteria": [
                "At least one reproduced finding with file:line evidence.",
                "Every candidate fix verified by agents independent of its author.",
                "No unrelated changes in any accepted candidate.",
                "A submittable-when-enabled PR draft awaiting human approval.",
            ],
        }

    def _findings_for_agent(self, agent_id: str) -> list[dict[str, Any]]:
        return [f for f in self._findings if f["agent_id"] == agent_id]

    @staticmethod
    def _wire(obj: dict[str, Any]) -> dict[str, Any]:
        """Strip internal ``_``-prefixed keys before putting an object on the wire."""
        return {k: v for k, v in obj.items() if not k.startswith("_")}

    def _resource(self, active_agents: int) -> dict[str, Any]:
        cpu = round(18.0 + active_agents * self.rng.uniform(6.0, 11.0) + self.rng.uniform(0, 6), 1)
        cpu = min(cpu, 99.0)
        ram = 6200 + active_agents * self.rng.randint(240, 520) + self.rng.randint(0, 300)
        return {"cpu_percent": cpu, "ram_used_mb": int(ram), "active_agents": active_agents}

    def _log(self, level: str, agent_id: str, message: str) -> dict[str, Any]:
        return {"ts": _now(), "level": level, "agent_id": agent_id, "message": message}

    def _start(self, agent_id: str) -> str:
        """Return (memoizing) a stable started_at timestamp for an agent."""
        if agent_id not in self._started_at:
            self._started_at[agent_id] = _now()
        return self._started_at[agent_id]

    def _node(
        self,
        agent_id: str,
        state: str,
        progress: float,
        *,
        result_count: int = 0,
        detail: str = "",
        started: bool = True,
    ) -> dict[str, Any]:
        n = self._node_by_id[agent_id]
        return _agent_node(
            agent_id,
            n["label"],
            n["group"],
            state,
            progress,
            result_count=result_count,
            started_at=self._start(agent_id) if started else None,
            detail=detail,
        )

    # -- the mission script (pure, deterministic) --------------------------
    def _script_events(self) -> list[tuple[str, dict[str, Any]]]:
        """Build the whole mission as an ordered list of events.

        Ordering is what makes the graph read as a believable DAG unfolding.
        No randomness of *ordering* here — only the pre-seeded content varies.
        """
        ev: list[tuple[str, dict[str, Any]]] = []

        static_ids = [n["id"] for n in self._nodes if n["group"] == GROUP_STATIC]
        runtime_ids = [n["id"] for n in self._nodes if n["group"] == GROUP_RUNTIME]
        verify_ids = [n["id"] for n in self._nodes if n["group"] == GROUP_VERIFY]

        # ---- 0. PLANNING + render the whole graph as WAITING ----------
        ev.append(
            (
                EVT_MISSION_STATUS,
                {"mission_id": self.mission_id, "status": _v(MissionStatus.PLANNING)},
            )
        )
        ev.append(
            (
                EVT_LOG,
                self._log(
                    "INFO",
                    "control.mission",
                    f"Mission accepted for {self.repo_slug}. Booting agent mesh.",
                ),
            )
        )
        for node in self._nodes:
            ev.append(
                (
                    EVT_AGENT_UPDATE,
                    _agent_node(
                        node["id"], node["label"], node["group"], _v(AgentState.WAITING), 0.0
                    ),
                )
            )
        for src, tgt in self._topo_edges:
            ev.append((EVT_EDGE_UPDATE, _edge_payload(src, tgt, animated=False)))

        # ---- 1. Control + planner -------------------------------------
        ev.append(
            (
                EVT_AGENT_UPDATE,
                self._node(
                    "control.mission",
                    _v(AgentState.RUNNING),
                    0.05,
                    detail="orchestrating agent mesh",
                ),
            )
        )
        ev.append((EVT_EDGE_UPDATE, _edge_payload("control.mission", "control.planner", True)))
        ev.append(
            (
                EVT_AGENT_UPDATE,
                self._node(
                    "control.planner",
                    _v(AgentState.RUNNING),
                    0.4,
                    detail="decomposing mission into phases",
                ),
            )
        )
        ev.append(
            (
                EVT_LOG,
                self._log(
                    "INFO",
                    "control.planner",
                    "Plan ready: 4 phases, 27 agents, 5 independent verifiers.",
                ),
            )
        )
        ev.append(
            (
                EVT_AGENT_UPDATE,
                self._node(
                    "control.planner", _v(AgentState.COMPLETED), 1.0, detail="plan finalized"
                ),
            )
        )
        ev.append((EVT_RESOURCE, self._resource(2)))

        # ---- 2. Intake + safety preflight -----------------------------
        ev.append((EVT_EDGE_UPDATE, _edge_payload("control.planner", "intake.repo", True)))
        ev.append(
            (
                EVT_AGENT_UPDATE,
                self._node(
                    "intake.repo",
                    _v(AgentState.RUNNING),
                    0.2,
                    detail=f"cloning {self.repo_slug} (shallow)",
                ),
            )
        )
        ev.append(
            (
                EVT_LOG,
                self._log(
                    "INFO",
                    "intake.repo",
                    f"git clone --depth=1 {self.repo_url} -> sandbox worktree",
                ),
            )
        )
        ev.append(
            (
                EVT_AGENT_UPDATE,
                self._node("intake.repo", _v(AgentState.RUNNING), 0.7, detail="reading tree"),
            )
        )
        ev.append(
            (
                EVT_AGENT_UPDATE,
                self._node(
                    "intake.repo",
                    _v(AgentState.COMPLETED),
                    1.0,
                    detail="1 pyproject.toml, 1 setup.py, 214 files",
                ),
            )
        )

        ev.append((EVT_EDGE_UPDATE, _edge_payload("intake.repo", "intake.safety", True)))
        ev.append(
            (
                EVT_AGENT_UPDATE,
                self._node(
                    "intake.safety",
                    _v(AgentState.RUNNING),
                    0.35,
                    detail="scanning for unsafe execution / secrets",
                ),
            )
        )
        ev.append(
            (
                EVT_LOG,
                self._log(
                    "INFO",
                    "intake.safety",
                    "Preflight: no secrets committed; sandbox execution gate armed.",
                ),
            )
        )
        ev.append(
            (
                EVT_AGENT_UPDATE,
                self._node(
                    "intake.safety",
                    _v(AgentState.COMPLETED),
                    1.0,
                    detail="safe to run in isolation",
                ),
            )
        )
        ev.append((EVT_RESOURCE, self._resource(3)))

        # ---- 3. PARALLEL static swarm ---------------------------------
        ev.append(
            (
                EVT_MISSION_STATUS,
                {"mission_id": self.mission_id, "status": _v(MissionStatus.RUNNING)},
            )
        )
        for sid in static_ids:
            ev.append((EVT_EDGE_UPDATE, _edge_payload("intake.safety", sid, True)))
        for sid in static_ids:
            ev.append(
                (
                    EVT_AGENT_UPDATE,
                    self._node(sid, _v(AgentState.RUNNING), 0.1, detail=self._static_detail(sid)),
                )
            )
        ev.append(
            (
                EVT_LOG,
                self._log(
                    "INFO",
                    "control.mission",
                    f"STATIC phase: {len(static_ids)} agents running in parallel.",
                ),
            )
        )
        ev.append((EVT_RESOURCE, self._resource(len(static_ids))))
        self._emit_swarm(ev, static_ids, emit_findings=True)

        # ---- 4. History + build/test plan -----------------------------
        ev.append((EVT_EDGE_UPDATE, _edge_payload("intake.repo", "intake.history", True)))
        ev.append(
            (
                EVT_AGENT_UPDATE,
                self._node(
                    "intake.history",
                    _v(AgentState.RUNNING),
                    0.3,
                    detail="walking 500 commits for churn / hotspots",
                ),
            )
        )
        ev.append(
            (
                EVT_LOG,
                self._log(
                    "INFO", "intake.history", "git log --numstat: hotspots in src/pipeline, tests/."
                ),
            )
        )
        ev.append(
            (
                EVT_AGENT_UPDATE,
                self._node(
                    "intake.history",
                    _v(AgentState.COMPLETED),
                    1.0,
                    detail="12 hotspot files identified",
                ),
            )
        )

        ev.append((EVT_EDGE_UPDATE, _edge_payload("intake.history", "intake.build_plan", True)))
        ev.append(
            (
                EVT_AGENT_UPDATE,
                self._node(
                    "intake.build_plan",
                    _v(AgentState.RUNNING),
                    0.4,
                    detail="detecting toolchain (pytest, ruff, mypy)",
                ),
            )
        )
        ev.append(
            (
                EVT_LOG,
                self._log(
                    "INFO",
                    "intake.build_plan",
                    "Detected: pytest, ruff, mypy; python_requires>=3.9.",
                ),
            )
        )
        ev.append(
            (
                EVT_AGENT_UPDATE,
                self._node(
                    "intake.build_plan",
                    _v(AgentState.COMPLETED),
                    1.0,
                    detail="build/test plan ready",
                ),
            )
        )
        ev.append((EVT_RESOURCE, self._resource(4)))

        # ---- 5. Isolated runtime swarm --------------------------------
        for rid in runtime_ids:
            ev.append((EVT_EDGE_UPDATE, _edge_payload("intake.build_plan", rid, True)))
        for rid in runtime_ids:
            ev.append(
                (
                    EVT_AGENT_UPDATE,
                    self._node(rid, _v(AgentState.RUNNING), 0.1, detail=self._runtime_detail(rid)),
                )
            )
        ev.append(
            (
                EVT_LOG,
                self._log(
                    "WARN",
                    "runtime.test",
                    "Executing test suite in isolated sandbox (network disabled).",
                ),
            )
        )
        ev.append((EVT_RESOURCE, self._resource(3 + len(runtime_ids))))
        self._emit_swarm(ev, runtime_ids, emit_findings=True)

        # ---- 6. Evidence aggregator -----------------------------------
        for sid in static_ids:
            ev.append((EVT_EDGE_UPDATE, _edge_payload(sid, "aggregate.evidence", True)))
        for rid in runtime_ids:
            ev.append((EVT_EDGE_UPDATE, _edge_payload(rid, "aggregate.evidence", True)))
        ev.append(
            (
                EVT_AGENT_UPDATE,
                self._node(
                    "aggregate.evidence",
                    _v(AgentState.RUNNING),
                    0.4,
                    detail="correlating findings + evidence",
                ),
            )
        )
        n_cat = len({f["category"] for f in self._findings})
        ev.append(
            (
                EVT_LOG,
                self._log(
                    "INFO",
                    "aggregate.evidence",
                    f"Aggregated {len(self._findings)} findings across {n_cat} categories.",
                ),
            )
        )
        ev.append(
            (
                EVT_AGENT_UPDATE,
                self._node(
                    "aggregate.evidence",
                    _v(AgentState.COMPLETED),
                    1.0,
                    result_count=len(self._findings),
                    detail=f"{len(self._findings)} findings ranked",
                ),
            )
        )
        ev.append((EVT_RESOURCE, self._resource(2)))

        # ---- 7. Duplicate detection -----------------------------------
        dup_hits = self.rng.randint(0, 2)
        ev.append(
            (EVT_EDGE_UPDATE, _edge_payload("aggregate.evidence", "duplicate.detector", True))
        )
        ev.append(
            (
                EVT_AGENT_UPDATE,
                self._node(
                    "duplicate.detector",
                    _v(AgentState.RUNNING),
                    0.5,
                    detail="searching issues/PRs for duplicates",
                ),
            )
        )
        ev.append(
            (
                EVT_LOG,
                self._log(
                    "INFO",
                    "duplicate.detector",
                    f"Semantic dedupe over existing issues: {dup_hits} likely duplicate(s) suppressed.",
                ),
            )
        )
        ev.append(
            (
                EVT_AGENT_UPDATE,
                self._node(
                    "duplicate.detector",
                    _v(AgentState.COMPLETED),
                    1.0,
                    result_count=dup_hits,
                    detail=f"{dup_hits} duplicate(s) filtered",
                ),
            )
        )

        # ---- 8. Fix swarm (worktrees) ---------------------------------
        fix_ids = ["fix.a", "fix.b", "fix.critic"]
        for fid in fix_ids:
            ev.append((EVT_EDGE_UPDATE, _edge_payload("duplicate.detector", fid, True)))
        for fid in fix_ids:
            ev.append(
                (
                    EVT_AGENT_UPDATE,
                    self._node(fid, _v(AgentState.RUNNING), 0.2, detail=self._fix_detail(fid)),
                )
            )
        ev.append(
            (
                EVT_LOG,
                self._log(
                    "INFO",
                    "control.mission",
                    "FIX phase: candidates generated in isolated git worktrees.",
                ),
            )
        )
        ev.append((EVT_RESOURCE, self._resource(3)))

        # Emit each candidate as PENDING (authored, not yet verified).
        for cand in self._candidates:
            pending = self._wire(cand)
            pending = dict(pending)
            pending["verdict"] = _v(CandidateVerdict.PENDING)
            pending["verification"] = []
            pending["verification_summary"] = "Authored; awaiting independent verification."
            ev.append((EVT_CANDIDATE_UPDATE, pending))
            ev.append(
                (
                    EVT_LOG,
                    self._log("INFO", cand["author_agent"], f"Candidate authored: {cand['title']}"),
                )
            )

        ev.append(
            (
                EVT_AGENT_UPDATE,
                self._node(
                    "fix.a",
                    _v(AgentState.COMPLETED),
                    1.0,
                    result_count=1,
                    detail="1 candidate in worktree wt-a",
                ),
            )
        )
        ev.append(
            (
                EVT_AGENT_UPDATE,
                self._node(
                    "fix.b",
                    _v(AgentState.COMPLETED),
                    1.0,
                    result_count=1,
                    detail="1 candidate in worktree wt-b",
                ),
            )
        )
        has_no_sub = any(
            c["verdict"] == _v(CandidateVerdict.NO_SUBMISSION) for c in self._candidates
        )
        ev.append(
            (
                EVT_AGENT_UPDATE,
                self._node(
                    "fix.critic",
                    _v(AgentState.COMPLETED),
                    1.0,
                    result_count=1 if has_no_sub else 0,
                    detail="NO_FIX recommendation issued" if has_no_sub else "no critique withheld",
                ),
            )
        )

        # ---- 9. Independent verification swarm ------------------------
        for src, tgt in [
            ("fix.a", "verify.regression"),
            ("fix.a", "verify.lint"),
            ("fix.a", "verify.types"),
            ("fix.a", "verify.scope"),
            ("fix.b", "verify.regression"),
            ("fix.b", "verify.scope"),
            ("fix.critic", "verify.reproduction"),
        ]:
            ev.append((EVT_EDGE_UPDATE, _edge_payload(src, tgt, True)))
        for vid in verify_ids:
            ev.append(
                (
                    EVT_AGENT_UPDATE,
                    self._node(
                        vid,
                        _v(AgentState.VERIFYING),
                        0.2,
                        detail=f"verifying candidates (independent of {_VERIFIER_OF.get(vid, 'author')})",
                    ),
                )
            )
        ev.append(
            (
                EVT_LOG,
                self._log(
                    "INFO",
                    "control.mission",
                    "VERIFY phase: 5 verifiers, each independent of the fix authors.",
                ),
            )
        )
        ev.append((EVT_RESOURCE, self._resource(3 + len(verify_ids))))
        self._emit_swarm(ev, verify_ids, emit_findings=False, verifying=True)

        # Resolve candidates with full verification matrices.
        accepted: list[dict[str, Any]] = []
        for cand in self._candidates:
            wire = self._wire(cand)
            ev.append((EVT_CANDIDATE_UPDATE, wire))
            verdict = wire["verdict"]
            if verdict == _v(CandidateVerdict.ACCEPTED):
                accepted.append(cand)
                ev.append(
                    (
                        EVT_LOG,
                        self._log(
                            "INFO",
                            "verify.regression",
                            f"ACCEPTED: {wire['title']} — {wire['verification_summary']}",
                        ),
                    )
                )
            elif verdict == _v(CandidateVerdict.REJECTED):
                ev.append(
                    (
                        EVT_LOG,
                        self._log(
                            "ERROR",
                            "verify.scope",
                            f"REJECTED: {wire['title']} — {wire['verification_summary']}",
                        ),
                    )
                )
                ev.append(
                    (
                        EVT_AGENT_UPDATE,
                        self._node(
                            wire["author_agent"],
                            _v(AgentState.REJECTED),
                            1.0,
                            detail="candidate rejected by independent verifier",
                        ),
                    )
                )
            elif verdict == _v(CandidateVerdict.NO_SUBMISSION):
                ev.append(
                    (
                        EVT_LOG,
                        self._log(
                            "WARN",
                            "verify.reproduction",
                            f"NO_SUBMISSION: {wire['title']} — deferred to human review.",
                        ),
                    )
                )

        # ---- 10. Approval gate + complete -----------------------------
        for vid in verify_ids:
            ev.append((EVT_EDGE_UPDATE, _edge_payload(vid, "control.mission", True)))

        if accepted:
            draft = _build_draft(self.repo_slug, accepted[0])
            ev.append(
                (
                    EVT_MISSION_STATUS,
                    {"mission_id": self.mission_id, "status": _v(MissionStatus.AWAITING_APPROVAL)},
                )
            )
            ev.append((EVT_APPROVAL_REQUIRED, {"mission_id": self.mission_id, "draft": draft}))
            ev.append(
                (
                    EVT_LOG,
                    self._log(
                        "WARN",
                        "control.mission",
                        "Human approval required. GitHub writes DISABLED — draft saved locally only.",
                    ),
                )
            )
            ev.append(
                (
                    EVT_AGENT_UPDATE,
                    self._node(
                        "control.mission",
                        _v(AgentState.BLOCKED),
                        0.95,
                        result_count=len(accepted),
                        detail="awaiting human approval",
                    ),
                )
            )
            final_status = _v(MissionStatus.AWAITING_APPROVAL)
        else:  # pragma: no cover - the script always accepts one candidate
            ev.append(
                (
                    EVT_AGENT_UPDATE,
                    self._node(
                        "control.mission",
                        _v(AgentState.COMPLETED),
                        1.0,
                        detail="no accepted candidates",
                    ),
                )
            )
            final_status = _v(MissionStatus.COMPLETED)

        ev.append((EVT_RESOURCE, self._resource(0)))
        ev.append((EVT_MISSION_COMPLETE, {"mission_id": self.mission_id, "status": final_status}))
        ev.append(
            (
                EVT_LOG,
                self._log(
                    "INFO",
                    "control.mission",
                    f"Mission stream complete. {len(self._findings)} findings, {len(self._candidates)} candidates. Status: {final_status}.",
                ),
            )
        )
        return ev

    def _emit_swarm(
        self,
        ev: list[tuple[str, dict[str, Any]]],
        agent_ids: list[str],
        *,
        emit_findings: bool,
        verifying: bool = False,
    ) -> None:
        """Interleave progress across a set of agents so they look concurrent.

        Each agent gets a deterministic step count; when it finishes we complete
        it (and, if ``emit_findings``, emit any findings it authored).
        """
        steps = {aid: self.rng.randint(3, 5) for aid in agent_ids}
        done = dict.fromkeys(agent_ids, False)
        current = dict.fromkeys(agent_ids, 0)
        active = len(agent_ids)
        max_rounds = max(steps.values()) if steps else 0
        running_state = _v(AgentState.VERIFYING) if verifying else _v(AgentState.RUNNING)

        for _round in range(max_rounds):
            for aid in agent_ids:
                if done[aid]:
                    continue
                current[aid] += 1
                total = steps[aid]
                if current[aid] >= total:
                    done[aid] = True
                    active -= 1
                    rc = 0
                    if emit_findings:
                        agent_findings = self._findings_for_agent(aid)
                        for finding in agent_findings:
                            ev.append((EVT_FINDING_NEW, self._wire(finding)))
                            ev.append(
                                (
                                    EVT_LOG,
                                    self._log(
                                        self._severity_log_level(finding["severity"]),
                                        aid,
                                        f"[{finding['severity']}] {finding['summary']}",
                                    ),
                                )
                            )
                        rc = len(agent_findings)
                    detail = (
                        "verification complete"
                        if verifying
                        else (f"{rc} finding(s)" if emit_findings else "done")
                    )
                    ev.append(
                        (
                            EVT_AGENT_UPDATE,
                            self._node(
                                aid, _v(AgentState.COMPLETED), 1.0, result_count=rc, detail=detail
                            ),
                        )
                    )
                else:
                    progress = current[aid] / total
                    detail = self._node_by_id[aid].get("_detail", "working")
                    ev.append(
                        (EVT_AGENT_UPDATE, self._node(aid, running_state, progress, detail=detail))
                    )
            ev.append((EVT_RESOURCE, self._resource(max(active, 1))))

    # -- detail-string helpers --------------------------------------------
    @staticmethod
    def _severity_log_level(severity: str) -> str:
        if severity in (_v(Severity.CRITICAL), _v(Severity.HIGH)):
            return "ERROR"
        if severity == _v(Severity.MEDIUM):
            return "WARN"
        return "INFO"

    @staticmethod
    def _static_detail(agent_id: str) -> str:
        details = {
            "static.architecture": "building import graph, checking layering",
            "static.code_quality": "ruff + radon complexity scan",
            "static.docs_drift": "diffing README against public API",
            "static.dependency": "resolving setup.py / pyproject, matching advisories",
            "static.test_quality": "coverage + assertion-density heuristics",
            "static.typing": "mypy --strict dry run",
            "static.api_consistency": "sampling endpoints for naming/shape drift",
            "static.security_smell": "bandit-style scan (subprocess, eval, pickle)",
        }
        return details.get(agent_id, "scanning")

    @staticmethod
    def _runtime_detail(agent_id: str) -> str:
        details = {
            "runtime.test": "pytest -q in sandbox",
            "runtime.docs": "executing documented commands",
            "runtime.deprecation": "run with -W error::DeprecationWarning",
        }
        return details.get(agent_id, "executing")

    @staticmethod
    def _fix_detail(agent_id: str) -> str:
        details = {
            "fix.a": "authoring minimal patch in worktree wt-a",
            "fix.b": "authoring patch in worktree wt-b",
            "fix.critic": "NO_FIX critic assessing fixability",
        }
        return details.get(agent_id, "working")


# ---------------------------------------------------------------------------
# Snapshot builders for GET /missions/{mission_id}.
# ---------------------------------------------------------------------------
def build_mission_snapshot(record: MissionRecord) -> dict[str, Any]:
    """Assemble the full Mission object from stored state (contract shape).

    ``approval`` is ``null`` until an approval has been requested.  Agents/edges
    are returned in stable topology order; findings/candidates in the order they
    were first seen (insertion order of the backing dicts).
    """
    plan = record.plan or {
        "goal": f"Analyze {_repo_slug(record.repo_url)}",
        "assumptions": [],
        "success_criteria": [],
    }
    nodes, topo_edges = _agent_topology()
    node_order = {n["id"]: i for i, n in enumerate(nodes)}
    edge_order = {f"e:{s}->{t}": i for i, (s, t) in enumerate(topo_edges)}

    agents = sorted(record.agents.values(), key=lambda a: node_order.get(a["id"], 10_000))
    edges = sorted(record.edges.values(), key=lambda e: edge_order.get(e["id"], 10_000))

    return {
        "mission_id": record.mission_id,
        "repo_url": record.repo_url,
        "status": record.status,
        "created_at": record.created_at,
        "plan": plan,
        "agents": agents,
        "edges": edges,
        "findings": list(record.findings.values()),
        "candidates": list(record.candidates.values()),
        "approval": record.approval,
    }


def build_snapshot(store: MissionStore, mission_id: str) -> dict[str, Any] | None:
    """Store-oriented snapshot builder (the name ``careerforge_api.main`` looks for)."""
    return store.snapshot(mission_id)


def grant_approval(record: MissionRecord, decision: str) -> dict[str, Any]:
    """Fold an approval decision into a mission record.

    Returns the ``POST /api/v1/approvals/{mission_id}`` response body. GitHub
    writes are always disabled in demo mode, so an APPROVE only saves locally.
    """
    approved = decision.upper() == "APPROVE"
    if record.approval is not None:
        record.approval = {
            "required": True,
            "granted": approved,
            "draft": record.approval.get("draft"),
        }
    record.status = _v(MissionStatus.COMPLETED) if approved else _v(MissionStatus.CANCELLED)
    record.complete = True
    return {
        "ok": True,
        "action_taken": "DRAFT_SAVED_LOCALLY" if approved else "DRAFT_DISCARDED",
        "github_write": False,
    }


__all__ = [
    "MissionSimulator",
    "MissionStore",
    "MissionRecord",
    "get_store",
    "build_mission_snapshot",
    "build_snapshot",
    "grant_approval",
    # SSE event-type constants.
    "EVT_MISSION_STATUS",
    "EVT_AGENT_UPDATE",
    "EVT_EDGE_UPDATE",
    "EVT_FINDING_NEW",
    "EVT_CANDIDATE_UPDATE",
    "EVT_LOG",
    "EVT_RESOURCE",
    "EVT_APPROVAL_REQUIRED",
    "EVT_MISSION_COMPLETE",
]
