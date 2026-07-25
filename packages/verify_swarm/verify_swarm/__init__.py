"""Independent verification swarm + quality gate (Phase 10).

Verifies candidate patches produced by ``patch_gen`` using independent
``verify.*`` agents (never the patch author), then a deterministic quality gate
yields ACCEPTED | REJECTED | NO_SUBMISSION.
"""

from __future__ import annotations

from verify_swarm.swarm import verify_candidate, verify_candidates
from verify_swarm.verifiers import (
    ALL_VERIFIERS,
    verify_adversary,
    verify_lint,
    verify_scope,
    verify_syntax,
    verify_type,
)

__all__ = [
    "ALL_VERIFIERS",
    "verify_adversary",
    "verify_candidate",
    "verify_candidates",
    "verify_lint",
    "verify_scope",
    "verify_syntax",
    "verify_type",
]
