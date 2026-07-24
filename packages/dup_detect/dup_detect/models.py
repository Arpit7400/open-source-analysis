"""Typed models for duplicate detection."""

from __future__ import annotations

from pydantic import BaseModel, Field

# Duplicate classification bands (by combined confidence).
DUP_CLASSES = ("EXACT", "NEAR", "WEAK", "NONE")


class DuplicateQuery(BaseModel):
    """The thing we are checking for prior art (a proposed issue/finding)."""

    title: str = ""
    body: str = ""
    error_strings: list[str] = Field(default_factory=list)
    symbols: list[str] = Field(default_factory=list)
    stack_frames: list[str] = Field(default_factory=list)

    def text(self) -> str:
        return f"{self.title}\n{self.body}".strip()


class Candidate(BaseModel):
    """An existing issue/PR/discussion to compare against."""

    id: str
    number: int | None = None
    title: str = ""
    body: str = ""
    url: str | None = None
    state: str | None = None
    is_pull: bool = False

    def text(self) -> str:
        return f"{self.title}\n{self.body}".strip()


class DuplicateMatch(BaseModel):
    """One candidate scored against the query."""

    candidate_id: str
    number: int | None = None
    url: str | None = None
    title: str = ""
    dup_class: str = "NONE"
    confidence: float = Field(ge=0.0, le=1.0)
    exact_score: float = 0.0
    lexical_score: float = 0.0
    semantic_score: float = 0.0
    shared_signals: list[str] = Field(default_factory=list)
    explanation: str = ""


class DuplicateReport(BaseModel):
    """Ranked duplicate matches for a query."""

    query_title: str
    matches: list[DuplicateMatch] = Field(default_factory=list)
    used_embedder: str = "none"

    @property
    def best(self) -> DuplicateMatch | None:
        return self.matches[0] if self.matches else None

    @property
    def has_duplicate(self) -> bool:
        return any(m.dup_class in ("EXACT", "NEAR") for m in self.matches)
