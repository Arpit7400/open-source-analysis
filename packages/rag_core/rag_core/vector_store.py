"""Vector store abstraction and the Qdrant-backed implementation.

This module defines the :class:`VectorStore` protocol from ``RAG_CONTRACT.md``
and a single production implementation, :class:`QdrantVectorStore`, built on the
``qdrant-client`` library.

Guiding principles honoured here (handbook §5, §6):

* **Local-first & replaceable.** The store selects its backing mode entirely
  from :class:`~rag_core.config.RagSettings`; nothing is hard-coded. Three modes
  are supported, in strict precedence order:

  1. ``qdrant:server`` — when :attr:`RagSettings.qdrant_url` points at a
     *reachable* Qdrant server (a fast pre-flight probe decides this).
  2. ``qdrant:local`` — an on-disk embedded Qdrant when
     :attr:`RagSettings.rag_qdrant_local_path` is set.
  3. ``qdrant:local`` — an in-process ``:memory:`` store otherwise.

* **Graceful degradation, never silent.** If the configured server URL is
  unreachable the store logs a warning and falls back to local mode. The chosen
  mode is exposed via :attr:`QdrantVectorStore.mode` and surfaced in health.

* **Async surface over a sync client.** ``qdrant-client``'s local mode is
  synchronous, so every protocol method runs the blocking call in a worker
  thread via :func:`asyncio.to_thread`, keeping the public API fully ``async``.

* **Version-defensive.** The current (1.12+) ``qdrant-client`` API is preferred
  (``query_points``, ``models.PointStruct``, ``models.Filter``), with guarded
  fallbacks to the legacy ``search`` API so the module keeps working across a
  range of client versions.

Everything is cross-platform: on-disk paths are resolved with :mod:`pathlib`.
"""

from __future__ import annotations

import asyncio
import logging
import socket
import uuid
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable
from urllib.parse import urlparse

from qdrant_client import QdrantClient, models

from rag_core.models import Chunk

# Fixed namespace for folding a Chunk's sha1-hex id into a deterministic
# UUIDv5 point id (Qdrant only accepts UUID / uint point ids). Stable across
# runs so re-indexing is idempotent.
_POINT_ID_NAMESPACE = uuid.UUID("6ba7b811-9dad-11d1-80b4-00c04fd430c8")

if TYPE_CHECKING:  # pragma: no cover - typing only
    from rag_core.config import RagSettings

logger = logging.getLogger(__name__)

# The set of scalar/optional ``Chunk`` fields we persist verbatim into the
# Qdrant payload. ``text`` and ``id`` are stored alongside these; ``imports``
# and ``metadata`` are containers handled explicitly on the way out.
_PAYLOAD_SCALAR_FIELDS: tuple[str, ...] = (
    "domain",
    "source_id",
    "source_type",
    "canonical_url",
    "path",
    "symbol",
    "start_line",
    "end_line",
    "language",
    "commit",
    "version",
    "published_at",
)


@runtime_checkable
class VectorStore(Protocol):
    """Swappable vector-store interface (see ``RAG_CONTRACT.md`` §Protocols)."""

    async def ensure_collection(self, name: str, dim: int) -> None:
        """Create ``name`` with cosine distance and ``dim`` size if absent."""
        ...

    async def upsert(
        self, name: str, chunks: list[Chunk], vectors: list[list[float]]
    ) -> int:
        """Store ``vectors`` with full chunk payloads; return points written."""
        ...

    async def search(
        self,
        name: str,
        vector: list[float],
        limit: int,
        flt: dict[str, Any] | None = None,
    ) -> list[tuple[Chunk, float]]:
        """Return ``(Chunk, score)`` pairs for the ``limit`` nearest vectors."""
        ...

    async def count(self, name: str) -> int:
        """Return the number of points stored in ``name`` (0 if absent)."""
        ...


class QdrantVectorStore:
    """A :class:`VectorStore` backed by ``qdrant-client``.

    The backing mode (server / on-disk local / in-memory local) is decided once,
    at construction time, from ``settings`` — see the module docstring for the
    precedence rules. ``mode`` reports the chosen backend for health/telemetry.
    """

    #: How long (seconds) to wait when probing a configured server URL.
    _PROBE_TIMEOUT_S: float = 0.75

    def __init__(self, settings: RagSettings) -> None:
        self._settings = settings
        self._client, self.mode = self._build_client(settings)
        logger.info("QdrantVectorStore initialised in mode=%s", self.mode)

    # -- construction --------------------------------------------------------

    @classmethod
    def _build_client(cls, settings: RagSettings) -> tuple[QdrantClient, str]:
        """Select and instantiate the backing client.

        Returns the client plus its mode string (``"qdrant:server"`` or
        ``"qdrant:local"``). Any failure to reach a configured server is logged
        and degrades to local mode rather than raising.
        """
        url = (getattr(settings, "qdrant_url", "") or "").strip()
        if url and cls._server_reachable(url):
            try:
                client = QdrantClient(url=url)
                logger.info("Connected to Qdrant server at %s", url)
                return client, "qdrant:server"
            except Exception as exc:  # pragma: no cover - network dependent
                logger.warning(
                    "Qdrant server %s reachable but client init failed (%s); "
                    "falling back to local mode.",
                    url,
                    exc,
                )
        elif url:
            logger.warning(
                "Qdrant server %s is not reachable; falling back to local mode.",
                url,
            )

        local_path = (getattr(settings, "rag_qdrant_local_path", "") or "").strip()
        if local_path:
            from pathlib import Path

            resolved = Path(local_path).expanduser()
            resolved.mkdir(parents=True, exist_ok=True)
            logger.info("Using on-disk local Qdrant at %s", resolved)
            return QdrantClient(path=str(resolved)), "qdrant:local"

        logger.info("Using in-memory (:memory:) local Qdrant")
        return QdrantClient(location=":memory:"), "qdrant:local"

    @classmethod
    def _server_reachable(cls, url: str) -> bool:
        """Cheap TCP pre-flight so an unreachable server never blocks startup."""
        parsed = urlparse(url if "://" in url else f"http://{url}")
        host = parsed.hostname or "localhost"
        port = parsed.port or (443 if parsed.scheme == "https" else 6333)
        try:
            with socket.create_connection((host, port), timeout=cls._PROBE_TIMEOUT_S):
                return True
        except OSError:
            return False

    # -- protocol methods ----------------------------------------------------

    async def ensure_collection(self, name: str, dim: int) -> None:
        await asyncio.to_thread(self._ensure_collection_sync, name, dim)

    async def upsert(
        self, name: str, chunks: list[Chunk], vectors: list[list[float]]
    ) -> int:
        if len(chunks) != len(vectors):
            raise ValueError(
                f"chunks/vectors length mismatch: {len(chunks)} != {len(vectors)}"
            )
        if not chunks:
            return 0
        return await asyncio.to_thread(self._upsert_sync, name, chunks, vectors)

    async def search(
        self,
        name: str,
        vector: list[float],
        limit: int,
        flt: dict[str, Any] | None = None,
    ) -> list[tuple[Chunk, float]]:
        return await asyncio.to_thread(self._search_sync, name, vector, limit, flt)

    async def count(self, name: str) -> int:
        return await asyncio.to_thread(self._count_sync, name)

    # -- synchronous internals (run in worker threads) -----------------------

    def _collection_exists(self, name: str) -> bool:
        try:
            return bool(self._client.collection_exists(name))
        except AttributeError:  # pragma: no cover - very old clients
            try:
                self._client.get_collection(name)
                return True
            except Exception:
                return False

    def _ensure_collection_sync(self, name: str, dim: int) -> None:
        if self._collection_exists(name):
            return
        self._client.create_collection(
            collection_name=name,
            vectors_config=models.VectorParams(
                size=dim, distance=models.Distance.COSINE
            ),
        )
        logger.debug("Created collection %s (dim=%d, distance=COSINE)", name, dim)

    def _upsert_sync(
        self, name: str, chunks: list[Chunk], vectors: list[list[float]]
    ) -> int:
        points = [
            models.PointStruct(
                id=self._point_id(chunk),
                vector=list(vector),
                payload=self._chunk_to_payload(chunk),
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        self._client.upsert(collection_name=name, points=points, wait=True)
        return len(points)

    def _search_sync(
        self,
        name: str,
        vector: list[float],
        limit: int,
        flt: dict[str, Any] | None,
    ) -> list[tuple[Chunk, float]]:
        if not self._collection_exists(name):
            return []
        query_filter = self._build_filter(flt)
        scored = self._run_query(name, vector, limit, query_filter)
        results: list[tuple[Chunk, float]] = []
        for point in scored:
            payload = point.payload or {}
            results.append((self._payload_to_chunk(payload), float(point.score)))
        return results

    def _run_query(
        self,
        name: str,
        vector: list[float],
        limit: int,
        query_filter: models.Filter | None,
    ) -> list[Any]:
        """Prefer the 1.12+ ``query_points`` API, fall back to ``search``."""
        query_points = getattr(self._client, "query_points", None)
        if callable(query_points):
            response = query_points(
                collection_name=name,
                query=list(vector),
                limit=limit,
                query_filter=query_filter,
                with_payload=True,
            )
            # ``QueryResponse`` exposes ``.points``; be defensive if not.
            return list(getattr(response, "points", response) or [])
        # Legacy client fallback.
        return list(
            self._client.search(  # type: ignore[attr-defined]
                collection_name=name,
                query_vector=list(vector),
                limit=limit,
                query_filter=query_filter,
                with_payload=True,
            )
        )

    def _count_sync(self, name: str) -> int:
        if not self._collection_exists(name):
            return 0
        try:
            result = self._client.count(collection_name=name, exact=True)
            return int(getattr(result, "count", 0) or 0)
        except Exception as exc:  # pragma: no cover - backend dependent
            logger.warning("count(%s) failed: %s", name, exc)
            return 0

    # -- payload <-> Chunk ---------------------------------------------------

    @staticmethod
    def _point_id(chunk: Chunk) -> str:
        """Qdrant point id.

        Qdrant only accepts point ids that are unsigned integers or UUID
        strings (its local/in-process mode enforces this strictly). The
        contract's :meth:`Chunk.make_id` yields a stable *sha1-hex* string,
        which is not a valid UUID, so we deterministically fold it into a
        UUIDv5. The mapping is stable (same ``chunk.id`` -> same UUID), so
        re-indexing the same chunk still overwrites in place (idempotent), and
        the original ``chunk.id`` is preserved verbatim in the payload
        (``payload["id"]``) for lossless round-tripping.
        """
        return str(uuid.uuid5(_POINT_ID_NAMESPACE, chunk.id))

    @staticmethod
    def _chunk_to_payload(chunk: Chunk) -> dict[str, Any]:
        """Serialise a :class:`Chunk` into a flat Qdrant payload.

        Every field needed to reconstruct the chunk on read is stored. ``None``
        values are kept so round-tripping is lossless and filters on absent
        fields behave predictably.
        """
        payload: dict[str, Any] = {"id": chunk.id, "text": chunk.text}
        for field in _PAYLOAD_SCALAR_FIELDS:
            payload[field] = getattr(chunk, field)
        payload["imports"] = list(chunk.imports)
        payload["metadata"] = dict(chunk.metadata)
        return payload

    @staticmethod
    def _payload_to_chunk(payload: dict[str, Any]) -> Chunk:
        """Reconstruct a :class:`Chunk` from a stored payload."""
        data: dict[str, Any] = {
            "id": payload.get("id", ""),
            "text": payload.get("text", ""),
        }
        for field in _PAYLOAD_SCALAR_FIELDS:
            data[field] = payload.get(field)
        data["imports"] = list(payload.get("imports") or [])
        raw_meta = payload.get("metadata") or {}
        data["metadata"] = {str(k): str(v) for k, v in dict(raw_meta).items()}
        return Chunk(**data)

    # -- filter construction -------------------------------------------------

    def _build_filter(self, flt: dict[str, Any] | None) -> models.Filter | None:
        """Translate a plain dict of payload constraints into a Qdrant filter.

        Supported keys (all optional, combined with logical AND):

        * ``source_type``, ``version``, ``language`` — exact match. A list value
          becomes a "match any" (``MatchAny``) constraint.
        * ``published_at`` — a ``{"gte"|"lte"|"gt"|"lt": <iso8601>}`` range
          (lexicographic ISO-8601 ordering) *or* a bare string for exact match.
        * ``path`` — exact match; ``path_prefix`` — a prefix ``MatchText`` on the
          ``path`` field so callers can scope to a directory/module.
        * Any other key — exact match against the same-named payload field,
          so the store stays useful as the payload schema grows.
        """
        if not flt:
            return None

        must: list[models.FieldCondition] = []

        for key, value in flt.items():
            if value is None:
                continue
            if key == "path_prefix":
                must.append(
                    models.FieldCondition(
                        key="path", match=models.MatchText(text=str(value))
                    )
                )
                continue
            if key == "published_at" and isinstance(value, dict):
                rng = self._published_range(value)
                if rng is not None:
                    must.append(
                        models.FieldCondition(key="published_at", range=rng)
                    )
                continue
            if isinstance(value, (list, tuple, set)):
                must.append(
                    models.FieldCondition(
                        key=key,
                        match=models.MatchAny(any=[self._scalar(v) for v in value]),
                    )
                )
                continue
            must.append(
                models.FieldCondition(
                    key=key, match=models.MatchValue(value=self._scalar(value))
                )
            )

        if not must:
            return None
        return models.Filter(must=must)

    @staticmethod
    def _published_range(spec: dict[str, Any]) -> models.DatetimeRange | None:
        """Build a datetime range filter over ISO-8601 ``published_at`` values.

        ISO-8601 strings sort lexicographically, and ``DatetimeRange`` accepts
        RFC-3339 strings, so this supports time/version windows without needing
        to parse dates ourselves.
        """
        kwargs: dict[str, Any] = {}
        for bound in ("gte", "lte", "gt", "lt"):
            if spec.get(bound) is not None:
                kwargs[bound] = str(spec[bound])
        if not kwargs:
            return None
        return models.DatetimeRange(**kwargs)

    @staticmethod
    def _scalar(value: Any) -> Any:
        """Coerce a filter value to a Qdrant-comparable scalar."""
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value
        return str(value)


__all__ = ["QdrantVectorStore", "VectorStore"]
