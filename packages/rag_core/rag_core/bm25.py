"""In-memory Okapi BM25 sparse index for the RAG subsystem.

A deterministic, dependency-free (stdlib + :mod:`math`) sparse retriever that
complements the dense vector search in the hybrid pipeline
(``docs/RAG_CONTRACT.md`` § *Retrieval pipeline*). It is built over a list of
:class:`~rag_core.models.Chunk` and returns ranked ``(chunk_id, score)`` pairs.

Design notes:

* **Okapi BM25** with the standard defaults ``k1=1.5``, ``b=0.75``.
* **Deterministic** — identical corpora/queries always produce identical
  rankings; ties are broken by ``chunk_id`` so ordering is total and stable
  across platforms.
* **Code-aware tokenization** — text is lower-cased and split on
  non-alphanumeric characters while *also* preserving dotted names
  (``os.path.join``) and underscored identifiers (``get_settings``) as whole
  tokens *and* their components, so both ``os.path.join`` and ``join`` match.
* **Exact-match boosting** (handbook §5.3) — a helper detects "exact" tokens in
  a query (error strings, dotted identifiers, snake/camel identifiers, stack
  trace fragments) and boosts chunks that contain them verbatim, so a query
  quoting an exception message surfaces the chunk containing it.
"""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from dataclasses import dataclass, field

from rag_core.models import Chunk

logger = logging.getLogger("rag_core.bm25")

#: Okapi BM25 term-frequency saturation parameter (contract-fixed).
BM25_K1: float = 1.5
#: Okapi BM25 length-normalisation parameter (contract-fixed).
BM25_B: float = 0.75

#: Multiplier applied per exact-token hit during exact-match boosting (§5.3).
DEFAULT_EXACT_MATCH_BOOST: float = 2.0

# A "word" for tokenization: a run of letters/digits/underscores, optionally
# joined by single dots into a dotted name (e.g. ``os.path.join``).
_WORD_RE = re.compile(r"[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)*")

# Splitters used to break a compound identifier into its component sub-tokens.
_DOT_SPLIT_RE = re.compile(r"\.")
_UNDERSCORE_SPLIT_RE = re.compile(r"_+")
# camelCase / PascalCase boundary split (``getSettings`` -> ``get`` ``Settings``).
_CAMEL_SPLIT_RE = re.compile(
    r".+?(?:(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])|$)"
)

# Heuristic detector for tokens worth exact-matching in a query: dotted names,
# snake_case, camelCase/PascalCase, or anything containing a digit (versions,
# error codes). Plain lowercase dictionary words are excluded.
_EXACT_TOKEN_RE = re.compile(
    r"""
    (?:[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+)  # dotted.name
    | (?:[A-Za-z0-9]+_[A-Za-z0-9_]+)                          # snake_case
    | (?:[a-z0-9]+[A-Z][A-Za-z0-9]*)                          # camelCase
    | (?:[A-Z][a-z0-9]+[A-Z][A-Za-z0-9]*)                     # PascalCase
    | (?:[A-Za-z]*[0-9][A-Za-z0-9]*)                          # has a digit
    """,
    re.VERBOSE,
)


def _split_identifier(word: str) -> list[str]:
    """Return component sub-tokens of a compound identifier.

    ``os.path.join`` -> ``["os", "path", "join"]``;
    ``get_settings`` -> ``["get", "settings"]``;
    ``getSettings`` -> ``["get", "settings"]``. Components are lower-cased.
    """
    components: list[str] = []
    for dotted in _DOT_SPLIT_RE.split(word):
        if not dotted:
            continue
        for under in _UNDERSCORE_SPLIT_RE.split(dotted):
            if not under:
                continue
            for camel in _CAMEL_SPLIT_RE.findall(under):
                if camel:
                    components.append(camel.lower())
    return components


def tokenize(text: str) -> list[str]:
    """Tokenize ``text`` for BM25 (lower-cased, code-aware, deterministic).

    Each matched "word" contributes:

    * the whole lower-cased token (dotted names kept intact), and
    * its component sub-tokens (dot / underscore / camelCase split),

    so both a fully-qualified ``os.path.join`` query and a bare ``join`` query
    match a chunk mentioning ``os.path.join``. Duplicate emissions are intended:
    they weight compound identifiers slightly higher, which is desirable for
    code search.
    """
    tokens: list[str] = []
    for match in _WORD_RE.findall(text):
        lowered = match.lower()
        tokens.append(lowered)
        components = _split_identifier(match)
        # Only add components when they actually differ from the whole token
        # (avoids doubling a simple word like ``python``).
        if components != [lowered]:
            tokens.extend(components)
    return tokens


def extract_exact_tokens(query: str) -> list[str]:
    """Return distinct exact-match tokens detected in ``query`` (§5.3).

    Targets error strings, dotted identifiers, snake/camel identifiers, and
    version/error-code fragments — the kinds of tokens where a *verbatim* match
    is a strong relevance signal for code/stack-trace search. Plain natural
    words are excluded to avoid over-boosting. Order is preserved (first-seen),
    lower-cased for case-insensitive containment checks.
    """
    seen: set[str] = set()
    ordered: list[str] = []
    for match in _EXACT_TOKEN_RE.findall(query):
        lowered = match.lower()
        if lowered and lowered not in seen:
            seen.add(lowered)
            ordered.append(lowered)
    return ordered


@dataclass
class _Posting:
    """Per-document state kept by :class:`BM25Index`."""

    chunk: Chunk
    length: int
    term_freq: Counter[str] = field(default_factory=Counter)
    # Lower-cased raw text, cached once for exact-substring boosting.
    lowered_text: str = ""


class BM25Index:
    """Deterministic in-memory Okapi BM25 sparse index over :class:`Chunk`.

    Usage::

        idx = BM25Index()
        idx.add(chunks)
        for chunk_id, score in idx.search("os.path.join", limit=10):
            chunk = idx.get_chunk(chunk_id)

    The index is incremental (:meth:`add` may be called repeatedly) and
    idempotent per ``chunk_id`` — re-adding a chunk with the same id replaces
    the previous posting rather than double-counting it.
    """

    def __init__(
        self,
        *,
        k1: float = BM25_K1,
        b: float = BM25_B,
        exact_match_boost: float = DEFAULT_EXACT_MATCH_BOOST,
    ) -> None:
        if k1 < 0.0:
            raise ValueError(f"BM25 k1 must be non-negative, got {k1}")
        if not 0.0 <= b <= 1.0:
            raise ValueError(f"BM25 b must be in [0, 1], got {b}")
        self.k1 = k1
        self.b = b
        self.exact_match_boost = exact_match_boost
        self._postings: dict[str, _Posting] = {}
        self._doc_freq: Counter[str] = Counter()
        self._total_length: int = 0

    # -- construction -------------------------------------------------------

    def add(self, chunks: list[Chunk]) -> None:
        """Index ``chunks`` (replacing any existing posting with the same id)."""
        for chunk in chunks:
            if chunk.id in self._postings:
                self._remove(chunk.id)
            tokens = tokenize(chunk.text)
            term_freq: Counter[str] = Counter(tokens)
            posting = _Posting(
                chunk=chunk,
                length=len(tokens),
                term_freq=term_freq,
                lowered_text=chunk.text.lower(),
            )
            self._postings[chunk.id] = posting
            self._total_length += posting.length
            for term in term_freq:
                self._doc_freq[term] += 1

    def _remove(self, chunk_id: str) -> None:
        """Remove a previously-indexed chunk, keeping corpus stats consistent."""
        posting = self._postings.pop(chunk_id, None)
        if posting is None:
            return
        self._total_length -= posting.length
        for term in posting.term_freq:
            self._doc_freq[term] -= 1
            if self._doc_freq[term] <= 0:
                del self._doc_freq[term]

    # -- introspection ------------------------------------------------------

    def __len__(self) -> int:
        return len(self._postings)

    @property
    def size(self) -> int:
        """Number of indexed chunks."""
        return len(self._postings)

    @property
    def avg_doc_length(self) -> float:
        """Mean token length across the corpus (0.0 when empty)."""
        if not self._postings:
            return 0.0
        return self._total_length / len(self._postings)

    def get_chunk(self, chunk_id: str) -> Chunk | None:
        """Return the indexed :class:`Chunk` for ``chunk_id`` (or ``None``)."""
        posting = self._postings.get(chunk_id)
        return posting.chunk if posting is not None else None

    def chunks(self) -> list[Chunk]:
        """Return all indexed chunks (insertion order)."""
        return [posting.chunk for posting in self._postings.values()]

    # -- scoring ------------------------------------------------------------

    def _idf(self, term: str) -> float:
        """Okapi BM25 IDF with the standard ``+0.5`` smoothing (clamped ≥ 0)."""
        n_docs = len(self._postings)
        df = self._doc_freq.get(term, 0)
        # Standard BM25 idf; clamp at 0 so terms in >half the corpus don't go
        # negative and flip rankings.
        idf = math.log((n_docs - df + 0.5) / (df + 0.5) + 1.0)
        return max(0.0, idf)

    def _score_document(self, posting: _Posting, query_terms: Counter[str]) -> float:
        """BM25 score of one document against the (de-duplicated) query terms."""
        avgdl = self.avg_doc_length
        if avgdl <= 0.0:
            return 0.0
        score = 0.0
        for term in query_terms:
            tf = posting.term_freq.get(term, 0)
            if tf == 0:
                continue
            idf = self._idf(term)
            if idf <= 0.0:
                continue
            denom = tf + self.k1 * (
                1.0 - self.b + self.b * (posting.length / avgdl)
            )
            score += idf * (tf * (self.k1 + 1.0)) / denom
        return score

    def search(
        self,
        query: str,
        limit: int = 30,
        *,
        boost_exact: bool = True,
    ) -> list[tuple[str, float]]:
        """Return the top ``limit`` ``(chunk_id, score)`` pairs for ``query``.

        Ranked by BM25 score descending, with exact-match boosting applied when
        ``boost_exact`` is set (see :meth:`exact_match_scores`). Ties are broken
        deterministically by ``chunk_id`` so results are stable across runs and
        platforms. Chunks with a non-positive score are dropped.
        """
        if limit <= 0 or not self._postings:
            return []
        query_terms: Counter[str] = Counter(tokenize(query))
        if not query_terms:
            return []

        exact_scores = (
            self.exact_match_scores(query) if boost_exact else {}
        )

        scored: list[tuple[str, float]] = []
        for chunk_id, posting in self._postings.items():
            score = self._score_document(posting, query_terms)
            score += exact_scores.get(chunk_id, 0.0)
            if score > 0.0:
                scored.append((chunk_id, score))

        # Sort by score desc, then chunk_id asc for deterministic tie-breaking.
        scored.sort(key=lambda item: (-item[1], item[0]))
        return scored[:limit]

    # -- exact-match boosting (handbook §5.3) -------------------------------

    def exact_match_scores(self, query: str) -> dict[str, float]:
        """Return additive boost scores for chunks containing exact query tokens.

        Detects exact tokens (error strings, dotted/snake/camel identifiers,
        stack-trace fragments) via :func:`extract_exact_tokens` and, for each
        such token found *verbatim* in a chunk's (lower-cased) text, adds
        :attr:`exact_match_boost` scaled by that token's IDF (rarer tokens boost
        more). Chunks with no exact hit are absent from the result.
        """
        exact_tokens = extract_exact_tokens(query)
        if not exact_tokens:
            return {}
        boosts: dict[str, float] = {}
        for chunk_id, posting in self._postings.items():
            total = 0.0
            for token in exact_tokens:
                if token in posting.lowered_text:
                    # Weight by IDF so a rare exact identifier boosts more than a
                    # common one; floor at 1.0 so even common exact hits count.
                    idf = self._idf(token) or 1.0
                    total += self.exact_match_boost * max(1.0, idf)
            if total > 0.0:
                boosts[chunk_id] = total
        return boosts


__all__ = [
    "BM25_B",
    "BM25_K1",
    "DEFAULT_EXACT_MATCH_BOOST",
    "BM25Index",
    "extract_exact_tokens",
    "tokenize",
]
