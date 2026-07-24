"""Embedding providers for the RAG subsystem.

Defines the :class:`Embedder` protocol and two implementations:

* :class:`OllamaEmbedder` — calls a local Ollama server (default model
  ``nomic-embed-text``, 768-dim). Batched over an ``httpx.AsyncClient`` with a
  configurable timeout; raises/degrades cleanly when the server is unreachable.
* :class:`HashEmbedder` — a deterministic, network-free fallback used for
  hermetic tests and whenever Ollama is down. It hashes tokens into a
  fixed-dimension (768) L2-normalised vector.

:func:`get_embedder` probes Ollama and returns the real embedder, or logs the
degradation and falls back to :class:`HashEmbedder`. The ``name`` attribute is
reported verbatim in :attr:`RagAnswer.used_embedder`
(``"ollama:<model>"`` or ``"hash-fallback"``).
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
from typing import Protocol, runtime_checkable

import httpx

from rag_core.config import RagSettings, get_rag_settings

logger = logging.getLogger("rag_core.embeddings")

#: Dimension used by the fallback hash embedder and by ``nomic-embed-text``.
DEFAULT_DIM: int = 768

#: Value reported in ``used_embedder`` when the hash fallback is active.
HASH_FALLBACK_NAME: str = "hash-fallback"

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


@runtime_checkable
class Embedder(Protocol):
    """A text embedding provider.

    Implementations must be swappable via config and expose a stable
    :attr:`name` (surfaced in ``used_embedder``) and :attr:`dim`.
    """

    name: str
    dim: int

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text, in order."""
        ...


def _tokenize(text: str) -> list[str]:
    """Lower-cased alphanumeric/underscore tokens (deterministic, no network)."""
    return _TOKEN_RE.findall(text.lower())


class HashEmbedder:
    """Deterministic, network-free embedder for tests and Ollama-down fallback.

    Each token is hashed (blake2b) to derive a target dimension and a signed
    weight; token counts accumulate into a fixed-dimension vector which is then
    L2-normalised. Same input → same output, on any platform, with no I/O.
    """

    def __init__(self, dim: int = DEFAULT_DIM) -> None:
        if dim <= 0:
            raise ValueError(f"HashEmbedder dim must be positive, got {dim}")
        self.dim: int = dim
        self.name: str = HASH_FALLBACK_NAME

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for token in _tokenize(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dim
            # Sign from a separate byte so collisions don't all push one way.
            sign = 1.0 if (digest[4] & 1) == 0 else -1.0
            vec[index] += sign
        norm = math.sqrt(sum(component * component for component in vec))
        if norm > 0.0:
            vec = [component / norm for component in vec]
        return vec

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return deterministic L2-normalised vectors for ``texts``."""
        return [self._embed_one(text) for text in texts]


class OllamaEmbedderError(RuntimeError):
    """Raised when the Ollama embeddings endpoint cannot be used."""


class OllamaEmbedder:
    """Embedder backed by a local Ollama server.

    Posts to ``{ollama_url}/api/embeddings`` once per text (Ollama's embeddings
    endpoint accepts a single ``prompt`` per call). :attr:`dim` is detected from
    the first successful response and cached. Network failures raise
    :class:`OllamaEmbedderError` so callers can degrade to :class:`HashEmbedder`.
    """

    def __init__(
        self,
        model: str,
        base_url: str,
        *,
        timeout: float = 30.0,
        dim: int | None = None,
        max_chars: int = 6000,
    ) -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        # Embedding models have a bounded context window (e.g. nomic-embed-text
        # is ~2048 tokens). Inputs longer than that make Ollama return HTTP 500
        # ("input length exceeds the context length"). A whole-class code chunk
        # can easily exceed it, so we truncate to a conservative character
        # budget before embedding. For retrieval this is standard and safe: the
        # vector represents the leading (most identifying) portion of the chunk,
        # while the full text is still stored verbatim in the payload.
        self._max_chars = max_chars
        self.name: str = f"ollama:{model}"
        # Contract's Embedder.dim must be an int; default to the known
        # nomic-embed-text dimension until the first response confirms it.
        self.dim: int = dim if dim is not None else DEFAULT_DIM
        self._dim_detected: bool = dim is not None

    @property
    def model(self) -> str:
        """The Ollama embedding model name (e.g. ``nomic-embed-text``)."""
        return self._model

    def _prepare(self, text: str) -> str:
        """Clamp a text to the model's safe input budget.

        Empty/whitespace-only inputs are coerced to a single space so Ollama
        returns a real vector (an empty ``prompt`` yields an empty embedding).
        """
        clamped = text[: self._max_chars]
        return clamped if clamped.strip() else " "

    async def _embed_one(self, client: httpx.AsyncClient, text: str) -> list[float]:
        payload = {"model": self._model, "prompt": self._prepare(text)}
        try:
            resp = await client.post(
                f"{self._base_url}/api/embeddings",
                json=payload,
                timeout=self._timeout,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise OllamaEmbedderError(
                f"Ollama embeddings request failed ({self.name}): {exc}"
            ) from exc

        data = resp.json()
        embedding = data.get("embedding")
        if not isinstance(embedding, list) or not embedding:
            raise OllamaEmbedderError(
                f"Ollama returned no embedding for model {self._model!r}: {data!r}"
            )
        vector = [float(value) for value in embedding]
        if not self._dim_detected:
            self.dim = len(vector)
            self._dim_detected = True
            logger.info("Detected Ollama embedding dim=%d for %s.", self.dim, self.name)
        elif len(vector) != self.dim:
            raise OllamaEmbedderError(
                f"Ollama embedding dim drift for {self.name}: "
                f"expected {self.dim}, got {len(vector)}"
            )
        return vector

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed ``texts`` via Ollama, one request per text (ordered)."""
        if not texts:
            return []
        async with httpx.AsyncClient() as client:
            return [await self._embed_one(client, text) for text in texts]


def _probe_ollama(settings: RagSettings) -> bool:
    """Return ``True`` if the Ollama server answers within the probe timeout."""
    base = settings.ollama_url.rstrip("/")
    try:
        resp = httpx.get(f"{base}/api/tags", timeout=settings.probe_timeout_seconds)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.info("Ollama not reachable at %s (%s); using hash fallback.", base, exc)
        return False
    return True


def get_embedder(settings: RagSettings | None = None) -> Embedder:
    """Return the best available embedder for ``settings``.

    Probes Ollama; on success returns an :class:`OllamaEmbedder` (with the
    configured ``rag_embed_model``), otherwise logs the degradation and returns
    a :class:`HashEmbedder`. Never raises for a missing Ollama — degradation is
    logged, not fatal.
    """
    settings = settings or get_rag_settings()
    if _probe_ollama(settings):
        logger.info(
            "Using OllamaEmbedder model=%s at %s.",
            settings.rag_embed_model,
            settings.ollama_url,
        )
        return OllamaEmbedder(
            model=settings.rag_embed_model,
            base_url=settings.ollama_url,
            timeout=settings.http_timeout_seconds,
        )
    logger.warning("Falling back to HashEmbedder (dim=%d).", DEFAULT_DIM)
    return HashEmbedder(dim=DEFAULT_DIM)


__all__ = [
    "DEFAULT_DIM",
    "HASH_FALLBACK_NAME",
    "Embedder",
    "HashEmbedder",
    "OllamaEmbedder",
    "OllamaEmbedderError",
    "get_embedder",
]
