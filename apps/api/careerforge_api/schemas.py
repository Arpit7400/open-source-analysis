"""Pydantic v2 schemas — the frontend/backend data contract.

Every model and enum here mirrors ``docs/API_CONTRACT.md`` **exactly**: field
names, JSON shapes, and enum spellings (UPPER_SNAKE) are load-bearing and must
not drift. This module is imported by every other backend file, so the names
defined here are the canonical source of truth.

Conventions honoured from the contract:

* IDs are UUID strings (kept as ``str`` so we never reformat/upper-case them).
* Enums are UPPER_SNAKE strings and subclass ``str`` for transparent JSON.
* Timestamps are ISO-8601 UTC strings; we accept :class:`datetime` on input and
  keep the field types permissive where the contract shows ``"..."`` examples.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Enums (exact spellings from API_CONTRACT.md § Enums)
# ---------------------------------------------------------------------------


class VerificationLevel(str, Enum):
    """How strongly a skill/evidence claim has been verified."""

    SELF_DECLARED = "SELF_DECLARED"
    AI_INFERRED = "AI_INFERRED"
    TOOL_VERIFIED = "TOOL_VERIFIED"
    HUMAN_REVIEWED = "HUMAN_REVIEWED"
    EXTERNALLY_VALIDATED = "EXTERNALLY_VALIDATED"


class AgentState(str, Enum):
    """Lifecycle state of an agent node in the mission graph."""

    WAITING = "WAITING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    VERIFYING = "VERIFYING"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"


class Severity(str, Enum):
    """Severity of a finding."""

    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class FindingCategory(str, Enum):
    """Category of a static/runtime finding."""

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


class ReproductionStatus(str, Enum):
    """Whether a finding has been reproduced."""

    NOT_REQUIRED = "NOT_REQUIRED"
    PENDING = "PENDING"
    REPRODUCED = "REPRODUCED"
    NOT_REPRODUCED = "NOT_REPRODUCED"


class MissionStatus(str, Enum):
    """Overall status of an analysis mission."""

    QUEUED = "QUEUED"
    PLANNING = "PLANNING"
    RUNNING = "RUNNING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class CandidateVerdict(str, Enum):
    """Verdict on a fix candidate after independent verification."""

    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    NO_SUBMISSION = "NO_SUBMISSION"
    PENDING = "PENDING"


class RiskLevel(str, Enum):
    """Risk level of applying a candidate change."""

    SAFE = "SAFE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    BLOCKED = "BLOCKED"


# ---------------------------------------------------------------------------
# Supporting enums referenced inline by the contract (not in the § Enums list
# but present in the JSON shapes; declared as Literal-style enums for clarity).
# ---------------------------------------------------------------------------


class ServiceStatus(str, Enum):
    """Per-service health status used in the health endpoint."""

    UP = "up"
    DOWN = "down"
    MOCK = "mock"


class HardwareProfileName(str, Enum):
    """Hardware profile band reported by the health endpoint.

    Mirrors ``careerforge_api.hardware.HardwareProfile`` values.
    """

    CPU_LOW = "CPU_LOW"
    VRAM_8_12 = "VRAM_8_12"
    VRAM_16_24 = "VRAM_16_24"
    WORKSTATION = "WORKSTATION"


class AgentGroup(str, Enum):
    """Functional group an agent node belongs to (drives graph rendering)."""

    STATIC = "STATIC"
    RUNTIME = "RUNTIME"
    INTAKE = "INTAKE"
    DUPLICATE = "DUPLICATE"
    FIX = "FIX"
    VERIFY = "VERIFY"
    CONTROL = "CONTROL"
    AGGREGATE = "AGGREGATE"


class EvidenceType(str, Enum):
    """Type of evidence backing a skill."""

    COMMIT = "COMMIT"
    TEST = "TEST"
    DOC = "DOC"
    PR = "PR"
    PROJECT = "PROJECT"


class VerificationStatus(str, Enum):
    """Outcome of a single verification check on a candidate."""

    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"


class DraftKind(str, Enum):
    """Kind of GitHub artifact a draft represents."""

    ISSUE = "ISSUE"
    PR = "PR"


class PulseSource(str, Enum):
    """Source of an industry-pulse item."""

    ARXIV = "arXiv"
    GITHUB = "GitHub"
    BLOG = "Blog"
    ADVISORY = "Advisory"


class LogLevel(str, Enum):
    """Log level for streamed log events."""

    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


class ApprovalDecision(str, Enum):
    """Human decision on an approval gate."""

    APPROVE = "APPROVE"
    REJECT = "REJECT"


# ---------------------------------------------------------------------------
# Base model
# ---------------------------------------------------------------------------


class _Base(BaseModel):
    """Shared base with strict, forward-compatible config.

    ``use_enum_values=False`` keeps enum members typed in Python while still
    serialising to their string values via the ``str`` subclass. ``extra`` is
    ignored so additive contract changes never crash deserialization.
    """

    model_config = ConfigDict(
        extra="ignore",
        populate_by_name=True,
        use_enum_values=False,
        ser_json_timedelta="iso8601",
    )


# ---------------------------------------------------------------------------
# System — health & resources
# ---------------------------------------------------------------------------


class Resources(_Base):
    """``GET /api/v1/system/resources`` payload / ``resource`` SSE event."""

    cpu_percent: float = Field(ge=0.0)
    ram_used_mb: int = Field(ge=0)
    ram_total_mb: int = Field(ge=0)
    active_agents: int = Field(ge=0)
    max_agents: int = Field(ge=0)


class HealthServices(_Base):
    """Per-service health map for the health endpoint."""

    api: ServiceStatus = ServiceStatus.UP
    database: ServiceStatus = ServiceStatus.MOCK
    qdrant: ServiceStatus = ServiceStatus.MOCK
    redis: ServiceStatus = ServiceStatus.MOCK
    ollama: ServiceStatus = ServiceStatus.MOCK
    temporal: ServiceStatus = ServiceStatus.MOCK


class HealthFlags(_Base):
    """Feature-flag view exposed in the health endpoint."""

    github_writes: bool = False
    repository_execution: bool = False


class Health(_Base):
    """``GET /api/v1/system/health`` payload."""

    status: str = "ok"
    version: str = "1.0.0"
    services: HealthServices = Field(default_factory=HealthServices)
    hardware_profile: HardwareProfileName
    flags: HealthFlags = Field(default_factory=HealthFlags)


# ---------------------------------------------------------------------------
# Profile Brain
# ---------------------------------------------------------------------------


class Profile(_Base):
    """``GET /api/v1/profile`` payload."""

    user_id: str
    name: str
    headline: str
    goals: list[str] = Field(default_factory=list)
    verified_skill_count: int = Field(ge=0)
    merged_prs: int = Field(ge=0)
    evidence_count: int = Field(ge=0)


class Skill(_Base):
    """A single skill in ``GET /api/v1/skills``."""

    id: str
    name: str
    category: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_strength: float = Field(ge=0.0, le=1.0)
    recency: float = Field(ge=0.0, le=1.0)
    complexity: float = Field(ge=0.0, le=1.0)
    independence: float = Field(ge=0.0, le=1.0)
    verification_level: VerificationLevel
    evidence_ids: list[str] = Field(default_factory=list)
    last_updated: datetime
    last_change_reason: str
    related_skill_ids: list[str] = Field(default_factory=list)


class SkillList(_Base):
    """Envelope for ``GET /api/v1/skills``."""

    skills: list[Skill] = Field(default_factory=list)


class Evidence(_Base):
    """A single evidence item backing a skill."""

    id: str
    type: EvidenceType
    summary: str
    source_url: str
    verification_level: VerificationLevel
    created_at: datetime


class EvidenceList(_Base):
    """Envelope for ``GET /api/v1/skills/{id}/evidence``."""

    skill_id: str
    evidence: list[Evidence] = Field(default_factory=list)


class ResumeIngestRequest(_Base):
    """JSON body variant of ``POST /api/v1/profile/ingest-resume``.

    The multipart/file variant is handled at the route layer; this covers the
    ``{ "text": "..." }`` shape.
    """

    text: str


class ResumeClaim(_Base):
    """A single extracted resume claim — a *claim*, never auto-verified."""

    skill: str
    evidence_level: VerificationLevel = VerificationLevel.SELF_DECLARED
    raw_span: str


class ResumeClaims(_Base):
    """Envelope returned by ``POST /api/v1/profile/ingest-resume``."""

    claims: list[ResumeClaim] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Repositories & Analysis
# ---------------------------------------------------------------------------


class AnalyzeRequest(_Base):
    """``POST /api/v1/repositories/analyze`` request body."""

    repo_url: str


class AnalyzeResponse(_Base):
    """``POST /api/v1/repositories/analyze`` response body."""

    mission_id: str
    status: MissionStatus = MissionStatus.QUEUED


class MissionPlan(_Base):
    """The planner's output attached to a mission."""

    goal: str
    assumptions: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)


class AgentNode(_Base):
    """A node in the live agent graph.

    ``verifier_of`` is the id of the candidate/agent this node verifies, or
    ``None`` when the node is not a verifier.
    """

    id: str
    label: str
    group: AgentGroup
    state: AgentState
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    result_count: int = Field(default=0, ge=0)
    started_at: datetime | None = None
    detail: str | None = None
    verifier_of: str | None = None


class GraphEdge(_Base):
    """A directed edge in the agent graph."""

    id: str
    source: str
    target: str
    animated: bool = False


class EvidenceRef(_Base):
    """A concrete code reference backing a finding (file:line + snippet)."""

    repo: str
    commit: str
    path: str
    start_line: int = Field(ge=0)
    end_line: int = Field(ge=0)
    snippet: str


class Finding(_Base):
    """A finding produced by a static/runtime agent."""

    finding_id: str
    category: FindingCategory
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str
    evidence: list[EvidenceRef] = Field(default_factory=list)
    reproduction_required: bool = False
    reproduction_status: ReproductionStatus = ReproductionStatus.NOT_REQUIRED
    duplicate_search_terms: list[str] = Field(default_factory=list)
    suggested_next_step: str
    limitations: list[str] = Field(default_factory=list)
    agent_id: str


class DiffLine(_Base):
    """A single proposed change within a candidate diff."""

    path: str
    old: str
    new: str
    hunk: str


class VerificationCheck(_Base):
    """A single verification check performed by an independent verifier."""

    check: str
    status: VerificationStatus
    detail: str
    verifier_agent: str


class Candidate(_Base):
    """A proposed fix candidate with its verification results."""

    candidate_id: str
    title: str
    author_agent: str
    verdict: CandidateVerdict = CandidateVerdict.PENDING
    root_cause: str
    risk_level: RiskLevel = RiskLevel.LOW
    scope_files_changed: int = Field(ge=0)
    unrelated_changes: bool = False
    diff: list[DiffLine] = Field(default_factory=list)
    verification: list[VerificationCheck] = Field(default_factory=list)
    verification_summary: str


class Draft(_Base):
    """An issue/PR draft — never auto-submitted while writes are disabled."""

    kind: DraftKind
    title: str
    body_markdown: str
    target_repo: str
    submittable: bool = False
    reason_not_submittable: str | None = None


class MissionApproval(_Base):
    """The ``approval`` block attached to a mission when human sign-off is due."""

    required: bool = True
    granted: bool = False
    draft: Draft | None = None


class Mission(_Base):
    """``GET /api/v1/missions/{mission_id}`` payload."""

    mission_id: str
    repo_url: str
    status: MissionStatus
    created_at: datetime
    plan: MissionPlan | None = None
    agents: list[AgentNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    candidates: list[Candidate] = Field(default_factory=list)
    approval: MissionApproval | None = None


class ApprovalRequest(_Base):
    """``POST /api/v1/approvals/{mission_id}`` request body."""

    decision: ApprovalDecision
    note: str | None = None


class ApprovalResponse(_Base):
    """``POST /api/v1/approvals/{mission_id}`` response body."""

    ok: bool = True
    action_taken: str = "DRAFT_SAVED_LOCALLY"
    github_write: bool = False


# ---------------------------------------------------------------------------
# Industry Pulse
# ---------------------------------------------------------------------------


class PulseItem(_Base):
    """A single industry-pulse item."""

    id: str
    title: str
    source: PulseSource
    technology: str
    published_at: datetime
    momentum: float = Field(ge=0.0, le=1.0)
    personal_relevance: float = Field(ge=0.0, le=1.0)
    actionability: float = Field(ge=0.0, le=1.0)
    why_it_matters: str
    skill_gap: str
    suggested_action: str
    canonical_url: str


class PulseList(_Base):
    """Envelope for ``GET /api/v1/pulse``."""

    items: list[PulseItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# SSE event payloads
# ---------------------------------------------------------------------------


class MissionStatusEvent(_Base):
    """``mission.status`` and ``mission.complete`` SSE payload."""

    mission_id: str
    status: MissionStatus


class LogEvent(_Base):
    """``log`` SSE payload."""

    ts: datetime
    level: LogLevel
    agent_id: str | None = None
    message: str


class ResourceEvent(_Base):
    """``resource`` SSE payload (subset of :class:`Resources`)."""

    cpu_percent: float = Field(ge=0.0)
    ram_used_mb: int = Field(ge=0)
    active_agents: int = Field(ge=0)


class ApprovalRequiredEvent(_Base):
    """``approval.required`` SSE payload."""

    mission_id: str
    draft: Draft


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ErrorBody(_Base):
    """The inner object of the standard error envelope."""

    code: str
    message: str
    detail: object | None = None


class ErrorResponse(_Base):
    """``{ "error": { "code", "message", "detail" } }`` envelope."""

    error: ErrorBody


__all__ = [
    # Enums (contract § Enums)
    "VerificationLevel",
    "AgentState",
    "Severity",
    "FindingCategory",
    "ReproductionStatus",
    "MissionStatus",
    "CandidateVerdict",
    "RiskLevel",
    # Supporting enums
    "ServiceStatus",
    "HardwareProfileName",
    "AgentGroup",
    "EvidenceType",
    "VerificationStatus",
    "DraftKind",
    "PulseSource",
    "LogLevel",
    "ApprovalDecision",
    # System
    "Resources",
    "HealthServices",
    "HealthFlags",
    "Health",
    # Profile Brain
    "Profile",
    "Skill",
    "SkillList",
    "Evidence",
    "EvidenceList",
    "ResumeIngestRequest",
    "ResumeClaim",
    "ResumeClaims",
    # Repositories & Analysis
    "AnalyzeRequest",
    "AnalyzeResponse",
    "MissionPlan",
    "AgentNode",
    "GraphEdge",
    "EvidenceRef",
    "Finding",
    "DiffLine",
    "VerificationCheck",
    "Candidate",
    "Draft",
    "MissionApproval",
    "Mission",
    "ApprovalRequest",
    "ApprovalResponse",
    # Industry Pulse
    "PulseItem",
    "PulseList",
    # SSE events
    "MissionStatusEvent",
    "LogEvent",
    "ResourceEvent",
    "ApprovalRequiredEvent",
    # Errors
    "ErrorBody",
    "ErrorResponse",
]
