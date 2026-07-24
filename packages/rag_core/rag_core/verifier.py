"""Claim-evidence verification.

The last deterministic gate of the RAG pipeline (``docs/RAG_CONTRACT.md``
§ *Retrieval pipeline*): given a generated claim and the candidate chunks that
supposedly support it, decide whether the evidence actually backs the claim.

Two strategies, in priority order:

1. **LLM judgment (optional).** When an Ollama LLM is configured
   (``rag_llm_model`` non-empty) and reachable, a low-temperature yes/no+why
   prompt over the cited context yields a support decision. Any failure
   (network, malformed output, timeout) degrades — logged, never silent — to
   the extractive baseline.
2. **Extractive baseline (always available).** Deterministic lexical/semantic
   overlap of claim tokens against the cited chunk text. The support score is
   the fraction of *content* claim tokens found in the evidence; a claim is
   ``supported`` only when that ratio meets :attr:`ClaimVerifier.threshold`.

Both paths return a :class:`rag_core.models.ClaimVerdict` and always populate
``cited_chunk_ids`` with the chunks the verdict was computed against. A claim
whose overlap is below threshold is **rejected** (``supported=False``).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable
from typing import TYPE_CHECKING

import httpx

from rag_core.config import RagSettings, get_rag_settings
from rag_core.models import Chunk, ClaimVerdict

if TYPE_CHECKING:  # pragma: no cover - typing only
    from rag_core.models import RetrievedChunk

logger = logging.getLogger("rag_core.verifier")

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")

# Very common English function words carry no evidentiary weight, so they are
# excluded from the overlap ratio (otherwise every claim "matches" trivially).
_STOPWORDS: frozenset[str] = frozenset(
    {
        "a", "an", "the", "and", "or", "but", "if", "then", "else", "of", "to",
        "in", "on", "at", "by", "for", "with", "as", "is", "are", "was", "were",
        "be", "been", "being", "it", "its", "this", "that", "these", "those",
        "from", "into", "over", "under", "than", "so", "such", "not", "no",
        "can", "could", "should", "would", "may", "might", "must", "will",
        "shall", "do", "does", "did", "done", "has", "have", "had", "which",
        "who", "whom", "whose", "what", "when", "where", "why", "how", "all",
        "any", "both", "each", "few", "more", "most", "other", "some", "s",
        "t", "you", "your", "we", "our", "they", "their", "he", "she", "his",
        "her", "them", "us", "i", "me", "my", "also", "there", "here", "up",
    }
)

#: Default overlap ratio above which a claim is considered supported.
DEFAULT_THRESHOLD: float = 0.5


def _content_tokens(text: str) -> list[str]:
    """Lower-cased, stopword-filtered alphanumeric tokens (deterministic)."""
    return [
        token
        for token in (t.lower() for t in _TOKEN_RE.findall(text))
        if token not in _STOPWORDS
    ]


class ClaimVerifier:
    """Verify that cited evidence supports a generated claim.

    Parameters
    ----------
    settings:
        :class:`rag_core.config.RagSettings`; ``rag_llm_model`` and
        ``ollama_url`` decide whether LLM judgment is attempted.
    llm:
        Optional flag/override. ``True`` forces attempting the LLM (still falls
        back on failure), ``False`` forces the extractive baseline, ``None``
        (default) attempts the LLM iff ``rag_llm_model`` is set.
    threshold:
        Minimum overlap ratio for ``supported=True`` in the extractive baseline
        (default :data:`DEFAULT_THRESHOLD`).
    """

    def __init__(
        self,
        settings: RagSettings | None = None,
        llm: bool | None = None,
        *,
        threshold: float = DEFAULT_THRESHOLD,
    ) -> None:
        self._settings = settings or get_rag_settings()
        self.threshold = threshold
        model = (self._settings.rag_llm_model or "").strip()
        if llm is None:
            self._use_llm = bool(model)
        else:
            self._use_llm = bool(llm) and bool(model)
        self._model = model

    # -- public API ----------------------------------------------------------

    async def verify(
        self,
        claim: str,
        chunks: Iterable[Chunk | RetrievedChunk],
    ) -> ClaimVerdict:
        """Return a :class:`ClaimVerdict` for ``claim`` given ``chunks``.

        Attempts the LLM judgment when enabled and reachable; on any failure or
        when disabled, uses the deterministic extractive baseline. The returned
        verdict always lists the ``cited_chunk_ids`` it considered.
        """
        materialised = [self._as_chunk(c) for c in chunks]
        cited_ids = [c.id for c in materialised]

        if not materialised:
            return ClaimVerdict(
                claim=claim,
                supported=False,
                support_score=0.0,
                reason="No supporting chunks were cited for this claim.",
                cited_chunk_ids=[],
            )

        if self._use_llm:
            verdict = await self._verify_with_llm(claim, materialised, cited_ids)
            if verdict is not None:
                return verdict
            logger.info(
                "LLM verification unavailable/failed; using extractive baseline."
            )

        return self._verify_extractive(claim, materialised, cited_ids)

    # -- extractive baseline -------------------------------------------------

    def _verify_extractive(
        self,
        claim: str,
        chunks: list[Chunk],
        cited_ids: list[str],
    ) -> ClaimVerdict:
        """Deterministic lexical-overlap support judgment."""
        claim_tokens = _content_tokens(claim)
        if not claim_tokens:
            # A claim with no content tokens (e.g. pure punctuation) cannot be
            # substantiated; reject conservatively.
            return ClaimVerdict(
                claim=claim,
                supported=False,
                support_score=0.0,
                reason="Claim has no substantive content tokens to verify.",
                cited_chunk_ids=cited_ids,
            )

        evidence_tokens: set[str] = set()
        for chunk in chunks:
            evidence_tokens.update(_content_tokens(chunk.text))

        matched = [tok for tok in claim_tokens if tok in evidence_tokens]
        # Ratio over the *unique* content tokens of the claim so repeated words
        # don't inflate or deflate the score.
        unique_claim = set(claim_tokens)
        overlap = len(unique_claim & evidence_tokens) / len(unique_claim)
        supported = overlap >= self.threshold

        reason = (
            f"Extractive overlap {overlap:.2f} "
            f"({len(unique_claim & evidence_tokens)}/{len(unique_claim)} content "
            f"tokens found in cited evidence) "
            f"{'meets' if supported else 'is below'} threshold {self.threshold:.2f}."
        )
        logger.debug(
            "Extractive verdict: supported=%s score=%.3f matched=%r",
            supported,
            overlap,
            matched[:10],
        )
        return ClaimVerdict(
            claim=claim,
            supported=supported,
            support_score=round(overlap, 4),
            reason=reason,
            cited_chunk_ids=cited_ids,
        )

    # -- LLM judgment --------------------------------------------------------

    async def _verify_with_llm(
        self,
        claim: str,
        chunks: list[Chunk],
        cited_ids: list[str],
    ) -> ClaimVerdict | None:
        """Ask a low-temperature Ollama model whether the evidence supports it.

        Returns ``None`` on any failure so the caller falls back to extractive.
        The prompt asks for strict JSON so the output is parseable; a
        best-effort brace-extraction handles chatty models.
        """
        context = self._format_context(chunks)
        prompt = (
            "You are a strict fact-checking judge. Decide ONLY from the CONTEXT "
            "whether it directly supports the CLAIM. Do not use outside "
            "knowledge. If the context does not clearly support the claim, it is "
            "NOT supported.\n\n"
            f"CLAIM:\n{claim}\n\n"
            f"CONTEXT:\n{context}\n\n"
            "Respond with a single JSON object and nothing else, of the form:\n"
            '{"supported": true|false, "score": <float 0..1>, '
            '"reason": "<one sentence>"}'
        )
        payload = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.0},
        }
        base = self._settings.ollama_url.rstrip("/")
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{base}/api/generate",
                    json=payload,
                    timeout=self._settings.http_timeout_seconds,
                )
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.info("Ollama verify request failed (%s).", exc)
            return None

        text = data.get("response")
        if not isinstance(text, str) or not text.strip():
            logger.info("Ollama verify returned empty response.")
            return None

        parsed = self._parse_judgment(text)
        if parsed is None:
            logger.info("Could not parse LLM verify output: %r", text[:200])
            return None

        supported, score, reason = parsed
        return ClaimVerdict(
            claim=claim,
            supported=supported,
            support_score=round(max(0.0, min(1.0, score)), 4),
            reason=reason or ("LLM judged the claim supported." if supported else "LLM judged the claim unsupported."),
            cited_chunk_ids=cited_ids,
        )

    @staticmethod
    def _parse_judgment(text: str) -> tuple[bool, float, str] | None:
        """Extract ``(supported, score, reason)`` from a model's JSON reply."""
        candidate = text.strip()
        # Isolate the first {...} object if the model wrapped it in prose.
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = candidate[start : end + 1]
        try:
            obj = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            return None
        if not isinstance(obj, dict):
            return None
        supported = bool(obj.get("supported", False))
        raw_score = obj.get("score", 1.0 if supported else 0.0)
        try:
            score = float(raw_score)
        except (TypeError, ValueError):
            score = 1.0 if supported else 0.0
        reason = str(obj.get("reason", "")).strip()
        return supported, score, reason

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _format_context(chunks: list[Chunk]) -> str:
        """Render cited chunks as a compact, numbered evidence block."""
        blocks: list[str] = []
        for idx, chunk in enumerate(chunks, start=1):
            locus = chunk.path or chunk.canonical_url or chunk.source_id or "unknown"
            if chunk.symbol:
                locus = f"{locus}:{chunk.symbol}"
            snippet = chunk.text.strip()
            if len(snippet) > 1200:
                snippet = snippet[:1200] + " …"
            blocks.append(f"[{idx}] ({locus})\n{snippet}")
        return "\n\n".join(blocks)

    @staticmethod
    def _as_chunk(item: Chunk | RetrievedChunk) -> Chunk:
        """Accept either a bare :class:`Chunk` or a :class:`RetrievedChunk`."""
        if isinstance(item, Chunk):
            return item
        inner = getattr(item, "chunk", None)
        if isinstance(inner, Chunk):
            return inner
        raise TypeError(f"Expected Chunk or RetrievedChunk, got {type(item)!r}")


__all__ = ["DEFAULT_THRESHOLD", "ClaimVerifier"]
