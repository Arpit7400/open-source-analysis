"""Typed findings emitted by the static-analysis agents.

These mirror ``docs/API_CONTRACT.md`` / ``careerforge_api.schemas`` (Finding,
EvidenceRef) EXACTLY so the API can serialize them without translation. The
enums are duplicated here as plain string constants (the package is standalone
and must not import the API), but the *values* are frozen by the contract.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# --- Contract enum values (UPPER_SNAKE strings, frozen by API_CONTRACT.md) ---
CATEGORIES = (
    "ARCHITECTURE",
    "CODE_QUALITY",
    "DOCS_DRIFT",
    "DEPENDENCY",
    "TEST_QUALITY",
    "TYPING",
    "API_CONSISTENCY",
    "SECURITY_SMELL",
    "DEPRECATION",
    "RUNTIME",
)
SEVERITIES = ("INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL")
REPRODUCTION = ("NOT_REQUIRED", "PENDING", "REPRODUCED", "NOT_REPRODUCED")


class EvidenceRef(BaseModel):
    """A precise pointer to the evidence backing a finding (contract shape)."""

    repo: str | None = None
    commit: str | None = None
    path: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    snippet: str | None = None


class Finding(BaseModel):
    """A single static-analysis finding (matches ``careerforge_api.schemas.Finding``)."""

    finding_id: str
    category: str
    severity: str
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str
    evidence: list[EvidenceRef] = Field(default_factory=list)
    reproduction_required: bool = False
    reproduction_status: str = "NOT_REQUIRED"
    duplicate_search_terms: list[str] = Field(default_factory=list)
    suggested_next_step: str = ""
    limitations: list[str] = Field(default_factory=list)
    agent_id: str = ""


class AgentReport(BaseModel):
    """The result of one analysis agent over a repository."""

    agent_id: str
    ok: bool
    findings: list[Finding] = Field(default_factory=list)
    note: str = ""


class AnalysisResult(BaseModel):
    """Aggregate result of a full static analysis run."""

    repo_path: str
    repo_id: str | None = None
    commit: str | None = None
    reports: list[AgentReport] = Field(default_factory=list)

    @property
    def findings(self) -> list[Finding]:
        out: list[Finding] = []
        for r in self.reports:
            out.extend(r.findings)
        return out
