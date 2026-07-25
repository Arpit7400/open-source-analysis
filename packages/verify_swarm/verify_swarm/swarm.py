"""Verification swarm + quality gate (Phase 10).

Runs every independent verifier over a candidate, then applies a deterministic
quality gate that maps the check results to a final verdict:

* Any FAIL on a *critical* check (syntax, scope, adversarial) -> REJECTED.
* A ``NO_SUBMISSION`` candidate stays NO_SUBMISSION (it is the honest outcome).
* Otherwise, with no failing critical checks and at least one substantive PASS
  -> ACCEPTED.

Guarantees the handbook rule: **patch authors do not verify their own output.**
Every ``verifier_agent`` id starts with ``verify.`` and differs from the
candidate's ``author_agent`` (``fix.*``); the gate asserts this.
"""

from __future__ import annotations

from pathlib import Path

from patch_gen.models import Candidate

from verify_swarm.verifiers import ALL_VERIFIERS

_CRITICAL = {"syntax", "scope", "adversarial"}


def verify_candidate(repo_root: str | Path, cand: Candidate) -> Candidate:
    """Run the swarm over one candidate and return it with verdict + checks set.

    The returned candidate is a copy with ``verification``, ``verification_summary``,
    and ``verdict`` populated. The input candidate is not mutated.
    """
    root = Path(repo_root).expanduser()

    checks = [verifier(root, cand) for verifier in ALL_VERIFIERS]

    # Enforce independence: a verifier must never be the patch author.
    for c in checks:
        assert c.verifier_agent.startswith("verify."), c.verifier_agent
        assert c.verifier_agent != cand.author_agent

    failed = [c for c in checks if c.status == "FAIL"]
    failed_critical = [c for c in failed if c.check in _CRITICAL]
    passed = [c for c in checks if c.status == "PASS"]

    if cand.verdict == "NO_SUBMISSION":
        verdict = "NO_SUBMISSION"
    elif failed_critical:
        verdict = "REJECTED"
    elif failed:
        # non-critical failure (lint/type regression) -> reject conservatively
        verdict = "REJECTED"
    elif passed:
        verdict = "ACCEPTED"
    else:
        verdict = "REJECTED"  # nothing could be verified -> do not submit

    n_pass = len(passed)
    n_total = len([c for c in checks if c.status != "SKIP"])
    summary = (
        f"{verdict}: {n_pass}/{n_total} checks passed by independent verifiers"
        + (f"; failures: {', '.join(c.check for c in failed)}" if failed else "")
    )

    return cand.model_copy(
        update={
            "verification": checks,
            "verification_summary": summary,
            "verdict": verdict,
        }
    )


def verify_candidates(repo_root: str | Path, candidates: list[Candidate]) -> list[Candidate]:
    """Verify a set of candidates independently, returning verdict-annotated copies."""
    return [verify_candidate(repo_root, c) for c in candidates]
