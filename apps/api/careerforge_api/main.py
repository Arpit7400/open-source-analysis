"""CareerForge AI — FastAPI application (HTTP + SSE surface).

This module owns the *transport* layer only: the FastAPI app, CORS, the
``/api/v1`` router, the Server-Sent-Events stream, and a structured error
handler. All domain logic (schemas, settings, hardware detection, the mission
simulation, and seed data) lives in sibling modules owned by other backend
tracks:

    careerforge_api.schemas       -> Pydantic models + enums (API_CONTRACT.md)
    careerforge_api.config        -> Settings (pydantic-settings)
    careerforge_api.hardware      -> hardware profile detection + live resources
    careerforge_api.simulation    -> MissionSimulator, MissionStore, snapshots
    careerforge_api.seed_data     -> profile / skills / evidence / pulse seeds

--------------------------------------------------------------------------------
Adapter layer
--------------------------------------------------------------------------------
The block below wires this transport layer to those sibling modules with
*direct imports* (the preferred path). Because backend tracks land
independently, and so that this app is always runnable + testable on its own
(Windows / macOS / Linux, no DB, no Docker, no Ollama), every wired-in callable
has a small, contract-accurate built-in fallback. If a sibling module (or an
expected name inside it) is missing, the fallback keeps the exact same JSON
shapes and enum spellings defined in ``docs/API_CONTRACT.md``. When the real
modules are present they take precedence automatically.

This is the ONLY place ``getattr``-style optional wiring is used, and it is
confined to composing the app — never to guessing data shapes at runtime.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import platform
import time
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from fastapi import Body, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

try:  # sse-starlette is a hard dependency (see pyproject.toml).
    from sse_starlette.sse import EventSourceResponse
except ImportError as exc:  # pragma: no cover - dependency guaranteed by install
    raise RuntimeError("sse-starlette is required. Install with `pip install -e .`.") from exc


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
API_PREFIX = "/api/v1"
APP_VERSION = "1.0.0"
ALLOWED_ORIGINS = ["http://localhost:3000"]
SSE_HEARTBEAT_SECONDS = 15.0


def _utc_now_iso() -> str:
    """Return the current time as an ISO-8601 UTC string (contract format)."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_uuid() -> str:
    return str(uuid.uuid4())


# ===========================================================================
# Adapter: Settings
# ===========================================================================
# The real ``careerforge_api.config`` exposes a ``Settings`` model whose
# ``app_env`` is an ``AppEnv`` enum, nested feature flags under ``.flags``, a
# ``cors_origins`` list, and ``max_agent_concurrency``. We read those defensively
# so that if the config module is absent (or a name differs) the app still boots
# with contract-correct defaults.
try:
    from careerforge_api.config import get_settings as _get_settings

    def _load_settings() -> Any:
        return _get_settings()

except Exception:
    try:
        from careerforge_api.config import Settings as _RealSettings

        def _load_settings() -> Any:
            return _RealSettings()

    except Exception:

        class _FallbackSettings:
            """Minimal settings mirror used only when config module is absent."""

            app_env: str = "demo"
            version: str = APP_VERSION
            api_prefix: str = API_PREFIX
            cors_origins: list[str] = list(ALLOWED_ORIGINS)
            max_agent_concurrency: int = 4
            # Demo mode never performs GitHub writes or executes repositories.
            github_writes: bool = False
            repository_execution: bool = False

        def _load_settings() -> Any:
            return _FallbackSettings()


SETTINGS: Any = _load_settings()


def _enum_value(value: Any) -> str:
    """Return ``value.value`` for an Enum, else ``str(value)``."""
    inner = getattr(value, "value", value)
    return str(inner)


def _flag(name: str, default: bool = False) -> bool:
    """Read a boolean feature flag off the settings object, defensively.

    Real config nests flags under ``settings.flags.<name>``; the fallback stub
    exposes them as top-level attributes. Both are supported.
    """
    flags_obj = getattr(SETTINGS, "flags", None)
    if flags_obj is not None and hasattr(flags_obj, name):
        return bool(getattr(flags_obj, name))
    return bool(getattr(SETTINGS, name, default))


def _app_env() -> str:
    return _enum_value(getattr(SETTINGS, "app_env", "demo"))


def _is_demo() -> bool:
    # Prefer the model's own predicate when present.
    is_demo = getattr(SETTINGS, "is_demo", None)
    if isinstance(is_demo, bool):
        return is_demo
    return _app_env().lower() == "demo"


def _app_version() -> str:
    return str(getattr(SETTINGS, "version", APP_VERSION))


def _cors_origins() -> list[str]:
    origins = getattr(SETTINGS, "cors_origins", None)
    if origins:
        return list(origins)
    return list(ALLOWED_ORIGINS)


def _max_agents() -> int:
    value = getattr(SETTINGS, "max_agent_concurrency", None)
    try:
        return int(value) if value is not None else 4
    except (TypeError, ValueError):
        return 4


# ===========================================================================
# Adapter: Hardware profile + live resources
# ===========================================================================
_VALID_PROFILES = {"CPU_LOW", "VRAM_8_12", "VRAM_16_24", "WORKSTATION"}


def _fallback_hardware_profile() -> str:
    """Best-effort hardware bucket without importing the hardware module."""
    try:
        import psutil  # local import keeps psutil optional at module load

        total_gb = psutil.virtual_memory().total / (1024**3)
        cpu_count = psutil.cpu_count(logical=True) or 1
    except Exception:
        total_gb, cpu_count = 8.0, 4

    if total_gb >= 64 and cpu_count >= 16:
        return "WORKSTATION"
    if total_gb >= 24:
        return "VRAM_16_24"
    if total_gb >= 12:
        return "VRAM_8_12"
    return "CPU_LOW"


def _fallback_resources(active_agents: int, max_agents: int) -> dict[str, Any]:
    try:
        import psutil

        cpu_percent = float(psutil.cpu_percent(interval=None))
        vm = psutil.virtual_memory()
        ram_total_mb = int(vm.total / (1024**2))
        ram_used_mb = int((vm.total - vm.available) / (1024**2))
    except Exception:
        cpu_percent, ram_used_mb, ram_total_mb = 34.2, 8123, 32768

    return {
        "cpu_percent": round(cpu_percent, 1),
        "ram_used_mb": ram_used_mb,
        "ram_total_mb": ram_total_mb,
        "active_agents": active_agents,
        "max_agents": max_agents,
    }


try:
    from careerforge_api import hardware as _hardware_mod

    def _detect_hardware_profile() -> str:
        # Real module: detect_hardware_profile() -> HardwareProfile enum.
        fn = (
            getattr(_hardware_mod, "detect_hardware_profile", None)
            or getattr(_hardware_mod, "detect_profile", None)
            or getattr(_hardware_mod, "get_profile", None)
        )
        if not callable(fn):
            return _fallback_hardware_profile()
        try:
            profile = _enum_value(fn())
        except Exception:
            return _fallback_hardware_profile()
        return profile if profile in _VALID_PROFILES else _fallback_hardware_profile()

    def _live_resources(active_agents: int, max_agents: int) -> dict[str, Any]:
        # The hardware module may expose a resources helper; otherwise derive
        # RAM totals from its structured HardwareInfo and CPU% from psutil.
        fn = getattr(_hardware_mod, "get_resources", None) or getattr(
            _hardware_mod, "resources", None
        )
        if callable(fn):
            try:
                data = dict(fn(active_agents=active_agents, max_agents=max_agents))
            except TypeError:
                data = dict(fn())
            data.setdefault("active_agents", active_agents)
            data.setdefault("max_agents", max_agents)
            return data

        detect_info = getattr(_hardware_mod, "detect_hardware", None)
        if callable(detect_info):
            try:
                info = detect_info()
                total = int(info.ram_total_mb)
                avail = int(info.ram_available_mb)
                import psutil

                cpu_percent = float(psutil.cpu_percent(interval=None))
                return {
                    "cpu_percent": round(cpu_percent, 1),
                    "ram_used_mb": max(0, total - avail),
                    "ram_total_mb": total,
                    "active_agents": active_agents,
                    "max_agents": max_agents,
                }
            except Exception:
                pass
        return _fallback_resources(active_agents, max_agents)

except Exception:

    def _detect_hardware_profile() -> str:
        return _fallback_hardware_profile()

    def _live_resources(active_agents: int, max_agents: int) -> dict[str, Any]:
        return _fallback_resources(active_agents, max_agents)


HARDWARE_PROFILE: str = _detect_hardware_profile()


# ===========================================================================
# Adapter: Seed data (profile / skills / evidence / pulse)
# ===========================================================================
def _fallback_profile() -> dict[str, Any]:
    return {
        "user_id": "8f14e45f-ceea-4e0a-9b3b-2a1f4c6d7e80",
        "name": "Ada Lovelace",
        "headline": "Backend & ML engineer",
        "goals": ["Merge 3 OSS PRs", "Master RAG systems"],
        "verified_skill_count": 12,
        "merged_prs": 4,
        "evidence_count": 37,
    }


def _fallback_skills() -> list[dict[str, Any]]:
    ev_a, ev_b, ev_c = _new_uuid(), _new_uuid(), _new_uuid()
    python_id = "c0ffee00-0000-4000-8000-000000000001"
    fastapi_id = "c0ffee00-0000-4000-8000-000000000002"
    rag_id = "c0ffee00-0000-4000-8000-000000000003"
    return [
        {
            "id": python_id,
            "name": "Python",
            "category": "language",
            "confidence": 0.86,
            "evidence_strength": 0.79,
            "recency": 0.9,
            "complexity": 0.7,
            "independence": 0.8,
            "verification_level": "TOOL_VERIFIED",
            "evidence_ids": [ev_a, ev_b],
            "last_updated": _utc_now_iso(),
            "last_change_reason": "3 passing tests added in linked repo",
            "related_skill_ids": [fastapi_id],
        },
        {
            "id": fastapi_id,
            "name": "FastAPI",
            "category": "framework",
            "confidence": 0.74,
            "evidence_strength": 0.68,
            "recency": 0.85,
            "complexity": 0.6,
            "independence": 0.72,
            "verification_level": "AI_INFERRED",
            "evidence_ids": [ev_c],
            "last_updated": _utc_now_iso(),
            "last_change_reason": "Router modules detected in analyzed repository",
            "related_skill_ids": [python_id],
        },
        {
            "id": rag_id,
            "name": "RAG Systems",
            "category": "domain",
            "confidence": 0.41,
            "evidence_strength": 0.33,
            "recency": 0.6,
            "complexity": 0.8,
            "independence": 0.4,
            "verification_level": "SELF_DECLARED",
            "evidence_ids": [],
            "last_updated": _utc_now_iso(),
            "last_change_reason": "Declared on resume; awaiting tool verification",
            "related_skill_ids": [python_id],
        },
    ]


def _fallback_evidence(skill_id: str) -> list[dict[str, Any]]:
    return [
        {
            "id": _new_uuid(),
            "type": "TEST",
            "summary": "Unit test suite exercises the module (142 passing).",
            "source_url": "https://github.com/owner/name/blob/main/tests/test_core.py",
            "verification_level": "TOOL_VERIFIED",
            "created_at": _utc_now_iso(),
        },
        {
            "id": _new_uuid(),
            "type": "COMMIT",
            "summary": "Refactor introducing typed interfaces.",
            "source_url": "https://github.com/owner/name/commit/abc123",
            "verification_level": "AI_INFERRED",
            "created_at": _utc_now_iso(),
        },
    ]


def _fallback_pulse() -> list[dict[str, Any]]:
    return [
        {
            "id": _new_uuid(),
            "title": "Structured outputs land in mainstream agent frameworks",
            "source": "Blog",
            "technology": "LLM tooling",
            "published_at": _utc_now_iso(),
            "momentum": 0.82,
            "personal_relevance": 0.61,
            "actionability": 0.7,
            "why_it_matters": "Typed tool I/O reduces agent brittleness.",
            "skill_gap": "Schema-driven prompting",
            "suggested_action": "Add a pydantic-validated tool layer to a side project.",
            "canonical_url": "https://example.com/structured-outputs",
        },
        {
            "id": _new_uuid(),
            "title": "New advisory: unpinned transitive dependency risk",
            "source": "Advisory",
            "technology": "Supply chain",
            "published_at": _utc_now_iso(),
            "momentum": 0.55,
            "personal_relevance": 0.48,
            "actionability": 0.9,
            "why_it_matters": "Directly affects repos with loose version constraints.",
            "skill_gap": "Dependency pinning discipline",
            "suggested_action": "Audit and pin direct dependencies in your OSS repos.",
            "canonical_url": "https://example.com/advisory-dep",
        },
    ]


# The real ``careerforge_api.seed_data`` exposes:
#   get_profile() -> dict
#   get_skills() -> {"skills": [...]}
#   list_skills() -> [ {...} ]
#   get_skill(id) -> dict | None
#   get_evidence_for_skill(id) -> {"skill_id", "evidence"} | None  (None => 404)
#   get_pulse_items() -> {"items": [...]}
# It does NOT provide resume-claim extraction, so that stays local (below).
try:
    from careerforge_api import seed_data as _seed_mod

    def _seed_profile() -> dict[str, Any]:
        fn = getattr(_seed_mod, "get_profile", None)
        return dict(fn()) if callable(fn) else _fallback_profile()

    def _seed_skills() -> list[dict[str, Any]]:
        # Prefer list_skills(); else unwrap get_skills()["skills"].
        lister = getattr(_seed_mod, "list_skills", None)
        if callable(lister):
            return [dict(s) for s in lister()]
        envelope = getattr(_seed_mod, "get_skills", None)
        if callable(envelope):
            data = envelope()
            skills = data.get("skills", []) if isinstance(data, dict) else data
            return [dict(s) for s in skills]
        return _fallback_skills()

    def _seed_skill_exists(skill_id: str) -> bool:
        getter = getattr(_seed_mod, "get_skill", None)
        if callable(getter):
            return getter(skill_id) is not None
        return any(s.get("id") == skill_id for s in _seed_skills())

    def _seed_evidence(skill_id: str) -> list[dict[str, Any]] | None:
        # Returns None when the skill id is unknown so the route can 404.
        fn = getattr(_seed_mod, "get_evidence_for_skill", None)
        if callable(fn):
            bundle = fn(skill_id)
            if bundle is None:
                return None
            evidence = bundle.get("evidence", []) if isinstance(bundle, dict) else bundle
            return [dict(e) for e in evidence]
        if not _seed_skill_exists(skill_id):
            return None
        return _fallback_evidence(skill_id)

    def _seed_pulse() -> list[dict[str, Any]]:
        fn = getattr(_seed_mod, "get_pulse_items", None) or getattr(_seed_mod, "get_pulse", None)
        if callable(fn):
            data = fn()
            items = data.get("items", []) if isinstance(data, dict) else data
            return [dict(p) for p in items]
        return _fallback_pulse()

    def _extract_resume_claims(text: str) -> list[dict[str, Any]]:
        fn = getattr(_seed_mod, "extract_resume_claims", None)
        return [dict(c) for c in fn(text)] if callable(fn) else _fallback_claims(text)

except Exception:

    def _seed_profile() -> dict[str, Any]:
        return _fallback_profile()

    def _seed_skills() -> list[dict[str, Any]]:
        return _fallback_skills()

    def _seed_skill_exists(skill_id: str) -> bool:
        return any(s.get("id") == skill_id for s in _fallback_skills())

    def _seed_evidence(skill_id: str) -> list[dict[str, Any]] | None:
        if not _seed_skill_exists(skill_id):
            return None
        return _fallback_evidence(skill_id)

    def _seed_pulse() -> list[dict[str, Any]]:
        return _fallback_pulse()

    def _extract_resume_claims(text: str) -> list[dict[str, Any]]:
        return _fallback_claims(text)


# A curated keyword map for the fallback resume parser. Claims are ALWAYS
# emitted as SELF_DECLARED — ingestion never fabricates verification.
_RESUME_KEYWORDS: dict[str, str] = {
    "python": "Python",
    "fastapi": "FastAPI",
    "django": "Django",
    "flask": "Flask",
    "typescript": "TypeScript",
    "javascript": "JavaScript",
    "react": "React",
    "next.js": "Next.js",
    "nextjs": "Next.js",
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "docker": "Docker",
    "kubernetes": "Kubernetes",
    "rag": "RAG Systems",
    "pytorch": "PyTorch",
    "tensorflow": "TensorFlow",
    "rust": "Rust",
    "go": "Go",
    "sql": "SQL",
    "aws": "AWS",
    "gcp": "GCP",
    "graphql": "GraphQL",
    "redis": "Redis",
    "qdrant": "Qdrant",
}


def _fallback_claims(text: str) -> list[dict[str, Any]]:
    """Extract skill *claims* from resume text.

    The result is intentionally conservative: every claim is SELF_DECLARED and
    carries the raw span it was matched from. No verification is inferred here.
    """
    if not text:
        return []

    lowered = text.lower()
    seen: set[str] = set()
    claims: list[dict[str, Any]] = []

    for needle, canonical in _RESUME_KEYWORDS.items():
        idx = lowered.find(needle)
        if idx == -1 or canonical in seen:
            continue
        seen.add(canonical)
        start = max(0, idx - 24)
        end = min(len(text), idx + len(needle) + 24)
        raw_span = text[start:end].strip()
        claims.append(
            {
                "skill": canonical,
                "evidence_level": "SELF_DECLARED",
                "raw_span": raw_span,
            }
        )

    return claims


# ===========================================================================
# Adapter: Mission simulation (MissionSimulator, MissionStore, snapshot builder)
# ===========================================================================
#
# The real ``careerforge_api.simulation`` module provides a MissionStore
# (append-only event log + current snapshot per mission) and a MissionSimulator
# that advances a scripted mission and appends contract-shaped events. When it
# is unavailable we use the fully self-contained ``_FallbackMissionStore`` /
# ``_FallbackMissionSimulator`` below so the flagship flow still runs.


class _FallbackMissionStore:
    """In-memory, append-only event store with per-mission snapshots.

    Events are ``(event_id, event_type, payload)`` tuples. ``event_id`` is a
    monotonic integer serialized as a string so SSE ``Last-Event-ID`` replay is
    trivial and deterministic.
    """

    def __init__(self) -> None:
        self._events: dict[str, list[tuple[int, str, dict[str, Any]]]] = {}
        self._snapshots: dict[str, dict[str, Any]] = {}
        self._counter: dict[str, int] = {}
        self._complete: dict[str, bool] = {}

    # -- lifecycle ---------------------------------------------------------
    def create(self, repo_url: str) -> str:
        mission_id = _new_uuid()
        self._events[mission_id] = []
        self._counter[mission_id] = 0
        self._complete[mission_id] = False
        self._snapshots[mission_id] = _initial_snapshot(mission_id, repo_url)
        return mission_id

    def exists(self, mission_id: str) -> bool:
        return mission_id in self._snapshots

    def is_complete(self, mission_id: str) -> bool:
        return self._complete.get(mission_id, False)

    def mark_complete(self, mission_id: str) -> None:
        self._complete[mission_id] = True

    # -- events ------------------------------------------------------------
    def append(self, mission_id: str, event_type: str, payload: dict[str, Any]) -> int:
        self._counter[mission_id] = self._counter.get(mission_id, 0) + 1
        event_id = self._counter[mission_id]
        self._events.setdefault(mission_id, []).append((event_id, event_type, payload))
        self._apply(mission_id, event_type, payload)
        return event_id

    def events_since(
        self, mission_id: str, last_event_id: int
    ) -> list[tuple[int, str, dict[str, Any]]]:
        return [e for e in self._events.get(mission_id, []) if e[0] > last_event_id]

    def last_event_id(self, mission_id: str) -> int:
        return self._counter.get(mission_id, 0)

    # -- snapshot ----------------------------------------------------------
    def snapshot(self, mission_id: str) -> dict[str, Any] | None:
        snap = self._snapshots.get(mission_id)
        return json.loads(json.dumps(snap)) if snap is not None else None

    def set_approval(self, mission_id: str, granted: bool) -> None:
        snap = self._snapshots.get(mission_id)
        if snap and snap.get("approval"):
            snap["approval"]["granted"] = granted

    def _apply(self, mission_id: str, event_type: str, payload: dict[str, Any]) -> None:
        """Fold an event into the mission snapshot (replace-by-id semantics)."""
        snap = self._snapshots.get(mission_id)
        if snap is None:
            return

        if event_type == "mission.status" or event_type == "mission.complete":
            snap["status"] = payload["status"]
        elif event_type == "agent.update":
            _upsert_by_id(snap["agents"], payload, "id")
        elif event_type == "edge.update":
            _upsert_by_id(snap["edges"], payload, "id")
        elif event_type == "finding.new":
            _upsert_by_id(snap["findings"], payload, "finding_id")
        elif event_type == "candidate.update":
            _upsert_by_id(snap["candidates"], payload, "candidate_id")
        elif event_type == "approval.required":
            snap["approval"] = {
                "required": True,
                "granted": False,
                "draft": payload["draft"],
            }


def _upsert_by_id(items: list[dict[str, Any]], payload: dict[str, Any], key: str) -> None:
    for i, existing in enumerate(items):
        if existing.get(key) == payload.get(key):
            items[i] = payload
            return
    items.append(payload)


def _initial_snapshot(mission_id: str, repo_url: str) -> dict[str, Any]:
    return {
        "mission_id": mission_id,
        "repo_url": repo_url,
        "status": "QUEUED",
        "created_at": _utc_now_iso(),
        "plan": {
            "goal": f"Analyze {repo_url} for correctness, quality, and security signals.",
            "assumptions": [
                "Repository is public and read-only cloned.",
                "No code is executed against production systems.",
            ],
            "success_criteria": [
                "At least one high-confidence finding with evidence.",
                "Every fix candidate independently verified.",
                "A human-reviewable draft prepared (never auto-submitted).",
            ],
        },
        "agents": [],
        "edges": [],
        "findings": [],
        "candidates": [],
        "approval": None,
    }


def _repo_slug(repo_url: str) -> str:
    parts = [p for p in repo_url.rstrip("/").split("/") if p]
    if len(parts) >= 2:
        return f"{parts[-2]}/{parts[-1]}"
    return "owner/name"


class _FallbackMissionSimulator:
    """Scripted, contract-accurate mission simulation.

    ``steps()`` yields ``(event_type, payload)`` tuples describing a realistic
    Intake -> Static -> Runtime -> Aggregate -> Fix -> Verify -> Approval run.
    The runner appends each step to the store; SSE and REST read from there.
    Includes at least one REJECTED candidate to demonstrate verification.
    """

    def __init__(self, store: Any, mission_id: str, repo_url: str) -> None:
        self.store = store
        self.mission_id = mission_id
        self.repo_url = repo_url
        self.slug = _repo_slug(repo_url)

    def script(self) -> list[tuple[str, dict[str, Any]]]:
        mid = self.mission_id
        slug = self.slug
        events: list[tuple[str, dict[str, Any]]] = []

        def agent(
            aid: str,
            label: str,
            group: str,
            state: str,
            progress: float,
            *,
            result_count: int = 0,
            detail: str = "",
            verifier_of: str | None = None,
            started: bool = True,
        ) -> dict[str, Any]:
            return {
                "id": aid,
                "label": label,
                "group": group,
                "state": state,
                "progress": round(progress, 2),
                "result_count": result_count,
                "started_at": _utc_now_iso() if started else None,
                "detail": detail,
                "verifier_of": verifier_of,
            }

        def edge(eid: str, source: str, target: str, animated: bool) -> dict[str, Any]:
            return {"id": eid, "source": source, "target": target, "animated": animated}

        def log(level: str, agent_id: str, message: str) -> dict[str, Any]:
            return {
                "ts": _utc_now_iso(),
                "level": level,
                "agent_id": agent_id,
                "message": message,
            }

        # --- Planning -----------------------------------------------------
        events.append(("mission.status", {"mission_id": mid, "status": "PLANNING"}))
        events.append(
            (
                "agent.update",
                agent(
                    "control.mission",
                    "Mission Control",
                    "CONTROL",
                    "RUNNING",
                    0.1,
                    detail="Decomposing mission into agent graph",
                ),
            )
        )
        events.append(("log", log("INFO", "control.mission", "Planning agent graph")))

        # --- Graph wiring -------------------------------------------------
        events.append(
            (
                "agent.update",
                agent(
                    "intake.repo",
                    "Repo Intake",
                    "INTAKE",
                    "RUNNING",
                    0.2,
                    detail=f"Cloning {slug} (read-only)",
                ),
            )
        )
        events.append(("edge.update", edge("e1", "control.mission", "intake.repo", True)))
        events.append(
            (
                "agent.update",
                agent(
                    "static.security",
                    "Security Smell Agent",
                    "STATIC",
                    "WAITING",
                    0.0,
                    started=False,
                ),
            )
        )
        events.append(
            (
                "agent.update",
                agent(
                    "static.quality", "Code Quality Agent", "STATIC", "WAITING", 0.0, started=False
                ),
            )
        )
        events.append(
            (
                "agent.update",
                agent(
                    "runtime.repro", "Runtime Repro Agent", "RUNTIME", "WAITING", 0.0, started=False
                ),
            )
        )
        events.append(("edge.update", edge("e2", "intake.repo", "static.security", False)))
        events.append(("edge.update", edge("e3", "intake.repo", "static.quality", False)))
        events.append(("edge.update", edge("e4", "static.security", "runtime.repro", False)))

        events.append(("mission.status", {"mission_id": mid, "status": "RUNNING"}))

        # --- Intake complete ---------------------------------------------
        events.append(
            (
                "agent.update",
                agent(
                    "intake.repo",
                    "Repo Intake",
                    "INTAKE",
                    "COMPLETED",
                    1.0,
                    result_count=1,
                    detail="Cloned; 214 files indexed",
                ),
            )
        )
        events.append(("log", log("INFO", "intake.repo", "Repository indexed (214 files)")))

        # --- Static: security --------------------------------------------
        events.append(("edge.update", edge("e2", "intake.repo", "static.security", True)))
        events.append(
            (
                "agent.update",
                agent(
                    "static.security",
                    "Security Smell Agent",
                    "STATIC",
                    "RUNNING",
                    0.45,
                    detail="scanning subprocess calls",
                ),
            )
        )
        finding_sec = {
            "finding_id": _new_uuid(),
            "category": "SECURITY_SMELL",
            "severity": "HIGH",
            "confidence": 0.82,
            "summary": "Unpinned dependency with known advisory",
            "evidence": [
                {
                    "repo": slug,
                    "commit": "abc123",
                    "path": "setup.py",
                    "start_line": 10,
                    "end_line": 14,
                    "snippet": "install_requires=[\n    'requests==2.0',\n]",
                }
            ],
            "reproduction_required": True,
            "reproduction_status": "REPRODUCED",
            "duplicate_search_terms": ["requests CVE", "unpinned dependency"],
            "suggested_next_step": "Pin dependency to >=2.31",
            "limitations": ["Only static analysis; no runtime confirmation"],
            "agent_id": "static.security",
        }
        events.append(("finding.new", finding_sec))
        events.append(
            (
                "agent.update",
                agent(
                    "static.security",
                    "Security Smell Agent",
                    "STATIC",
                    "COMPLETED",
                    1.0,
                    result_count=1,
                    detail="1 high-severity smell",
                ),
            )
        )
        events.append(
            ("log", log("WARN", "static.security", "HIGH: unpinned dependency in setup.py"))
        )

        # --- Static: quality ---------------------------------------------
        events.append(("edge.update", edge("e3", "intake.repo", "static.quality", True)))
        events.append(
            (
                "agent.update",
                agent(
                    "static.quality",
                    "Code Quality Agent",
                    "STATIC",
                    "RUNNING",
                    0.5,
                    detail="measuring cyclomatic complexity",
                ),
            )
        )
        finding_quality = {
            "finding_id": _new_uuid(),
            "category": "CODE_QUALITY",
            "severity": "MEDIUM",
            "confidence": 0.66,
            "summary": "High-complexity function with no tests",
            "evidence": [
                {
                    "repo": slug,
                    "commit": "abc123",
                    "path": "src/core/handler.py",
                    "start_line": 88,
                    "end_line": 141,
                    "snippet": "def handle(event):\n    ...  # 53 lines, complexity 17",
                }
            ],
            "reproduction_required": False,
            "reproduction_status": "NOT_REQUIRED",
            "duplicate_search_terms": ["cyclomatic complexity handler"],
            "suggested_next_step": "Extract sub-functions and add unit coverage",
            "limitations": ["Complexity heuristic; not a correctness proof"],
            "agent_id": "static.quality",
        }
        events.append(("finding.new", finding_quality))
        events.append(
            (
                "agent.update",
                agent(
                    "static.quality",
                    "Code Quality Agent",
                    "STATIC",
                    "COMPLETED",
                    1.0,
                    result_count=1,
                    detail="1 medium-severity finding",
                ),
            )
        )

        # --- Runtime reproduction ----------------------------------------
        events.append(("edge.update", edge("e4", "static.security", "runtime.repro", True)))
        events.append(
            (
                "agent.update",
                agent(
                    "runtime.repro",
                    "Runtime Repro Agent",
                    "RUNTIME",
                    "RUNNING",
                    0.6,
                    detail="reproducing dependency resolution",
                ),
            )
        )
        events.append(
            (
                "agent.update",
                agent(
                    "runtime.repro",
                    "Runtime Repro Agent",
                    "RUNTIME",
                    "COMPLETED",
                    1.0,
                    result_count=1,
                    detail="Advisory reproduced in clean env",
                ),
            )
        )
        events.append(("log", log("INFO", "runtime.repro", "Reproduced advisory in isolated venv")))

        # --- Aggregate ----------------------------------------------------
        events.append(
            (
                "agent.update",
                agent(
                    "aggregate.dedupe",
                    "Aggregator",
                    "AGGREGATE",
                    "RUNNING",
                    0.5,
                    detail="deduplicating findings",
                ),
            )
        )
        events.append(("edge.update", edge("e5", "static.security", "aggregate.dedupe", True)))
        events.append(("edge.update", edge("e6", "static.quality", "aggregate.dedupe", True)))
        events.append(("edge.update", edge("e7", "runtime.repro", "aggregate.dedupe", True)))
        events.append(
            (
                "agent.update",
                agent(
                    "aggregate.dedupe",
                    "Aggregator",
                    "AGGREGATE",
                    "COMPLETED",
                    1.0,
                    result_count=2,
                    detail="2 unique findings",
                ),
            )
        )

        # --- Fix agents ---------------------------------------------------
        events.append(
            (
                "agent.update",
                agent(
                    "fix.a", "Fix Agent A", "FIX", "RUNNING", 0.4, detail="drafting dependency pin"
                ),
            )
        )
        events.append(("edge.update", edge("e8", "aggregate.dedupe", "fix.a", True)))
        cand_accepted = {
            "candidate_id": _new_uuid(),
            "title": "Pin vulnerable dependency",
            "author_agent": "fix.a",
            "verdict": "PENDING",
            "root_cause": "requests pinned to a version with a known advisory.",
            "risk_level": "LOW",
            "scope_files_changed": 1,
            "unrelated_changes": False,
            "diff": [
                {
                    "path": "setup.py",
                    "old": "requests==2.0",
                    "new": "requests>=2.31",
                    "hunk": "@@ -10,3 +10,3 @@ install_requires=[",
                }
            ],
            "verification": [],
            "verification_summary": "Awaiting independent verification",
        }
        events.append(("candidate.update", cand_accepted))

        events.append(
            (
                "agent.update",
                agent(
                    "fix.b",
                    "Fix Agent B",
                    "FIX",
                    "RUNNING",
                    0.4,
                    detail="attempting broad refactor",
                ),
            )
        )
        events.append(("edge.update", edge("e9", "aggregate.dedupe", "fix.b", True)))
        cand_rejected = {
            "candidate_id": _new_uuid(),
            "title": "Refactor handler and bump unrelated deps",
            "author_agent": "fix.b",
            "verdict": "PENDING",
            "root_cause": "Attempts to fix complexity but touches unrelated modules.",
            "risk_level": "HIGH",
            "scope_files_changed": 9,
            "unrelated_changes": True,
            "diff": [
                {
                    "path": "src/core/handler.py",
                    "old": "def handle(event):",
                    "new": "def handle(event, *, legacy=False):",
                    "hunk": "@@ -88,6 +88,10 @@",
                }
            ],
            "verification": [],
            "verification_summary": "Awaiting independent verification",
        }
        events.append(("candidate.update", cand_rejected))

        # --- Verify (independent verifiers) ------------------------------
        events.append(
            (
                "agent.update",
                agent(
                    "verify.regression",
                    "Regression Verifier",
                    "VERIFY",
                    "VERIFYING",
                    0.5,
                    detail="running regression suite",
                    verifier_of="fix.a",
                ),
            )
        )
        events.append(("edge.update", edge("e10", "fix.a", "verify.regression", True)))
        events.append(
            (
                "agent.update",
                agent(
                    "verify.lint",
                    "Lint Verifier",
                    "VERIFY",
                    "VERIFYING",
                    0.5,
                    detail="running ruff",
                    verifier_of="fix.a",
                ),
            )
        )
        events.append(("edge.update", edge("e11", "fix.a", "verify.lint", True)))

        cand_accepted_final = dict(cand_accepted)
        cand_accepted_final["verdict"] = "ACCEPTED"
        cand_accepted_final["verification"] = [
            {
                "check": "regression_tests",
                "status": "PASS",
                "detail": "142 passed",
                "verifier_agent": "verify.regression",
            },
            {
                "check": "lint",
                "status": "PASS",
                "detail": "ruff clean",
                "verifier_agent": "verify.lint",
            },
            {
                "check": "scope_guard",
                "status": "PASS",
                "detail": "1 file changed; no unrelated edits",
                "verifier_agent": "verify.scope",
            },
        ]
        cand_accepted_final["verification_summary"] = "3/3 checks passed by independent verifiers"
        events.append(("candidate.update", cand_accepted_final))
        events.append(
            (
                "agent.update",
                agent(
                    "verify.regression",
                    "Regression Verifier",
                    "VERIFY",
                    "COMPLETED",
                    1.0,
                    result_count=1,
                    detail="142 passed",
                    verifier_of="fix.a",
                ),
            )
        )
        events.append(
            (
                "agent.update",
                agent(
                    "verify.lint",
                    "Lint Verifier",
                    "VERIFY",
                    "COMPLETED",
                    1.0,
                    result_count=1,
                    detail="ruff clean",
                    verifier_of="fix.a",
                ),
            )
        )
        events.append(
            (
                "agent.update",
                agent(
                    "fix.a",
                    "Fix Agent A",
                    "FIX",
                    "COMPLETED",
                    1.0,
                    result_count=1,
                    detail="candidate accepted",
                ),
            )
        )

        # Reject the over-broad candidate.
        events.append(
            (
                "agent.update",
                agent(
                    "verify.scope",
                    "Scope Verifier",
                    "VERIFY",
                    "VERIFYING",
                    0.5,
                    detail="checking change scope",
                    verifier_of="fix.b",
                ),
            )
        )
        events.append(("edge.update", edge("e12", "fix.b", "verify.scope", True)))
        cand_rejected_final = dict(cand_rejected)
        cand_rejected_final["verdict"] = "REJECTED"
        cand_rejected_final["verification"] = [
            {
                "check": "scope_guard",
                "status": "FAIL",
                "detail": "9 files changed; unrelated modules touched",
                "verifier_agent": "verify.scope",
            },
            {
                "check": "regression_tests",
                "status": "SKIP",
                "detail": "skipped after scope failure",
                "verifier_agent": "verify.regression",
            },
        ]
        cand_rejected_final["verification_summary"] = (
            "Rejected by independent verifier: out-of-scope changes"
        )
        events.append(("candidate.update", cand_rejected_final))
        events.append(
            (
                "agent.update",
                agent(
                    "verify.scope",
                    "Scope Verifier",
                    "VERIFY",
                    "COMPLETED",
                    1.0,
                    result_count=1,
                    detail="scope violation",
                    verifier_of="fix.b",
                ),
            )
        )
        events.append(
            (
                "agent.update",
                agent(
                    "fix.b",
                    "Fix Agent B",
                    "FIX",
                    "REJECTED",
                    1.0,
                    detail="candidate rejected by verifier",
                ),
            )
        )
        events.append(("log", log("ERROR", "verify.scope", "REJECTED fix.b: out-of-scope changes")))

        # --- Approval gate (human-in-the-loop, GitHub writes disabled) ----
        events.append(("mission.status", {"mission_id": mid, "status": "AWAITING_APPROVAL"}))
        draft = {
            "kind": "PR",
            "title": "Pin vulnerable dependency (requests>=2.31)",
            "body_markdown": (
                f"## Summary\n\nPins `requests` to `>=2.31` in `{slug}` to close a "
                "known advisory.\n\n### Verification\n- regression_tests: PASS "
                "(142 passed)\n- lint: PASS (ruff clean)\n- scope_guard: PASS\n\n"
                "_Drafted by CareerForge AI. Human review required; not auto-submitted._"
            ),
            "target_repo": slug,
            "submittable": False,
            "reason_not_submittable": "GitHub writes disabled",
        }
        events.append(("approval.required", {"mission_id": mid, "draft": draft}))
        events.append(
            (
                "agent.update",
                agent(
                    "control.approval",
                    "Approval Gate",
                    "CONTROL",
                    "BLOCKED",
                    1.0,
                    detail="Awaiting human decision (GitHub writes disabled)",
                ),
            )
        )
        events.append(("edge.update", edge("e13", "fix.a", "control.approval", True)))
        events.append(
            ("log", log("INFO", "control.approval", "Draft prepared; awaiting human approval"))
        )

        # --- Complete -----------------------------------------------------
        events.append(("mission.complete", {"mission_id": mid, "status": "COMPLETED"}))

        return events


# ---------------------------------------------------------------------------
# Mission engine — a thin uniform facade over the simulation backend.
#
# Both the real ``careerforge_api.simulation`` store and the in-file fallback
# store expose the same *synchronous* surface the transport layer needs:
#     create(repo_url) -> str
#     exists(id) -> bool
#     append(id, type, payload) -> int
#     events_since(id, last_id) -> [(id, type, payload)]
#     last_event_id(id) -> int          (0 when no events yet)
#     is_complete(id) -> bool
#     mark_complete(id) -> None
#     snapshot(id) -> dict | None
#     set_approval(id, granted) -> None
#     set_plan(id, plan) -> None        (optional)
#     active_agent_count() -> int       (optional)
# Event ids are 1-based in both stores, so a cursor of 0 always means
# "nothing seen yet". The engine below drives the simulator's synchronous
# ``steps()``/``script()`` list, appending events one at a time — the async
# ``run()`` on the live simulator is only used for the streaming background
# task. The endpoints only ever talk to ``ENGINE``.
# ---------------------------------------------------------------------------
class _MissionEngine:
    """Uniform facade over a mission store + simulator pair."""

    def __init__(self, store: Any, simulator_cls: Any, grant_approval: Any | None) -> None:
        self._store = store
        self._simulator_cls = simulator_cls
        self._grant_approval = grant_approval

    # -- lifecycle ---------------------------------------------------------
    def create(self, repo_url: str) -> str:
        return str(self._store.create(repo_url))

    def exists(self, mission_id: str) -> bool:
        return bool(self._store.exists(mission_id))

    def _new_simulator(self, mission_id: str, repo_url: str) -> Any:
        return self._simulator_cls(self._store, mission_id, repo_url)

    def _script(self, simulator: Any) -> list[tuple[str, dict[str, Any]]]:
        getter = getattr(simulator, "script", None) or getattr(simulator, "steps", None)
        return list(getter()) if callable(getter) else []

    def _maybe_set_plan(self, mission_id: str, simulator: Any) -> None:
        plan_fn = getattr(simulator, "_plan", None) or getattr(simulator, "plan", None)
        set_plan = getattr(self._store, "set_plan", None)
        if callable(plan_fn) and callable(set_plan):
            # Plan is best-effort; the snapshot builder supplies a default.
            with contextlib.suppress(Exception):
                set_plan(mission_id, plan_fn())

    async def run(self, mission_id: str, repo_url: str) -> None:
        """Drive the mission for the live SSE stream, pacing events over time."""
        simulator = self._new_simulator(mission_id, repo_url)
        self._maybe_set_plan(mission_id, simulator)
        delay = 0.14 if _is_demo() else 0.0
        for event_type, payload in self._script(simulator):
            self._store.append(mission_id, event_type, payload)
            if delay:
                await asyncio.sleep(delay)
        self._store.mark_complete(mission_id)

    def create_and_run_sync(self, repo_url: str) -> str:
        """Create a mission and fully drain its simulation synchronously.

        Deterministic and non-blocking (no real sleeps): used by tests to
        produce a completed mission and inspect its snapshot without awaiting
        the live stream. Returns the created ``mission_id``.
        """
        mission_id = self.create(repo_url)
        simulator = self._new_simulator(mission_id, repo_url)
        self._maybe_set_plan(mission_id, simulator)
        for event_type, payload in self._script(simulator):
            self._store.append(mission_id, event_type, payload)
        self._store.mark_complete(mission_id)
        return mission_id

    # -- reads -------------------------------------------------------------
    def snapshot(self, mission_id: str) -> dict[str, Any] | None:
        snap = self._store.snapshot(mission_id)
        return dict(snap) if snap is not None else None

    def events_since(
        self, mission_id: str, last_event_id: int
    ) -> list[tuple[int, str, dict[str, Any]]]:
        return list(self._store.events_since(mission_id, last_event_id))

    def last_event_id(self, mission_id: str) -> int:
        return int(self._store.last_event_id(mission_id))

    def is_complete(self, mission_id: str) -> bool:
        return bool(self._store.is_complete(mission_id))

    def active_agent_count(self) -> int:
        counter = getattr(self._store, "active_agent_count", None)
        if callable(counter):
            try:
                return int(counter())
            except Exception:
                return 0
        # Derive from snapshots if the store has no dedicated counter.
        active = 0
        for snap in getattr(self._store, "_snapshots", {}).values():
            for node in snap.get("agents", []):
                if node.get("state") in {"RUNNING", "VERIFYING"}:
                    active += 1
        return active

    # -- approval ----------------------------------------------------------
    def apply_approval(self, mission_id: str, decision: str) -> dict[str, Any]:
        approved = decision.upper() == "APPROVE"
        # Prefer the module's grant_approval() (also sets terminal status).
        if self._grant_approval is not None:
            record = getattr(self._store, "get", lambda _m: None)(mission_id)
            if record is not None:
                return dict(self._grant_approval(record, decision))
        # Fallback path: record the decision on the store directly.
        self._store.set_approval(mission_id, granted=approved)
        return {
            "ok": True,
            "action_taken": "DRAFT_SAVED_LOCALLY" if approved else "DRAFT_DISCARDED",
            "github_write": False,
        }


def _build_engine() -> _MissionEngine:
    """Wire the engine to the real simulation module, else the in-file fallback."""
    try:
        from careerforge_api import simulation as _sim_mod

        store = _sim_mod.get_store()
        simulator_cls = _sim_mod.MissionSimulator
        grant = getattr(_sim_mod, "grant_approval", None)
        # Sanity-check the store surface before committing to it.
        for name in ("create", "exists", "append", "events_since", "snapshot"):
            if not hasattr(store, name):
                raise AttributeError(name)
        return _MissionEngine(store, simulator_cls, grant)
    except Exception:
        return _MissionEngine(_FallbackMissionStore(), _FallbackMissionSimulator, None)


# Process-wide mission engine used by every endpoint.
ENGINE: _MissionEngine = _build_engine()

# Strong references to in-flight background simulation tasks so the event loop
# does not garbage-collect them before they finish (asyncio only holds weakrefs).
_BACKGROUND_TASKS: set[asyncio.Task[Any]] = set()


def _initial_cursor() -> int:
    """Cursor sentinel meaning "no events seen yet" (buffer ids are 1-based)."""
    return 0


def run_mission_sync(repo_url: str) -> str:
    """Create a mission and fully run its simulation synchronously.

    Returns the created ``mission_id``. Used by tests and diagnostics.
    """
    return ENGINE.create_and_run_sync(repo_url)


# ===========================================================================
# Adapter: RAG subsystem (packages/rag_core, wired via rag_service)
# ===========================================================================
# The RAG endpoints and the ``services.rag`` health value are served by the thin
# ``careerforge_api.rag_service`` adapter, which lazily builds the real
# ``rag_core`` pipeline (Ollama/hash embedder + local/server Qdrant) and seeds
# the repo's own docs on first use. Wiring is defensive: if the adapter (or
# ``rag_core``) is missing the app still boots and health simply reports
# ``rag: "down"``.
try:
    from careerforge_api import rag_router as _rag_router_mod
    from careerforge_api import rag_service as _rag_service_mod

    _RAG_ROUTER: Any | None = _rag_router_mod.router

    def _rag_health_label() -> str:
        try:
            return str(_rag_service_mod.health_label())
        except Exception:
            return "down"

except Exception:  # pragma: no cover - RAG optional at boot
    _RAG_ROUTER = None

    def _rag_health_label() -> str:
        return "down"


# ===========================================================================
# Error handling — contract error shape
# ===========================================================================
def _error_response(status_code: int, code: str, message: str, detail: Any = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "detail": detail}},
    )


# ===========================================================================
# FastAPI application
# ===========================================================================
app = FastAPI(
    title="CareerForge AI API",
    version=APP_VERSION,
    description="Local-first multi-agent career-intelligence backend.",
)

app.add_middleware(
    CORSMiddleware,
    # http://localhost:3000 is always allowed (per task); config may add more.
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


@app.exception_handler(StarletteHTTPException)
async def _http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code_map = {
        400: "BAD_REQUEST",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        409: "CONFLICT",
        422: "UNPROCESSABLE_ENTITY",
        500: "INTERNAL_ERROR",
    }
    code = code_map.get(exc.status_code, "ERROR")
    message = exc.detail if isinstance(exc.detail, str) else "Request failed"
    return _error_response(exc.status_code, code, message, None)


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return _error_response(500, "INTERNAL_ERROR", "An unexpected error occurred", str(exc))


# ---------------------------------------------------------------------------
# RAG router (POST /rag/query, POST /rag/index/repository, GET /rag/collections)
# mounted under the shared /api/v1 prefix. Only included when the adapter and
# rag_core imported cleanly; otherwise the endpoints are simply absent and
# health reports rag: "down".
# ---------------------------------------------------------------------------
if _RAG_ROUTER is not None:
    app.include_router(_RAG_ROUTER, prefix=API_PREFIX)


# ---------------------------------------------------------------------------
# Root banner
# ---------------------------------------------------------------------------
@app.get("/")
async def root() -> dict[str, Any]:
    return {
        "name": "CareerForge AI API",
        "version": APP_VERSION,
        "status": "ok",
        "app_env": _app_env(),
        "docs": "/docs",
        "api_base": API_PREFIX,
        "hardware_profile": HARDWARE_PROFILE,
    }


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------
@app.get(f"{API_PREFIX}/system/health")
async def system_health() -> dict[str, Any]:
    # In demo mode all backing services are mocked (no real DB/Qdrant/etc.).
    service_state = "mock" if _is_demo() else "up"
    return {
        "status": "ok",
        "version": _app_version(),
        "services": {
            "api": "up",
            "database": service_state,
            "qdrant": service_state,
            "redis": service_state,
            "ollama": service_state,
            "temporal": service_state,
            # The RAG subsystem is real/local-first even in demo mode, so its
            # health reflects the actually-resolved providers (or "down").
            # e.g. "ollama+qdrant-local" | "hash+qdrant-local" | "down".
            "rag": _rag_health_label(),
        },
        "hardware_profile": HARDWARE_PROFILE,
        "flags": {
            "github_writes": _flag("github_writes", False),
            "repository_execution": _flag("repository_execution", False),
        },
    }


@app.get(f"{API_PREFIX}/system/resources")
async def system_resources() -> dict[str, Any]:
    active = _active_agent_count()
    return _live_resources(active_agents=active, max_agents=_max_agents())


def _active_agent_count() -> int:
    """Count RUNNING/VERIFYING agents across all in-flight missions (best effort)."""
    try:
        return min(int(ENGINE.active_agent_count()), _max_agents())
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Profile Brain
# ---------------------------------------------------------------------------
@app.get(f"{API_PREFIX}/profile")
async def get_profile() -> dict[str, Any]:
    return _seed_profile()


@app.get(f"{API_PREFIX}/skills")
async def get_skills() -> dict[str, Any]:
    return {"skills": _seed_skills()}


@app.get(f"{API_PREFIX}/skills/{{skill_id}}/evidence")
async def get_skill_evidence(skill_id: str) -> dict[str, Any]:
    evidence = _seed_evidence(skill_id)
    if evidence is None:
        raise StarletteHTTPException(status_code=404, detail="Skill not found")
    return {"skill_id": skill_id, "evidence": evidence}


async def _read_resume_text(request: Request) -> str:
    """Extract resume text from a JSON body or a multipart/form upload.

    Supports three shapes:
      * JSON ``{ "text": "..." }``
      * multipart/form-data with a ``text`` field
      * multipart/form-data with an uploaded file (``file``/``resume``/first file)
    Any parse failure degrades to an empty string (yielding zero claims), never
    a 500.
    """
    content_type = (request.headers.get("content-type") or "").lower()

    if "application/json" in content_type:
        try:
            body = await request.json()
        except Exception:
            return ""
        if isinstance(body, dict):
            value = body.get("text", "")
            return value if isinstance(value, str) else ""
        return ""

    if "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
        try:
            form = await request.form()
        except Exception:
            return ""
        # Prefer an explicit text field.
        text_field = form.get("text")
        if isinstance(text_field, str) and text_field:
            return text_field
        # Otherwise take the first uploaded file's decoded contents. We
        # duck-type on an awaitable ``read`` rather than isinstance-checking a
        # specific UploadFile class, since Starlette's and FastAPI's UploadFile
        # types are not always identical.
        for key in ("file", "resume", *form.keys()):
            candidate = form.get(key)
            reader = getattr(candidate, "read", None)
            if candidate is not None and not isinstance(candidate, str) and callable(reader):
                try:
                    raw = await candidate.read()
                    if isinstance(raw, bytes):
                        return raw.decode("utf-8", errors="replace")
                    return str(raw)
                except Exception:
                    return ""
        return ""

    # Unknown content type: attempt JSON as a best effort.
    try:
        body = await request.json()
        if isinstance(body, dict):
            value = body.get("text", "")
            return value if isinstance(value, str) else ""
    except Exception:
        pass
    return ""


@app.post(f"{API_PREFIX}/profile/ingest-resume")
async def ingest_resume(request: Request) -> dict[str, Any]:
    """Extract skill *claims* from a resume.

    Accepts either JSON ``{"text": "..."}`` or a multipart upload (``file`` or a
    ``text`` form field). Every returned claim is SELF_DECLARED — ingestion
    never fabricates verification, no matter what the underlying parser returns.
    """
    resume_text = await _read_resume_text(request)
    claims = _extract_resume_claims(resume_text)
    # Hard invariant: resume ingestion only ever yields SELF_DECLARED claims.
    for claim in claims:
        claim["evidence_level"] = "SELF_DECLARED"
    return {"claims": claims}


# ---------------------------------------------------------------------------
# Repositories & Analysis (flagship flow)
# ---------------------------------------------------------------------------
@app.post(f"{API_PREFIX}/repositories/analyze", status_code=202)
async def analyze_repository(
    payload: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    repo_url = str(payload.get("repo_url", "")).strip()
    if not repo_url:
        raise StarletteHTTPException(status_code=400, detail="repo_url is required")

    mission_id = ENGINE.create(repo_url)

    # Launch the background simulation. It folds events into the mission store,
    # which both the REST snapshot endpoint and the SSE stream read from. The
    # task is retained so it is not garbage-collected mid-flight.
    task = asyncio.create_task(ENGINE.run(mission_id, repo_url))
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)

    return {"mission_id": mission_id, "status": "QUEUED"}


@app.get(f"{API_PREFIX}/missions/{{mission_id}}")
async def get_mission(mission_id: str) -> dict[str, Any]:
    if not ENGINE.exists(mission_id):
        raise StarletteHTTPException(status_code=404, detail="Mission not found")
    snapshot = ENGINE.snapshot(mission_id)
    if snapshot is None:
        raise StarletteHTTPException(status_code=404, detail="Mission not found")
    return snapshot


@app.post(f"{API_PREFIX}/approvals/{{mission_id}}")
async def submit_approval(
    mission_id: str,
    payload: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    if not ENGINE.exists(mission_id):
        raise StarletteHTTPException(status_code=404, detail="Mission not found")

    decision = str(payload.get("decision", "")).upper()
    if decision not in {"APPROVE", "REJECT"}:
        raise StarletteHTTPException(status_code=400, detail="decision must be APPROVE or REJECT")

    # Record the human decision. This NEVER performs a GitHub write: the draft
    # is only saved locally. ``github_write`` is always false by contract, and
    # the API layer never calls any GitHub API here regardless of the decision.
    response = ENGINE.apply_approval(mission_id, decision)
    response["github_write"] = False  # hard invariant, never trust the backend
    return response


# ---------------------------------------------------------------------------
# Industry Pulse
# ---------------------------------------------------------------------------
@app.get(f"{API_PREFIX}/pulse")
async def get_pulse() -> dict[str, Any]:
    return {"items": _seed_pulse()}


# ---------------------------------------------------------------------------
# SSE event stream
# ---------------------------------------------------------------------------
def _parse_last_event_id(request: Request) -> int | None:
    """Read the SSE Last-Event-ID header (or ?lastEventId= fallback).

    Returns ``None`` when no cursor was supplied (fresh connection → replay the
    full buffer), else the integer id the client last saw.
    """
    raw = request.headers.get("last-event-id") or request.query_params.get("lastEventId")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _resource_event_payload() -> str:
    """JSON for the SSE ``resource`` event.

    Per API_CONTRACT.md the SSE ``resource`` payload is the 3-field subset
    ``{ cpu_percent, ram_used_mb, active_agents }`` (a subset of the
    ``/system/resources`` REST body).
    """
    full = _live_resources(_active_agent_count(), _max_agents())
    return json.dumps(
        {
            "cpu_percent": full["cpu_percent"],
            "ram_used_mb": full["ram_used_mb"],
            "active_agents": full["active_agents"],
        }
    )


async def _sse_event_generator(
    request: Request, mission_id: str, last_event_id: int | None
) -> AsyncIterator[dict[str, Any]]:
    """Yield SSE events for a mission.

    Replays everything after ``last_event_id`` (reconnect support), then tails
    new events, emitting periodic heartbeat comments to keep the connection
    alive. Also emits a ``resource`` event on connect and on each heartbeat.
    """
    # Emit a resource snapshot immediately so the UI gauges are never empty.
    yield {"event": "resource", "data": _resource_event_payload()}

    # ``cursor`` is the id of the last event we've emitted. When the client did
    # not send Last-Event-ID we start from the engine's "nothing seen" sentinel
    # so the full buffer replays.
    cursor = _initial_cursor() if last_event_id is None else last_event_id
    last_heartbeat = time.monotonic()

    while True:
        if await request.is_disconnected():
            break

        pending = ENGINE.events_since(mission_id, cursor)
        for event_id, event_type, payload in pending:
            cursor = event_id
            yield {
                "id": str(event_id),
                "event": event_type,
                "data": json.dumps(payload),
            }

        # Stop tailing once the mission is complete and fully drained.
        if ENGINE.is_complete(mission_id) and cursor >= ENGINE.last_event_id(mission_id):
            # Final resource ping so gauges settle to idle.
            yield {"event": "resource", "data": _resource_event_payload()}
            break

        now = time.monotonic()
        if now - last_heartbeat >= SSE_HEARTBEAT_SECONDS:
            last_heartbeat = now
            # sse-starlette renders `comment` as an SSE `:` comment line.
            yield {"comment": "heartbeat"}
            yield {"event": "resource", "data": _resource_event_payload()}

        await asyncio.sleep(0.1)


@app.get(f"{API_PREFIX}/events/stream")
async def events_stream(request: Request, mission_id: str) -> EventSourceResponse:
    if not ENGINE.exists(mission_id):
        raise StarletteHTTPException(status_code=404, detail="Mission not found")

    last_event_id = _parse_last_event_id(request)
    generator = _sse_event_generator(request, mission_id, last_event_id)
    return EventSourceResponse(
        generator,
        ping=int(SSE_HEARTBEAT_SECONDS),
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Metadata used by the entrypoint / diagnostics.
# ---------------------------------------------------------------------------
def app_info() -> dict[str, Any]:
    return {
        "version": APP_VERSION,
        "app_env": _app_env(),
        "hardware_profile": HARDWARE_PROFILE,
        "platform": platform.system(),
        "python": platform.python_version(),
    }
