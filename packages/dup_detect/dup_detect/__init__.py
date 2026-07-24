"""Duplicate issue/PR detection (Phase 8).

Given a *query* (a proposed finding/issue with a title, body, and optional
error strings / symbols / stack traces) and a set of *candidate* issues/PRs,
rank the candidates by how likely each is a duplicate — combining:

* **Exact signals** (handbook §5.3): shared error messages, dotted symbols,
  identifiers, and stack-trace frames. High-precision.
* **Lexical overlap** (token Jaccard) over title+body.
* **Semantic similarity** (embedding cosine) when an embedder is provided;
  falls back to lexical-only when none is available.

Each result carries a confidence in [0,1], a duplicate class
(EXACT | NEAR | WEAK | NONE), and a human-readable explanation of *why*.
Deterministic given a fixed embedder (defaults to the hermetic hash embedder).
"""

from __future__ import annotations

from dup_detect.detector import DuplicateDetector, detect_duplicates
from dup_detect.models import Candidate, DuplicateMatch, DuplicateQuery, DuplicateReport

__all__ = [
    "Candidate",
    "DuplicateDetector",
    "DuplicateMatch",
    "DuplicateQuery",
    "DuplicateReport",
    "detect_duplicates",
]
