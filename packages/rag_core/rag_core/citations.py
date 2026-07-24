"""Citation building for the RAG subsystem.

Citations are **mandatory** (``docs/RAG_CONTRACT.md`` § *Guiding principles*):
every retrieved chunk carries exact provenance, and every claim in an answer
cites the chunks that support it.

This module:

* :func:`build_citations` — assigns sequential markers ``[1]``, ``[2]``, … to a
  ranked list of :class:`~rag_core.models.RetrievedChunk`, derives a short
  supporting snippet from each chunk's text (trimmed to ~240 chars around the
  most query-relevant line when a query is given), and carries full provenance
  (``source_type``, ``canonical_url``, ``path``, ``symbol``, line range,
  ``version``) into the :class:`~rag_core.models.Citation`.
* :func:`attach_citation_markers` — attaches citation markers to a list of
  :class:`~rag_core.models.Claim` by matching each claim's text span against the
  cited chunks (lexical overlap + explicit chunk-id references), so downstream
  answers are grounded in specific evidence.
"""

from __future__ import annotations

import logging
import re

from rag_core.models import Citation, Claim, RetrievedChunk

logger = logging.getLogger("rag_core.citations")

#: Target maximum length of a citation snippet (characters).
SNIPPET_MAX_CHARS: int = 240
#: Minimum lexical overlap for a claim→chunk match in :func:`attach_citation_markers`.
DEFAULT_MATCH_THRESHOLD: float = 0.12

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


def _tokens(text: str) -> list[str]:
    """Return lower-cased alphanumeric/underscore tokens in ``text``."""
    return [match.lower() for match in _TOKEN_RE.findall(text)]


def _token_set(text: str) -> set[str]:
    return set(_tokens(text))


def _split_lines(text: str) -> list[str]:
    """Split ``text`` into non-empty stripped lines (order preserved)."""
    return [line.strip() for line in text.splitlines() if line.strip()]


def _best_window(text: str, query: str | None, max_chars: int) -> str:
    """Return a short passage from ``text``, focused on the query if given.

    When ``query`` is provided, the line with the greatest token overlap with
    the query is chosen as an anchor and the window is expanded around it
    (preferring following lines) up to ``max_chars``. Without a query, the
    leading ``max_chars`` are returned. The result is single-spaced and
    ellipsised when it does not start/end at a text boundary.
    """
    normalized = text.strip()
    if not normalized:
        return ""
    if len(normalized) <= max_chars and query is None:
        return normalized

    lines = _split_lines(normalized)
    if not lines:
        return normalized[:max_chars].rstrip()

    anchor = 0
    truncated_head = False
    if query:
        query_tokens = _token_set(query)
        if query_tokens:
            best_overlap = -1
            for index, line in enumerate(lines):
                overlap = len(_token_set(line) & query_tokens)
                if overlap > best_overlap:
                    best_overlap = overlap
                    anchor = index
            truncated_head = anchor > 0

    # Grow a window around the anchor line, preferring following context.
    selected = [lines[anchor]]
    length = len(lines[anchor])
    lo, hi = anchor, anchor
    while length < max_chars and (hi + 1 < len(lines) or lo - 1 >= 0):
        grew = False
        if hi + 1 < len(lines):
            candidate = lines[hi + 1]
            if length + 1 + len(candidate) <= max_chars:
                selected.append(candidate)
                length += 1 + len(candidate)
                hi += 1
                grew = True
        if lo - 1 >= 0 and length < max_chars:
            candidate = lines[lo - 1]
            if length + 1 + len(candidate) <= max_chars:
                selected.insert(0, candidate)
                length += 1 + len(candidate)
                lo -= 1
                grew = True
        if not grew:
            break

    truncated_head = truncated_head or lo > 0
    truncated_tail = hi < len(lines) - 1

    snippet = " ".join(selected)
    if len(snippet) > max_chars:
        snippet = snippet[:max_chars].rstrip()
        truncated_tail = True
    if truncated_head:
        snippet = "… " + snippet
    if truncated_tail:
        snippet = snippet + " …"
    return snippet


def derive_snippet(
    chunk_text: str, query: str | None = None, max_chars: int = SNIPPET_MAX_CHARS
) -> str:
    """Derive a short supporting snippet from ``chunk_text``.

    Trims to roughly ``max_chars`` characters, centred on the most
    query-relevant line when ``query`` is provided. See :func:`_best_window`.
    """
    return _best_window(chunk_text, query, max_chars)


def build_citations(
    retrieved: list[RetrievedChunk],
    query: str | None = None,
    *,
    max_snippet_chars: int = SNIPPET_MAX_CHARS,
) -> list[Citation]:
    """Build ordered :class:`Citation` objects from ranked ``retrieved`` chunks.

    Markers ``[1]``, ``[2]``, … are assigned in the given (final-rank) order.
    Each citation carries the chunk's provenance and a short supporting snippet
    derived from its text (focused on ``query`` when provided). ``retrieved`` is
    consumed in order and is **not** re-sorted here — the caller controls rank.
    """
    citations: list[Citation] = []
    for index, item in enumerate(retrieved, start=1):
        chunk = item.chunk
        snippet = derive_snippet(chunk.text, query, max_snippet_chars)
        citations.append(
            Citation(
                marker=f"[{index}]",
                chunk_id=chunk.id,
                source_type=chunk.source_type,
                canonical_url=chunk.canonical_url,
                path=chunk.path,
                symbol=chunk.symbol,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                version=chunk.version,
                snippet=snippet,
            )
        )
    return citations


def _relevance(claim_text: str, citation: Citation) -> float:
    """Jaccard-style overlap between a claim and a citation's snippet/symbol."""
    claim_tokens = _token_set(claim_text)
    if not claim_tokens:
        return 0.0
    cite_tokens = _token_set(citation.snippet)
    if citation.symbol:
        cite_tokens |= _token_set(citation.symbol)
    if citation.path:
        cite_tokens |= _token_set(citation.path)
    if not cite_tokens:
        return 0.0
    intersection = len(claim_tokens & cite_tokens)
    if intersection == 0:
        return 0.0
    union = len(claim_tokens | cite_tokens)
    return intersection / union if union else 0.0


def attach_citation_markers(
    claims: list[Claim],
    citations: list[Citation],
    *,
    match_threshold: float = DEFAULT_MATCH_THRESHOLD,
    max_markers_per_claim: int = 3,
) -> list[Claim]:
    """Attach citation markers to claims by matching text spans to chunks.

    For each claim, citations are ranked by lexical relevance to the claim text
    (overlap against the citation snippet plus symbol/path tokens). Citations
    whose ``chunk_id`` is referenced verbatim in the claim text always match.
    The top ``max_markers_per_claim`` matches above ``match_threshold`` are
    attached; if none clear the threshold, the single best-scoring citation is
    attached so no claim is left uncited. Any markers already present on the
    claim are preserved (de-duplicated).

    Returns a **new** list of :class:`Claim` (inputs are not mutated).
    """
    result: list[Claim] = []
    for claim in claims:
        scored: list[tuple[float, str]] = []
        for citation in citations:
            explicit = citation.chunk_id and citation.chunk_id in claim.text
            score = 1.0 if explicit else _relevance(claim.text, citation)
            if score > 0.0:
                scored.append((score, citation.marker))

        scored.sort(key=lambda item: (-item[0], item[1]))
        chosen = [marker for score, marker in scored if score >= match_threshold]
        if not chosen and scored:
            # Never leave a claim uncited: fall back to the single best match.
            chosen = [scored[0][1]]
        chosen = chosen[:max_markers_per_claim]

        # Preserve any pre-existing markers, de-duplicated, order-stable.
        markers: list[str] = []
        for marker in [*claim.citation_markers, *chosen]:
            if marker not in markers:
                markers.append(marker)

        result.append(Claim(text=claim.text, citation_markers=markers))
    return result


__all__ = [
    "DEFAULT_MATCH_THRESHOLD",
    "SNIPPET_MAX_CHARS",
    "attach_citation_markers",
    "build_citations",
    "derive_snippet",
]
