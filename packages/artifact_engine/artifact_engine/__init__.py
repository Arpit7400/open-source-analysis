"""Skill-to-artifact engine + contribution opportunity miner (Phase 13)."""

from __future__ import annotations

from artifact_engine.engine import (
    assignments_for_skills,
    build_assignment,
    compute_gaps,
)
from artifact_engine.miner import mine_opportunities
from artifact_engine.models import (
    ArtifactAssignment,
    Milestone,
    Opportunity,
    OpportunityReport,
    RepoSignal,
    SkillGap,
)

__all__ = [
    "ArtifactAssignment",
    "Milestone",
    "Opportunity",
    "OpportunityReport",
    "RepoSignal",
    "SkillGap",
    "assignments_for_skills",
    "build_assignment",
    "compute_gaps",
    "mine_opportunities",
]
