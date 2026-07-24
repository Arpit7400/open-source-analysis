"""Duplicate detection logic.

Combines three signals into a confidence score per candidate:

1. **Exact signals** — shared error strings, dotted symbols, identifiers, and
   stack-trace frames between the query and a candidate. These are the
   strongest evidence that two reports describe the same problem.
2. **Lexical overlap** — token-set Jaccard over title+body (fast, deterministic).
3. **Semantic similarity** — cosine similarity of embeddings when an embedder is
   supplied; skipped (weight redistributed) when none is available.

The three are fused with fixed weights and mapped to a duplicate class:
EXACT / NEAR / WEAK / NONE. Everything is deterministic given a fixed embedder,
so results are reproducible and testable without a network or a model.
"""

from __future__ import annotations

import math
import re
from typing import Protocol

from dup_detect.models import (
    Candidate,
    DuplicateMatch,
    DuplicateQuery,
    DuplicateReport,
)

# Fusion weights (sum to 1.0 when an embedder is present). When no embedder is
# available the semantic weight is redistributed proportionally to the other two.
_W_EXACT = 0.5
_W_LEXICAL = 0.2
_W_SEMANTIC = 0.3

# Confidence -> class thresholds.
_T_EXACT = 0.72
_T_NEAR = 0.5
_T_WEAK = 0.3

_TOKEN_RE = re.compile(r"[A-Za-z0-9_.]+")
_DOTTED_RE = re.compile(r"\b[A-Za-z_]\w*(?:\.\w+)+\b")
_STOPWORDS = frozenset(
    {
        "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with",
        "is", "it", "this", "that", "when", "was", "not", "but", "as", "at",
        "by", "be", "are", "from", "if", "so", "we", "i", "you", "error",
        "issue", "bug", "fix",
    }
)


class _Embedder(Protocol):
    """Minimal embedder interface (matches rag_core.embeddings.Embedder)."""

    name: str

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


def _tokens(text: str) -> set[str]:
    return {
        t.lower()
        for t in _TOKEN_RE.findall(text)
        if len(t) > 1 and t.lower() not in _STOPWORDS
    }


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    # cosine is in [-1,1]; clamp to [0,1] for a similarity score.
    return max(0.0, dot / (na * nb))


def _query_signals(q: DuplicateQuery) -> set[str]:
    """Collect the exact signals from a query (errors, symbols, stack frames)."""
    sig: set[str] = set()
    for s in q.error_strings:
        sig.add(s.strip().lower())
    for s in q.symbols:
        sig.add(s.strip().lower())
    for s in q.stack_frames:
        sig.add(s.strip().lower())
    # dotted symbols mentioned in the body (e.g. requests.adapters.HTTPAdapter)
    for m in _DOTTED_RE.findall(q.text()):
        sig.add(m.lower())
    return {s for s in sig if s}


def _candidate_haystack(c: Candidate) -> str:
    return c.text().lower()


def _exact_overlap(signals: set[str], haystack: str) -> tuple[float, list[str]]:
    """Fraction of query signals present verbatim in the candidate text."""
    if not signals:
        return 0.0, []
    hits = sorted(s for s in signals if s and s in haystack)
    return len(hits) / len(signals), hits


def _classify(confidence: float) -> str:
    if confidence >= _T_EXACT:
        return "EXACT"
    if confidence >= _T_NEAR:
        return "NEAR"
    if confidence >= _T_WEAK:
        return "WEAK"
    return "NONE"


def _explain(exact: float, lexical: float, semantic: float, shared: list[str], dup: str) -> str:
    bits: list[str] = []
    if shared:
        preview = ", ".join(shared[:3])
        bits.append(f"shares exact signal(s): {preview}")
    if lexical >= 0.2:
        bits.append(f"lexical overlap {lexical:.0%}")
    if semantic >= 0.5:
        bits.append(f"semantically similar ({semantic:.0%})")
    if not bits:
        bits.append("little overlap on any signal")
    verdict = {
        "EXACT": "Very likely a duplicate",
        "NEAR": "Probable duplicate — review before filing",
        "WEAK": "Weakly related; probably not a duplicate",
        "NONE": "Not a duplicate",
    }[dup]
    return f"{verdict}: " + "; ".join(bits) + "."


class DuplicateDetector:
    """Score candidate issues/PRs against a query for duplication."""

    def __init__(self, embedder: _Embedder | None = None) -> None:
        self._embedder = embedder

    async def detect(
        self, query: DuplicateQuery, candidates: list[Candidate], top_k: int = 10
    ) -> DuplicateReport:
        signals = _query_signals(query)
        q_tokens = _tokens(query.text())

        # Semantic vectors (optional, one batched call).
        used_embedder = "none"
        q_vec: list[float] | None = None
        cand_vecs: list[list[float] | None] = [None] * len(candidates)
        have_semantic = self._embedder is not None and bool(query.text().strip())
        if have_semantic:
            assert self._embedder is not None
            used_embedder = getattr(self._embedder, "name", "embedder")
            texts = [query.text()] + [c.text() for c in candidates]
            vectors = await self._embedder.embed(texts)
            if vectors and len(vectors) == len(texts):
                q_vec = vectors[0]
                cand_vecs = list(vectors[1:])
            else:
                have_semantic = False

        # Weight scheme: redistribute semantic weight when no embedder.
        if have_semantic:
            w_exact, w_lex, w_sem = _W_EXACT, _W_LEXICAL, _W_SEMANTIC
        else:
            total = _W_EXACT + _W_LEXICAL
            w_exact, w_lex, w_sem = _W_EXACT / total, _W_LEXICAL / total, 0.0

        matches: list[DuplicateMatch] = []
        for i, cand in enumerate(candidates):
            haystack = _candidate_haystack(cand)
            exact_score, shared = _exact_overlap(signals, haystack)
            lexical_score = _jaccard(q_tokens, _tokens(cand.text()))
            cand_vec = cand_vecs[i]
            if have_semantic and q_vec is not None and cand_vec is not None:
                semantic_score = _cosine(q_vec, cand_vec)
            else:
                semantic_score = 0.0
            confidence = round(
                w_exact * exact_score + w_lex * lexical_score + w_sem * semantic_score, 4
            )
            dup = _classify(confidence)
            matches.append(
                DuplicateMatch(
                    candidate_id=cand.id,
                    number=cand.number,
                    url=cand.url,
                    title=cand.title,
                    dup_class=dup,
                    confidence=confidence,
                    exact_score=round(exact_score, 4),
                    lexical_score=round(lexical_score, 4),
                    semantic_score=round(semantic_score, 4),
                    shared_signals=shared,
                    explanation=_explain(exact_score, lexical_score, semantic_score, shared, dup),
                )
            )

        # Rank best-first; deterministic tie-break on candidate_id.
        matches.sort(key=lambda m: (-m.confidence, m.candidate_id))
        return DuplicateReport(
            query_title=query.title,
            matches=matches[: max(0, top_k)],
            used_embedder=used_embedder,
        )


async def detect_duplicates(
    query: DuplicateQuery,
    candidates: list[Candidate],
    embedder: _Embedder | None = None,
    top_k: int = 10,
) -> DuplicateReport:
    """Convenience wrapper: build a detector and run it once."""
    return await DuplicateDetector(embedder).detect(query, candidates, top_k=top_k)
