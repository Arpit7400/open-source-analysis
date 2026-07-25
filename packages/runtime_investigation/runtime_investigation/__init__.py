"""Runtime investigation (Phase 7).

Environment detection + sandboxed install/tests/lint/type/reproduction, composing
the gated Phase 6 sandbox. Produces typed runtime findings and a reproduction
report. Safe everywhere: when execution is disabled it returns a complete
PLANNED report instead of running anything.
"""

from __future__ import annotations

from runtime_investigation.detect import detect_environment
from runtime_investigation.investigator import RuntimeInvestigator
from runtime_investigation.models import (
    EnvironmentInfo,
    RuntimeFinding,
    RuntimeReport,
    RuntimeStep,
)

__all__ = [
    "EnvironmentInfo",
    "RuntimeFinding",
    "RuntimeInvestigator",
    "RuntimeReport",
    "RuntimeStep",
    "detect_environment",
]
