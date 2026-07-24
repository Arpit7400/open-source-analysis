"""Runtime configuration for the RAG subsystem.

:class:`RagSettings` reads the ``CAREERFORGE_`` environment prefix (matching
``apps/api/careerforge_api/config.py``) and adds the ``RAG_*`` keys from
``docs/RAG_CONTRACT.md`` § *Config*. Service URLs (``ollama_url``,
``qdrant_url``) reuse the existing conventions so a single ``.env`` configures
both the API app and this package.

Everything is cross-platform: local Qdrant paths are resolved with
:mod:`pathlib`, and no shell/OS-specific behaviour is assumed. The default
posture is **local-first, degrade-gracefully**: with no reachable Qdrant server
the store runs in-process (on-disk path or ``:memory:``); with no Ollama the
embedder falls back to a deterministic hash embedder (see ``embeddings.py``).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

import httpx
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("rag_core.config")


class QdrantMode(str, Enum):
    """How the vector store connects to Qdrant."""

    SERVER = "server"  # remote/local Qdrant HTTP server via qdrant_url
    LOCAL_PATH = "local_path"  # in-process persistent store at a filesystem path
    MEMORY = "memory"  # in-process ephemeral store (":memory:")


@dataclass(frozen=True)
class QdrantTarget:
    """Resolved Qdrant connection target.

    Exactly one of ``url`` / ``path`` is meaningful depending on ``mode``:

    * ``SERVER`` → ``url`` holds the reachable server URL.
    * ``LOCAL_PATH`` → ``path`` holds the on-disk store directory.
    * ``MEMORY`` → neither; construct ``QdrantClient(":memory:")``.

    ``label`` is the value reported in :attr:`RagAnswer.used_vector_store`
    (``"qdrant:server"`` or ``"qdrant:local"``).
    """

    mode: QdrantMode
    url: str | None = None
    path: str | None = None

    @property
    def label(self) -> str:
        """Return the contract's ``used_vector_store`` label for this target."""
        return "qdrant:server" if self.mode is QdrantMode.SERVER else "qdrant:local"


class RagSettings(BaseSettings):
    """RAG subsystem settings (env prefix ``CAREERFORGE_``).

    Reuses ``ollama_url`` / ``qdrant_url`` from the base API settings and adds
    the ``rag_*`` keys. Field names map to env vars by upper-casing and
    prefixing, e.g. ``rag_embed_model`` → ``CAREERFORGE_RAG_EMBED_MODEL``.
    """

    model_config = SettingsConfigDict(
        env_prefix="CAREERFORGE_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- reused service URLs (shared with apps/api) ------------------------
    ollama_url: str = Field(default="http://localhost:11434")
    qdrant_url: str = Field(default="http://localhost:6333")

    # --- RAG-specific keys (RAG_CONTRACT.md § Config) ----------------------
    rag_embed_model: str = Field(default="nomic-embed-text")
    rag_rerank_model: str = Field(default="")  # empty -> lexical reranker
    rag_qdrant_local_path: str = Field(default="")  # empty -> :memory:
    rag_min_score: float = Field(default=0.15)
    rag_top_n: int = Field(default=30, ge=1)  # per-retriever pool
    rag_top_k: int = Field(default=8, ge=1)  # final context
    rag_llm_model: str = Field(default="qwen2.5:7b")  # claim gen/verify (optional)

    # --- tuning knobs (sensible defaults; overridable via env) -------------
    http_timeout_seconds: float = Field(default=30.0, gt=0.0)
    probe_timeout_seconds: float = Field(default=2.0, gt=0.0)
    rrf_k: int = Field(default=60, ge=1)

    def qdrant_server_reachable(self) -> bool:
        """Probe ``qdrant_url`` with a short timeout.

        Returns ``True`` only when the URL is well-formed and the server answers
        its readiness/root endpoint. Any network error, timeout, or malformed
        URL yields ``False`` (and is logged) so we degrade to local mode.
        """
        parsed = urlparse(self.qdrant_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            logger.info(
                "Qdrant URL %r is not an http(s) URL; using local Qdrant mode.",
                self.qdrant_url,
            )
            return False

        base = self.qdrant_url.rstrip("/")
        # Qdrant exposes "/readyz" (newer) and a JSON root ("/"). Try both.
        for path in ("/readyz", "/"):
            try:
                resp = httpx.get(f"{base}{path}", timeout=self.probe_timeout_seconds)
            except httpx.HTTPError as exc:  # connection refused, timeout, DNS, ...
                logger.debug("Qdrant probe %s%s failed: %s", base, path, exc)
                continue
            if resp.status_code < 500:
                return True
        logger.info(
            "Qdrant server at %s is not reachable; using local Qdrant mode.",
            self.qdrant_url,
        )
        return False

    def resolve_qdrant_target(self, *, probe: bool = True) -> QdrantTarget:
        """Decide the Qdrant connection target per the contract's precedence.

        Order:

        1. If ``probe`` and ``qdrant_url`` is reachable → :class:`QdrantMode.SERVER`.
        2. Else if ``rag_qdrant_local_path`` is set → on-disk local store
           (:class:`QdrantMode.LOCAL_PATH`); the directory is created if absent.
        3. Else → in-process ``:memory:`` store (:class:`QdrantMode.MEMORY`).

        The chosen mode is logged so degradation is never silent.
        """
        if probe and self.qdrant_server_reachable():
            logger.info("Using Qdrant server at %s.", self.qdrant_url)
            return QdrantTarget(mode=QdrantMode.SERVER, url=self.qdrant_url)

        local_path = self.rag_qdrant_local_path.strip()
        if local_path:
            path = Path(local_path).expanduser().resolve()
            path.mkdir(parents=True, exist_ok=True)
            logger.info("Using on-disk local Qdrant at %s.", path)
            return QdrantTarget(mode=QdrantMode.LOCAL_PATH, path=str(path))

        logger.info("Using in-process Qdrant (:memory:).")
        return QdrantTarget(mode=QdrantMode.MEMORY)


@lru_cache(maxsize=1)
def get_rag_settings() -> RagSettings:
    """Return a cached :class:`RagSettings` instance.

    Cached so the ``.env`` file and environment are read once per process. Use
    ``get_rag_settings.cache_clear()`` in tests to force a re-read.
    """
    return RagSettings()


__all__ = [
    "QdrantMode",
    "QdrantTarget",
    "RagSettings",
    "get_rag_settings",
]
