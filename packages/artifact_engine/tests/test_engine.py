"""Tests for the skill-to-artifact engine."""

from __future__ import annotations

from artifact_engine import assignments_for_skills, build_assignment, compute_gaps


def test_compute_gaps_flags_low_confidence_only() -> None:
    skills = [
        {"name": "Python", "confidence": 0.9},       # no gap
        {"name": "RAG systems", "confidence": 0.4},  # gap
        {"name": "Rust", "confidence": 0.2},         # bigger gap
    ]
    gaps = compute_gaps(skills, target_confidence=0.8, min_gap=0.15)
    names = [g.skill for g in gaps]
    assert "Python" not in names
    assert names == ["Rust", "RAG systems"]  # largest gap first
    assert all(0.0 <= g.gap <= 1.0 for g in gaps)


def test_assignment_is_complete_and_evidence_producing() -> None:
    (gap,) = compute_gaps([{"name": "RAG systems", "confidence": 0.4}])
    a = build_assignment(gap)
    assert a.target_skill == "RAG systems"
    assert a.problem_statement
    assert len(a.milestones) >= 3
    assert a.tests and a.evaluation_rubric and a.readme_outline
    assert a.expected_evidence, "an artifact must produce inspectable evidence"
    assert a.estimated_effort_hours > 0
    # milestones are ordered
    assert [m.order for m in a.milestones] == sorted(m.order for m in a.milestones)


def test_assignments_deterministic() -> None:
    skills = [{"name": "RAG systems", "confidence": 0.4}]
    a = assignments_for_skills(skills)
    b = assignments_for_skills(skills)
    assert [x.assignment_id for x in a] == [x.assignment_id for x in b]


def test_no_gap_no_assignment() -> None:
    assert assignments_for_skills([{"name": "Python", "confidence": 0.95}]) == []
