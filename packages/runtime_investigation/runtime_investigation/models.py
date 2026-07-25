"""Typed models for runtime investigation (Phase 7)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class EnvironmentInfo(BaseModel):
    """Detected characteristics of a repository's Python environment."""

    has_pyproject: bool = False
    has_setup_py: bool = False
    has_requirements: bool = False
    has_tests: bool = False
    test_runner: str = "pytest"  # pytest | unittest | none
    python_files: int = 0
    declared_python: str | None = None


class RuntimeStep(BaseModel):
    """One executed (or refused) runtime step, wrapping a sandbox command."""

    name: str  # install | tests | lint | type | import_check | example
    command: list[str] = Field(default_factory=list)
    executed: bool = False
    exit_code: int | None = None
    passed: bool | None = None
    duration_ms: int = 0
    summary: str = ""
    stdout_tail: str = ""
    stderr_tail: str = ""


class RuntimeFinding(BaseModel):
    """A runtime finding (matches the API Finding shape; category RUNTIME)."""

    finding_id: str
    category: str = "RUNTIME"
    severity: str = "MEDIUM"
    confidence: float = Field(ge=0.0, le=1.0, default=0.7)
    summary: str = ""
    evidence: list[dict[str, object]] = Field(default_factory=list)
    reproduction_required: bool = True
    reproduction_status: str = "PENDING"  # PENDING | REPRODUCED | NOT_REPRODUCED | NOT_REQUIRED
    suggested_next_step: str = ""
    limitations: list[str] = Field(default_factory=list)
    agent_id: str = "runtime.investigator"


class RuntimeReport(BaseModel):
    """Full runtime-investigation report for a repository."""

    repo_path: str
    executed: bool = False
    reason: str = ""
    environment: EnvironmentInfo = Field(default_factory=EnvironmentInfo)
    steps: list[RuntimeStep] = Field(default_factory=list)
    findings: list[RuntimeFinding] = Field(default_factory=list)
    reproduction_status: str = "PENDING"
