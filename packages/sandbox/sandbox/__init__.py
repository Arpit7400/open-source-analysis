"""Restricted repository sandbox (Phase 6).

Static safety preflight + command policy engine + a hardened, gated Docker
runner. Execution is OFF by default (repository_execution flag) and blocked
outright for HIGH-risk repositories. Safe to import without Docker: the runner
no-ops with a clear reason when a gate fails.
"""

from __future__ import annotations

from sandbox.models import (
    PolicyDecision,
    PreflightIssue,
    PreflightResult,
    ResourceLimits,
    SandboxCommand,
    SandboxRun,
)
from sandbox.policy import validate_all, validate_command
from sandbox.preflight import run_preflight
from sandbox.runner import (
    DEFAULT_IMAGE,
    SandboxRunner,
    build_run_args,
    container_engine,
    engine_available,
)

__all__ = [
    "DEFAULT_IMAGE",
    "PolicyDecision",
    "PreflightIssue",
    "PreflightResult",
    "ResourceLimits",
    "SandboxCommand",
    "SandboxRun",
    "SandboxRunner",
    "build_run_args",
    "container_engine",
    "engine_available",
    "run_preflight",
    "validate_all",
    "validate_command",
]
