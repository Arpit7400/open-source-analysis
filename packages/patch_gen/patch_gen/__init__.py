"""Candidate patch generation (Phase 9).

Deterministic template-based patch candidates from static findings, optionally
enriched by a local LLM when one is reachable. Always includes a NO_SUBMISSION
critic candidate. Diffs are computed from real source with :mod:`difflib`, never
hallucinated.
"""

from __future__ import annotations

from patch_gen.generator import PatchGenerator, is_python_file, parses
from patch_gen.llm import LocalLLM, probe
from patch_gen.models import Candidate, CandidateSet, DiffLine, VerificationCheck

__all__ = [
    "Candidate",
    "CandidateSet",
    "DiffLine",
    "LocalLLM",
    "PatchGenerator",
    "VerificationCheck",
    "is_python_file",
    "parses",
    "probe",
]
