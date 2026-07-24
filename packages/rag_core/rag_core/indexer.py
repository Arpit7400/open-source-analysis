"""Repository & document indexing (handbook §5.3).

:class:`RepositoryIndexer` walks a local directory, chunks each text file with
the content-aware :func:`rag_core.chunking.chunk_file`, embeds the chunks in
batches, ensures the target Qdrant collection exists, upserts the vectors, and
registers the chunks with the :class:`rag_core.retrieval.HybridRetriever` so the
BM25 sparse index stays in lock-step with the vector store.

Domain routing (fixed collection names from ``rag_core.domains``):

* Python / other source and test files → ``repository_code``.
* Markdown / reST / doc files            → ``repository_docs``.

Everything is cross-platform: the walk, ignore matching, and path recording all
use :mod:`pathlib`, and file paths are recorded as repo-relative POSIX strings so
provenance is stable across operating systems. Binary/undecodable files are
skipped (logged), never fatal.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rag_core.chunking import chunk_file
from rag_core.config import RagSettings, get_rag_settings
from rag_core.domains import REPOSITORY_CODE, REPOSITORY_DOCS, validate_domain
from rag_core.models import Chunk

if TYPE_CHECKING:  # pragma: no cover - typing only
    from rag_core.embeddings import Embedder
    from rag_core.retrieval import HybridRetriever
    from rag_core.vector_store import VectorStore

logger = logging.getLogger("rag_core.indexer")

#: Directory names never descended into during a repository walk.
DEFAULT_IGNORE_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        ".venv",
        "venv",
        "env",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        "dist",
        "build",
        ".next",
        ".nuxt",
        ".turbo",
        "target",
        ".idea",
        ".vscode",
        ".cache",
        "coverage",
        ".coverage",
        "site-packages",
        ".gradle",
        ".terraform",
    }
)

#: File suffixes routed to the ``repository_docs`` collection.
_DOC_EXTS: frozenset[str] = frozenset(
    {".md", ".markdown", ".mdx", ".rst", ".txt", ".adoc"}
)

#: File suffixes routed to the ``repository_code`` collection. This is the set of
#: text-ish source extensions we index; anything else is skipped as non-textual.
_CODE_EXTS: frozenset[str] = frozenset(
    {
        ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
        ".go", ".rs", ".java", ".kt", ".kts", ".c", ".h", ".cc", ".cpp",
        ".hpp", ".cs", ".rb", ".php", ".swift", ".scala", ".sh", ".bash",
        ".zsh", ".sql", ".r", ".m", ".mm", ".lua", ".pl", ".pm",
        ".yaml", ".yml", ".toml", ".ini", ".cfg", ".json",
    }
)

#: Max characters read from any single file (guards against giant blobs).
_MAX_FILE_BYTES: int = 2_000_000

#: Chunks embedded per Ollama batch (bounds concurrent request fan-out).
_EMBED_BATCH: int = 64


class RepositoryIndexer:
    """Walk, chunk, embed and upsert a local repository into the vector store.

    Parameters
    ----------
    embedder, vector_store, retriever, settings:
        Injected collaborators. ``retriever`` receives every indexed chunk via
        :meth:`HybridRetriever.register_chunks` so sparse retrieval works.
    """

    def __init__(
        self,
        embedder: Embedder,
        vector_store: VectorStore,
        retriever: HybridRetriever,
        settings: RagSettings | None = None,
    ) -> None:
        self._embedder = embedder
        self._store = vector_store
        self._retriever = retriever
        self._settings = settings or get_rag_settings()

    # -- public API ----------------------------------------------------------

    async def index_repository(
        self,
        repo_path: str | Path,
        repo_id: str,
        commit: str | None = None,
    ) -> dict[str, Any]:
        """Index a local repository directory.

        Returns a summary dict matching ``POST /api/v1/rag/index/repository``::

            {
              "indexed_chunks": int,
              "collections": {domain: count},   # chunks indexed per collection
              "embedder": str,                   # embedder.name
              "store": str,                      # vector_store.mode
            }

        The walk respects :data:`DEFAULT_IGNORE_DIRS`, reads UTF-8 text files
        (undecodable/oversized files are skipped and logged), routes each file
        to ``repository_code`` or ``repository_docs``, and upserts per domain.
        """
        root = Path(repo_path).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            raise NotADirectoryError(f"repo_path is not a directory: {root}")

        # Collect chunks per destination collection, in a deterministic file order.
        per_domain: dict[str, list[Chunk]] = {
            REPOSITORY_CODE: [],
            REPOSITORY_DOCS: [],
        }
        for file_path in self._iter_files(root):
            text = self._read_text(file_path)
            if text is None:
                continue
            rel = file_path.relative_to(root).as_posix()
            domain = self._route(file_path)
            try:
                chunks = chunk_file(
                    path=rel,
                    text=text,
                    domain=domain,
                    source_id=repo_id,
                    commit=commit,
                )
            except Exception as exc:  # pragma: no cover - chunker is robust
                logger.warning("Chunking failed for %s (%s); skipping.", rel, exc)
                continue
            per_domain[domain].extend(chunks)

        counts: dict[str, int] = {}
        total = 0
        for domain, chunks in per_domain.items():
            if not chunks:
                continue
            written = await self._embed_and_store(domain, chunks)
            counts[domain] = written
            total += written

        summary = {
            "indexed_chunks": total,
            "collections": counts,
            "embedder": self._embedder.name,
            "store": getattr(self._store, "mode", "qdrant:local"),
        }
        logger.info(
            "Indexed repo_id=%s from %s: %d chunk(s) across %s.",
            repo_id,
            root,
            total,
            counts,
        )
        return summary

    async def index_documents(
        self,
        domain: str,
        docs: Iterable[Chunk],
    ) -> dict[str, Any]:
        """Index a pre-chunked corpus into any of the six domains.

        For non-repository sources (profile evidence, industry sources, issues,
        evaluation memory). ``docs`` are already :class:`Chunk` objects with
        their provenance set by the caller. Returns the same summary shape as
        :meth:`index_repository` (``collections`` has a single entry).
        """
        validate_domain(domain)
        chunks = list(docs)
        if not chunks:
            return {
                "indexed_chunks": 0,
                "collections": {},
                "embedder": self._embedder.name,
                "store": getattr(self._store, "mode", "qdrant:local"),
            }
        written = await self._embed_and_store(domain, chunks)
        return {
            "indexed_chunks": written,
            "collections": {domain: written},
            "embedder": self._embedder.name,
            "store": getattr(self._store, "mode", "qdrant:local"),
        }

    # -- indexing internals --------------------------------------------------

    async def _embed_and_store(self, domain: str, chunks: list[Chunk]) -> int:
        """Embed ``chunks`` in batches, ensure the collection, upsert, register.

        Returns the number of points written. Registers the chunks with the
        retriever's BM25 mirror even if the vector upsert wrote fewer than
        ``len(chunks)`` (so sparse retrieval still covers everything indexed).
        """
        vectors: list[list[float]] = []
        for batch in self._batched(chunks, _EMBED_BATCH):
            vectors.extend(await self._embedder.embed([c.text for c in batch]))

        if len(vectors) != len(chunks):  # pragma: no cover - defensive
            raise RuntimeError(
                f"Embedder returned {len(vectors)} vectors for {len(chunks)} chunks."
            )

        await self._store.ensure_collection(domain, self._embedder.dim)
        written = await self._store.upsert(domain, chunks, vectors)

        # Keep BM25 in lock-step with what we just indexed.
        self._retriever.register_chunks(domain, chunks)
        return int(written)

    # -- filesystem walk -----------------------------------------------------

    def _iter_files(self, root: Path) -> list[Path]:
        """Return indexable files under ``root`` in a deterministic order.

        Ignored directories (:data:`DEFAULT_IGNORE_DIRS`) are pruned. Only files
        whose suffix is a known doc or code extension are returned. Symlinked
        directories are not followed to avoid cycles.
        """
        results: list[Path] = []
        stack: list[Path] = [root]
        while stack:
            current = stack.pop()
            try:
                entries = sorted(current.iterdir(), key=lambda p: p.name)
            except (PermissionError, OSError) as exc:
                logger.debug("Cannot list %s (%s); skipping.", current, exc)
                continue
            for entry in entries:
                try:
                    is_dir = entry.is_dir() and not entry.is_symlink()
                except OSError:
                    continue
                if is_dir:
                    if entry.name in DEFAULT_IGNORE_DIRS:
                        continue
                    stack.append(entry)
                    continue
                if self._is_indexable(entry):
                    results.append(entry)
        results.sort(key=lambda p: p.as_posix())
        return results

    @staticmethod
    def _is_indexable(path: Path) -> bool:
        ext = path.suffix.lower()
        return ext in _DOC_EXTS or ext in _CODE_EXTS

    @staticmethod
    def _route(path: Path) -> str:
        """Route ``repository_docs`` for doc suffixes, else ``repository_code``."""
        return REPOSITORY_DOCS if path.suffix.lower() in _DOC_EXTS else REPOSITORY_CODE

    @staticmethod
    def _read_text(path: Path) -> str | None:
        """Read a file as UTF-8 text, skipping oversized/undecodable files."""
        try:
            size = path.stat().st_size
        except OSError as exc:
            logger.debug("stat(%s) failed (%s); skipping.", path, exc)
            return None
        if size > _MAX_FILE_BYTES:
            logger.info("Skipping oversized file %s (%d bytes).", path, size)
            return None
        try:
            return path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, ValueError):
            logger.debug("Skipping non-UTF-8/binary file %s.", path)
            return None
        except OSError as exc:
            logger.debug("read(%s) failed (%s); skipping.", path, exc)
            return None

    @staticmethod
    def _batched(items: list[Chunk], size: int) -> Iterable[list[Chunk]]:
        for start in range(0, len(items), size):
            yield items[start : start + size]


__all__ = ["DEFAULT_IGNORE_DIRS", "RepositoryIndexer"]
