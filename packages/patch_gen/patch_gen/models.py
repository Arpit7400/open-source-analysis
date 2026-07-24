"""Typed candidate-patch models (mirror ``careerforge_api.schemas``)."""

from __future__ import annotations

from pydantic import BaseModel, Field

VERDICTS = ("ACCEPTED", "REJECTED", "NO_SUBMISSION", "PENDING")
RISK_LEVELS = ("SAFE", "LOW", "MEDIUM", "HIGH", "BLOCKED")


class DiffLine(BaseModel):
    """One diff hunk (contract shape)."""

    path: str
    old: str = ""
    new: str = ""
    hunk: str = ""


class VerificationCheck(BaseModel):
    """A single verification check result (populated by Phase 10)."""

    check: str
    status: str = "SKIP"  # PASS | FAIL | SKIP
    detail: str = ""
    verifier_agent: str = ""


class Candidate(BaseModel):
    """A candidate patch (matches ``careerforge_api.schemas.Candidate``)."""

    candidate_id: str
    title: str
    author_agent: str
    verdict: str = "PENDING"
    root_cause: str = ""
    risk_level: str = "LOW"
    scope_files_changed: int = 0
    unrelated_changes: bool = False
    diff: list[DiffLine] = Field(default_factory=list)
    verification: list[VerificationCheck] = Field(default_factory=list)
    verification_summary: str = ""

    # --- extra (not in the API Candidate; useful for the workflow) ---
    finding_id: str | None = None
    test_snippet: str = ""
    verification_commands: list[str] = Field(default_factory=list)
    generated_by: str = "template"  # "template" | "ollama:<model>"


class CandidateSet(BaseModel):
    """The set of candidates generated for one finding/problem."""

    finding_id: str | None = None
    problem_summary: str = ""
    candidates: list[Candidate] = Field(default_factory=list)
    generated_by: str = "template"
