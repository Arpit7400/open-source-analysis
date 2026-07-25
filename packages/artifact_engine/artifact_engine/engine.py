"""Skill-to-artifact engine (Phase 13).

Turns a verified skill gap into a concrete, evidence-producing project
assignment: problem statement, prerequisites, architecture, milestones with
acceptance criteria, tests, an evaluation rubric, a demo, a README outline, a
portfolio description, an effort estimate, and the exact evidence it produces.

Deterministic: the same skill + gap always yields the same assignment, so the
output is testable without a network or a model. (A local LLM could later
enrich the prose, but the structure is generated deterministically here.)
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

from artifact_engine.models import ArtifactAssignment, Milestone, SkillGap


def _aid(*parts: object) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:16]


def _as_float(value: object, default: float = 0.0) -> float:
    """Coerce an untyped value (from a plain dict) to float."""
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


def compute_gaps(
    skills: Iterable[dict[str, object]],
    target_confidence: float = 0.8,
    min_gap: float = 0.15,
) -> list[SkillGap]:
    """Compute skill gaps from a list of skill dicts (name + confidence).

    A gap exists when a skill's confidence is below ``target_confidence`` by at
    least ``min_gap``. Sorted by largest gap first (most valuable to close).
    """
    gaps: list[SkillGap] = []
    for s in skills:
        name = str(s.get("name", "")).strip()
        if not name:
            continue
        conf = _as_float(s.get("confidence", 0.0))
        gap = round(max(0.0, target_confidence - conf), 4)
        if gap >= min_gap:
            gaps.append(
                SkillGap(
                    skill=name,
                    current_confidence=round(conf, 4),
                    target_confidence=target_confidence,
                    gap=gap,
                    rationale=(
                        f"Current confidence {conf:.0%} is below the {target_confidence:.0%} "
                        f"target by {gap:.0%}; a shipped, tested artifact would raise the "
                        f"verification level with real evidence."
                    ),
                )
            )
    gaps.sort(key=lambda g: (-g.gap, g.skill))
    return gaps


def build_assignment(gap: SkillGap) -> ArtifactAssignment:
    """Build a full evidence-producing assignment for a single skill gap."""
    skill = gap.skill
    effort = 8 + int(gap.gap * 40)  # 8..48h scaled by gap size

    milestones = [
        Milestone(
            order=1,
            title=f"Scaffold a minimal {skill} project",
            outcome=f"A runnable repo skeleton exercising {skill} with CI-ready structure.",
            acceptance_criteria=[
                "Repo runs from a clean clone with documented commands.",
                "A smoke test passes.",
            ],
        ),
        Milestone(
            order=2,
            title=f"Implement the core {skill} capability",
            outcome=f"The central feature that demonstrates real {skill} competence.",
            acceptance_criteria=[
                "The feature works end-to-end on a realistic input.",
                "Unit tests cover the happy path and one edge case.",
            ],
        ),
        Milestone(
            order=3,
            title="Benchmark against a baseline and document",
            outcome="A measured comparison plus a README that a stranger can follow.",
            acceptance_criteria=[
                "A baseline is defined and the artifact is compared to it with numbers.",
                "README explains what, why, and how to reproduce.",
            ],
        ),
    ]

    return ArtifactAssignment(
        assignment_id=_aid(skill, gap.gap),
        target_skill=skill,
        problem_statement=(
            f"Design and ship a small but real project that proves {skill} through working "
            f"code, tests, and a measured result — not a tutorial follow-along. The project "
            f"must produce evidence an employer can inspect."
        ),
        prerequisites=["Working Python environment", f"Basic familiarity with {skill}"],
        missing_competencies=[
            f"Depth in {skill} beyond surface usage",
            "Turning a capability into a tested, documented artifact",
        ],
        architecture=(
            f"A single-purpose module implementing the {skill} capability, a thin CLI or API "
            f"entry point, a tests/ suite, and a benchmark script comparing against a baseline."
        ),
        milestones=milestones,
        acceptance_criteria=[
            "Runs from a clean clone using documented commands.",
            "Tests pass; lint and type checks pass.",
            "A measured result vs. a baseline is recorded.",
            "README and a short portfolio blurb exist.",
        ],
        tests=[
            "Unit tests for the core capability (happy path + edge case).",
            "An integration test exercising the entry point end-to-end.",
            "A regression test capturing the benchmarked behaviour.",
        ],
        evaluation_rubric=[
            "Correctness: the capability actually works on realistic input.",
            "Evidence: tests + benchmark numbers are present and reproducible.",
            "Clarity: a stranger can run it from the README.",
            "Scope discipline: small, focused, no unrelated features.",
        ],
        demo=(
            "A 60-second demo: run the entry point on a sample input and show the benchmark "
            "result vs. the baseline."
        ),
        readme_outline=[
            "What it is and the problem it solves",
            "Quick start (clean-clone commands)",
            f"How it demonstrates {skill}",
            "Benchmark: method, baseline, results",
            "Tests and how to run them",
            "Limitations and future work",
        ],
        portfolio_description=(
            f"Shipped a tested, benchmarked {skill} project demonstrating real competence "
            f"with reproducible evidence."
        ),
        estimated_effort_hours=effort,
        expected_evidence=[
            "A public repo with passing tests",
            "Benchmark results vs. a baseline",
            "A README and portfolio blurb",
            f"Commits demonstrating {skill} in practice",
        ],
    )


def assignments_for_skills(
    skills: Iterable[dict[str, object]],
    target_confidence: float = 0.8,
    min_gap: float = 0.15,
    limit: int = 5,
) -> list[ArtifactAssignment]:
    """Compute gaps from ``skills`` and build assignments for the top ``limit``."""
    gaps = compute_gaps(skills, target_confidence=target_confidence, min_gap=min_gap)
    return [build_assignment(g) for g in gaps[: max(0, limit)]]
