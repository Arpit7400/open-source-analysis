"""Typed models for the restricted repository sandbox (Phase 6)."""

from __future__ import annotations

from pydantic import BaseModel, Field

RISK_LEVELS = ("SAFE", "LOW", "MEDIUM", "HIGH", "BLOCKED")


class PreflightIssue(BaseModel):
    """One suspicious pattern found by the static safety preflight."""

    category: str  # INSTALL_HOOK | NETWORK | DESTRUCTIVE | CREDENTIAL | SUBPROCESS | TRAVERSAL | OBFUSCATION
    severity: str  # LOW | MEDIUM | HIGH
    path: str
    line: int
    snippet: str
    explanation: str


class PreflightResult(BaseModel):
    """Result of the static safety preflight over a repository."""

    repo_path: str
    risk_level: str = "SAFE"
    issues: list[PreflightIssue] = Field(default_factory=list)
    files_scanned: int = 0
    execution_allowed: bool = False
    reason: str = ""


class PolicyDecision(BaseModel):
    """Whether a single command is allowed to run in the sandbox."""

    command: list[str]
    allowed: bool
    reason: str


class ResourceLimits(BaseModel):
    """Container resource caps (mirrors .env MAX_SANDBOX_* defaults)."""

    memory_mb: int = 4096
    cpus: float = 2.0
    pids: int = 256
    wall_seconds: int = 900
    network: bool = False  # network disabled during tests by default


class SandboxCommand(BaseModel):
    """An audited command execution record."""

    command: list[str]
    exit_code: int | None = None
    duration_ms: int = 0
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    stage: str = "test"  # install | test | example | lint | type


class SandboxRun(BaseModel):
    """Full record of a sandbox run (audit trail)."""

    repo_path: str
    image: str = ""
    executed: bool = False
    limits: ResourceLimits = Field(default_factory=ResourceLimits)
    preflight: PreflightResult | None = None
    commands: list[SandboxCommand] = Field(default_factory=list)
    note: str = ""
