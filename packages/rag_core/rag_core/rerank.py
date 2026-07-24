"""Rerankers for the RAG subsystem.

The reranker is the fourth stage of the retrieval pipeline
(``docs/RAG_CONTRACT.md`` § *Retrieval pipeline*): after dense + sparse
retrieval and reciprocal-rank fusion, candidate chunks are re-scored against
the query and re-ordered.

Two implementations, both swappable via config:

* :class:`LexicalReranker` — the deterministic, network-free default used when
  no rerank model is configured. Scores a chunk by query/chunk token overlap
  (a Jaccard-style measure) plus boosts for symbol and path matches, so a query
  naming a function or file surfaces the chunk defining it.
* :class:`OllamaReranker` — optional LLM reranker, active only when
  ``CAREERFORGE_RAG_RERANK_MODEL`` is set. It asks the configured Ollama model
  to score query/chunk relevance in ``[0, 1]``. It is guarded: any network
  error or malformed response degrades (logged, never silent) to the lexical
  score for that chunk, so it can never harden a hard dependency on Ollama.

:func:`get_reranker` returns the configured reranker and logs the choice.
"""

from __future__ import annotations

import logging
import re
from typing import Protocol, runtime_checkable

import httpx

from rag_core.config import RagSettings, get_rag_settings
from rag_core.models import Chunk

logger = logging.getLogger("rag_core.rerank")

# Weights for the lexical relevance score. Overlap is the base signal; symbol
# and path matches are strong code-search signals worth an additive boost.
_OVERLAP_WEIGHT: float = 1.0
_SYMBOL_BOOST: float = 0.35
_PATH_BOOST: float = 0.25

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")
# Path-like fragments in a query: contain a slash or a dotted file extension.
_PATH_LIKE_RE = re.compile(r"[A-Za-z0-9_./\\-]*[/\\][A-Za-z0-9_./\\-]+|[A-Za-z0-9_-]+\.[A-Za-z0-9]+")


@runtime_checkable
class Reranker(Protocol):
    """Re-scores candidate chunks against a query.

    Contract signature (``docs/RAG_CONTRACT.md`` § *Protocols*): returns one
    score per input chunk, in the same order. Higher means more relevant.
    """

    async def rerank(self, query: str, chunks: list[Chunk]) -> list[float]:
        """Return one relevance score per chunk, aligned to ``chunks`` order."""
        ...


def _tokens(text: str) -> set[str]:
    """Return the set of lower-cased alphanumeric/underscore tokens in ``text``."""
    return {match.lower() for match in _TOKEN_RE.findall(text)}


class LexicalReranker:
    """Deterministic lexical reranker (the no-model fallback).

    Scores each chunk by:

    * **token overlap** — ``|query ∩ chunk| / |query ∪ chunk|`` (Jaccard-style,
      symmetric and bounded in ``[0, 1]``), weighted by :data:`_OVERLAP_WEIGHT`;
    * **symbol boost** — added when the chunk's ``symbol`` (or its component
      identifiers) appears among the query tokens;
    * **path boost** — added when a path-like fragment of the query matches the
      chunk's ``path``.

    The result is clamped to ``[0, 1]``. Fully deterministic and network-free.
    """

    name: str = "lexical"

    def _symbol_match(self, chunk: Chunk, query_tokens: set[str]) -> bool:
        if not chunk.symbol:
            return False
        symbol_tokens = _tokens(chunk.symbol)
        return bool(symbol_tokens & query_tokens)

    def _path_match(self, chunk: Chunk, query: str, query_tokens: set[str]) -> bool:
        if not chunk.path:
            return False
        path_lower = chunk.path.lower()
        # Direct substring match of any path-like fragment in the query.
        for fragment in _PATH_LIKE_RE.findall(query.lower()):
            fragment = fragment.strip()
            if fragment and fragment in path_lower:
                return True
        # Fall back to component-token overlap (e.g. query mentions "config").
        path_tokens = _tokens(chunk.path)
        return bool(path_tokens & query_tokens)

    def _score_one(self, query: str, query_tokens: set[str], chunk: Chunk) -> float:
        chunk_tokens = _tokens(chunk.text)
        if query_tokens and chunk_tokens:
            intersection = len(query_tokens & chunk_tokens)
            union = len(query_tokens | chunk_tokens)
            overlap = intersection / union if union else 0.0
        else:
            overlap = 0.0

        score = _OVERLAP_WEIGHT * overlap
        if self._symbol_match(chunk, query_tokens):
            score += _SYMBOL_BOOST
        if self._path_match(chunk, query, query_tokens):
            score += _PATH_BOOST
        return max(0.0, min(1.0, score))

    async def rerank(self, query: str, chunks: list[Chunk]) -> list[float]:
        """Return deterministic lexical relevance scores for ``chunks``."""
        query_tokens = _tokens(query)
        return [self._score_one(query, query_tokens, chunk) for chunk in chunks]


class OllamaReranker:
    """Optional LLM reranker backed by a local Ollama chat model.

    Prompts the configured model to rate query/chunk relevance in ``[0, 1]``.
    Every call is guarded: if the server is unreachable or a response cannot be
    parsed as a number, that chunk degrades to the :class:`LexicalReranker`
    score (the degradation is logged, never silent), so this reranker never
    becomes a hard dependency on Ollama.
    """

    def __init__(
        self,
        model: str,
        base_url: str,
        *,
        timeout: float = 30.0,
        fallback: LexicalReranker | None = None,
    ) -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._fallback = fallback or LexicalReranker()
        self.name: str = f"ollama:{model}"

    @property
    def model(self) -> str:
        """The Ollama model used for relevance scoring."""
        return self._model

    @staticmethod
    def _prompt(query: str, chunk: Chunk) -> str:
        """Build a compact, low-variance relevance-scoring prompt."""
        header_parts = [chunk.source_type or "CONTENT"]
        if chunk.path:
            header_parts.append(chunk.path)
        if chunk.symbol:
            header_parts.append(chunk.symbol)
        header = " | ".join(header_parts)
        # Cap passage length to keep the prompt small and the scoring fast.
        passage = chunk.text[:1200]
        return (
            "You are a strict retrieval relevance judge. Given a user QUERY and a "
            "candidate PASSAGE, output ONLY a single number between 0 and 1 "
            "(with up to two decimals) for how well the passage helps answer the "
            "query. 1 = directly answers; 0 = irrelevant. No words, no "
            "explanation.\n\n"
            f"QUERY:\n{query}\n\n"
            f"PASSAGE ({header}):\n{passage}\n\n"
            "SCORE:"
        )

    _NUMBER_RE = re.compile(r"[-+]?\d*\.?\d+")

    @classmethod
    def _parse_score(cls, raw: str) -> float | None:
        """Parse the first number in ``raw`` and clamp it to ``[0, 1]``."""
        match = cls._NUMBER_RE.search(raw)
        if match is None:
            return None
        try:
            value = float(match.group())
        except ValueError:
            return None
        return max(0.0, min(1.0, value))

    async def _score_one(
        self, client: httpx.AsyncClient, query: str, chunk: Chunk
    ) -> float | None:
        """Return the model's score for one chunk, or ``None`` to fall back."""
        payload = {
            "model": self._model,
            "prompt": self._prompt(query, chunk),
            "stream": False,
            "options": {"temperature": 0.0},
        }
        try:
            resp = await client.post(
                f"{self._base_url}/api/generate",
                json=payload,
                timeout=self._timeout,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning(
                "OllamaReranker request failed (%s); degrading to lexical: %s",
                self.name,
                exc,
            )
            return None
        data = resp.json()
        response_text = data.get("response")
        if not isinstance(response_text, str):
            logger.warning(
                "OllamaReranker got no 'response' field (%s); degrading to lexical.",
                self.name,
            )
            return None
        score = self._parse_score(response_text)
        if score is None:
            logger.warning(
                "OllamaReranker could not parse score from %r (%s); degrading to lexical.",
                response_text[:80],
                self.name,
            )
        return score

    async def rerank(self, query: str, chunks: list[Chunk]) -> list[float]:
        """Return per-chunk relevance scores, falling back per-chunk on failure."""
        if not chunks:
            return []
        fallback_scores = await self._fallback.rerank(query, chunks)
        scores: list[float] = list(fallback_scores)
        try:
            async with httpx.AsyncClient() as client:
                for index, chunk in enumerate(chunks):
                    model_score = await self._score_one(client, query, chunk)
                    if model_score is not None:
                        scores[index] = model_score
        except httpx.HTTPError as exc:
            # Whole-client failure: keep the already-computed lexical scores.
            logger.warning(
                "OllamaReranker client error (%s); using lexical scores: %s",
                self.name,
                exc,
            )
        return scores


def _probe_ollama(settings: RagSettings) -> bool:
    """Return ``True`` if the Ollama server answers within the probe timeout."""
    base = settings.ollama_url.rstrip("/")
    try:
        resp = httpx.get(f"{base}/api/tags", timeout=settings.probe_timeout_seconds)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.info("Ollama not reachable at %s (%s) for reranking.", base, exc)
        return False
    return True


def get_reranker(settings: RagSettings | None = None) -> Reranker:
    """Return the configured reranker, logging the choice.

    * If ``rag_rerank_model`` is empty (the default) → :class:`LexicalReranker`.
    * Otherwise, probe Ollama: reachable → :class:`OllamaReranker` (which still
      degrades per-chunk to lexical on transient failures); unreachable → log
      the degradation and return :class:`LexicalReranker`.
    """
    settings = settings or get_rag_settings()
    model = settings.rag_rerank_model.strip()
    if not model:
        logger.info("No rag_rerank_model configured; using LexicalReranker.")
        return LexicalReranker()
    if _probe_ollama(settings):
        logger.info(
            "Using OllamaReranker model=%s at %s.", model, settings.ollama_url
        )
        return OllamaReranker(
            model=model,
            base_url=settings.ollama_url,
            timeout=settings.http_timeout_seconds,
        )
    logger.warning(
        "rag_rerank_model=%r set but Ollama unreachable; falling back to LexicalReranker.",
        model,
    )
    return LexicalReranker()


__all__ = [
    "LexicalReranker",
    "OllamaReranker",
    "Reranker",
    "get_reranker",
]
