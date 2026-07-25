"""Typed models for the artifact engine + opportunity miner (Phase 13)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SkillGap(BaseModel):
    """A verified gap between a target skill and current evidence."""

    skill: str
    current_confidence: float = Field(ge=0.0, le=1.0)
    target_confidence: float = Field(ge=0.0, le=1.0)
    gap: float = Field(ge=0.0, le=1.0)
    rationale: str = ""


class Milestone(BaseModel):
    """One buildable milestone of an artifact assignment."""

    order: int
    title: str
    outcome: str
    acceptance_criteria: list[str] = Field(default_factory=list)


class ArtifactAssignment(BaseModel):
    """An evidence-producing project assignment derived from a skill gap.

    Prefers building/testing/documenting/contributing over passive study
    (handbook Skill-to-Artifact Engine).
    """

    assignment_id: str
    target_skill: str
    problem_statement: str
    prerequisites: list[str] = Field(default_factory=list)
    missing_competencies: list[str] = Field(default_factory=list)
    architecture: str = ""
    milestones: list[Milestone] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    tests: list[str] = Field(default_factory=list)
    evaluation_rubric: list[str] = Field(default_factory=list)
    demo: str = ""
    readme_outline: list[str] = Field(default_factory=list)
    portfolio_description: str = ""
    estimated_effort_hours: int = 0
    expected_evidence: list[str] = Field(default_factory=list)


class RepoSignal(BaseModel):
    """Maintainability / activity signals for a candidate repository."""

    full_name: str
    language: str | None = None
    stars: int = 0
    open_issues: int = 0
    has_tests: bool = False
    has_contributing_guide: bool = False
    archived: bool = False
    recent_activity: bool = True


class Opportunity(BaseModel):
    """A ranked contribution opportunity."""

    repo: str
    url: str | None = None
    contribution_type: str  # DOCS | TEST | BUGFIX | TYPING | REFACTOR | FEATURE
    fit_score: float = Field(ge=0.0, le=1.0)
    maintainability_score: float = Field(ge=0.0, le=1.0)
    rank_score: float = Field(ge=0.0, le=1.0)
    matched_skills: list[str] = Field(default_factory=list)
    rationale: str = ""


class OpportunityReport(BaseModel):
    """Ranked opportunities for a user's evidence profile."""

    opportunities: list[Opportunity] = Field(default_factory=list)
