"""Thin adapter between the FastAPI transport layer and ``github_client``.

This module owns the *lifecycle* of the real, read-only GitHub client inside the
API process and the wiring that feeds real repository content into the RAG
subsystem. It:

* Lazily builds a **singleton** :class:`github_client.GitHubClient` (a fresh
  short-lived instance is created per operation and closed afterwards, but the
  resolved :class:`github_client.GithubSettings` are cached once per process).
  The client works unauthenticated when ``CAREERFORGE_GITHUB_TOKEN`` is unset,
  or authenticated with a read-only PAT when it is — matching the contract.

* Exposes **async wrappers** for the read-only operations the API surfaces:
  :func:`get_repo`, :func:`list_issues`, :func:`list_pulls`, :func:`list_commits`,
  :func:`list_releases`, and :func:`rate_limit`. Each returns the typed
  :mod:`github_client` Pydantic models untouched.

* Provides :func:`index_repo`, which fetches a repository's README (→
  ``repository_docs``) and its Python files (→ ``repository_code``) via the
  read-only client and pushes them into the real ``rag_core`` pipeline (reached
  through :mod:`careerforge_api.rag_service`). It returns an index summary.

* Reports subsystem health via :func:`health_label`, returning
  ``"authenticated" | "anonymous" | "down"`` for ``GET /system/health``.

**Never leaks the token.** The token lives only inside the ``github_client``
:class:`~pydantic.SecretStr`; this adapter never reads, logs, returns, or places
it in an error. Every GitHub failure is caught and translated to a
:class:`GitHubServiceError` whose message is already redacted by the client.

**Degrades cleanly.** If ``github_client`` cannot be imported, or the network is
unreachable, health reports ``"down"`` and operations raise
:class:`GitHubServiceError`; the rest of the API keeps serving.

Everything is cross-platform: no shell/OS-specific behaviour is assumed and all
imports resolve through the installed packages.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:  # pragma: no cover - typing only
    from github_client import (
        CommitRef,
        GitHubClient,
        IssueRef,
        PullRef,
        RateLimit,
        RepoMeta,
    )

logger = logging.getLogger("careerforge_api.github_service")


class GitHubServiceError(RuntimeError):
    """Raised when a GitHub operation could not be completed.

    Carries a human-readable, **already-redacted** ``reason`` the router surfaces
    in the contract error envelope's ``detail``. It is never constructed with a
    string that could contain a credential (the underlying client redacts all of
    its own error messages before they reach here).
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class _GitHubService:
    """Process-wide holder for cached settings + client construction state.

    A single instance (:data:`_SERVICE`) is shared by every request. The heavy,
    import-time-sensitive work (importing ``github_client`` and resolving its
    settings) is done once and cached; each operation then constructs a
    short-lived :class:`~github_client.GitHubClient` bound to those settings and
    closes it when done, so no long-lived sockets are held between requests.
    """

    def __init__(self) -> None:
        self._import_failed_reason: str | None = None
        self._settings: Any | None = None
        self._lock = asyncio.Lock()

    # -- construction --------------------------------------------------------

    def _load_module(self) -> Any | None:
        """Import :mod:`github_client`, caching an import failure reason.

        Returns the module or ``None`` (with :attr:`_import_failed_reason` set)
        on failure, so the API keeps booting when the package is missing.
        """
        try:
            import github_client as _gh
        except Exception as exc:  # ImportError or transitive dep failure
            self._import_failed_reason = f"github_client import failed: {exc}"
            logger.warning(
                "GitHub subsystem unavailable: %s. GitHub endpoints will report 'down'.",
                self._import_failed_reason,
            )
            return None
        return _gh

    def _resolve_settings(self) -> Any | None:
        """Resolve and cache :class:`github_client.GithubSettings` once."""
        if self._settings is not None:
            return self._settings
        module = self._load_module()
        if module is None:
            return None
        try:
            self._settings = module.get_github_settings()
        except Exception as exc:  # settings/env resolution failure
            self._import_failed_reason = f"GithubSettings resolution failed: {exc}"
            logger.warning(
                "GitHub subsystem unavailable: %s. GitHub endpoints will report 'down'.",
                self._import_failed_reason,
            )
            return None
        return self._settings

    def _new_client(self) -> GitHubClient:
        """Construct a fresh read-only client bound to the cached settings.

        Raises :class:`GitHubServiceError` when the package/settings could not be
        resolved. The returned client MUST be closed by the caller (use
        :meth:`_call`, which does this for you).
        """
        module = self._load_module()
        if module is None:
            raise GitHubServiceError(
                self._import_failed_reason or "GitHub subsystem is unavailable."
            )
        settings = self._resolve_settings()
        if settings is None:
            raise GitHubServiceError(
                self._import_failed_reason or "GitHub subsystem is unavailable."
            )
        return cast("GitHubClient", module.GitHubClient(settings))

    # -- health --------------------------------------------------------------

    def health_label(self) -> str:
        """Return the ``services.github`` value for ``/system/health``.

        One of:

        * ``"authenticated"`` — the package imported and a read-only PAT is set.
        * ``"anonymous"``     — the package imported but no token is configured.
        * ``"down"``          — ``github_client`` could not be imported / settings
          could not be resolved.

        Synchronous and non-networking: it never contacts GitHub (so health stays
        fast) and never raises — a probe failure reports ``"down"``.
        """
        try:
            settings = self._resolve_settings()
            if settings is None:
                return "down"
            return "authenticated" if bool(settings.is_authenticated) else "anonymous"
        except Exception as exc:  # health must never raise
            logger.debug("github health_label probe failed (%s); reporting down.", exc)
            return "down"


# Process-wide singleton used by the wrappers, the router, and health.
_SERVICE = _GitHubService()


# ---------------------------------------------------------------------------
# Internal call helper — one guarded client lifecycle per operation.
# ---------------------------------------------------------------------------
async def _call(method_name: str, *args: Any, **kwargs: Any) -> Any:
    """Invoke a read-only :class:`GitHubClient` method, guarded and closed.

    Constructs a fresh client, calls ``method_name`` with ``*args``/``**kwargs``,
    and always closes the client. Any ``github_client`` error (rate limit, 404,
    transport) is re-raised unchanged so the router can map it precisely; any
    other failure is wrapped in :class:`GitHubServiceError`. The token never
    appears in any raised message.
    """
    client = _SERVICE._new_client()
    try:
        method = getattr(client, method_name)
        return await method(*args, **kwargs)
    except GitHubServiceError:
        raise
    except Exception as exc:
        # github_client's own errors (GitHubClientError / RateLimitError /
        # ReadOnlyViolation) are already redacted; re-raise them verbatim so the
        # router can special-case rate limits / not-found. Anything else becomes
        # a redaction-safe GitHubServiceError.
        module = _SERVICE._load_module()
        if module is not None and isinstance(exc, module.GitHubClientError):
            raise
        raise GitHubServiceError(f"GitHub operation {method_name} failed: {exc}") from None
    finally:
        try:
            await client.aclose()
        except Exception:  # pragma: no cover - close is best-effort
            logger.debug("github client aclose failed after %s", method_name)


# ---------------------------------------------------------------------------
# Read-only async wrappers (thin passthroughs to GitHubClient).
# ---------------------------------------------------------------------------
async def get_repo(owner: str, name: str) -> Any:
    """Return :class:`github_client.RepoMeta` for ``owner/name``."""
    return cast("RepoMeta", await _call("get_repo", owner, name))


async def list_issues(
    owner: str, name: str, state: str = "open", limit: int = 30
) -> list[IssueRef]:
    """List issues (PRs excluded) for ``owner/name``."""
    return cast("list[IssueRef]", await _call("list_issues", owner, name, state=state, limit=limit))


async def list_pulls(
    owner: str, name: str, state: str = "open", limit: int = 30
) -> list[PullRef]:
    """List pull requests for ``owner/name``."""
    return cast("list[PullRef]", await _call("list_pulls", owner, name, state=state, limit=limit))


async def list_commits(
    owner: str, name: str, limit: int = 30, sha: str | None = None
) -> list[CommitRef]:
    """List commits for ``owner/name``."""
    return cast("list[CommitRef]", await _call("list_commits", owner, name, limit=limit, sha=sha))


async def list_releases(owner: str, name: str, limit: int = 10) -> list[Any]:
    """List releases for ``owner/name``."""
    return cast("list[Any]", await _call("list_releases", owner, name, limit=limit))


async def rate_limit() -> RateLimit:
    """Return the current core :class:`github_client.RateLimit`."""
    return cast("RateLimit", await _call("rate_limit"))


def health_label() -> str:
    """Return the ``services.github`` health string; see :meth:`_GitHubService.health_label`."""
    return _SERVICE.health_label()


# ---------------------------------------------------------------------------
# Indexing — feed real repo content into rag_core.
# ---------------------------------------------------------------------------
#: Max Python files fetched + indexed per ``index_repo`` call. Bounds both the
#: number of GitHub content requests and the RAG write size for a single call.
_MAX_PYTHON_FILES: int = 40


def _repo_id(owner: str, name: str) -> str:
    """Canonical ``owner/name`` provenance id used for indexed chunks."""
    return f"{owner}/{name}"


def _make_doc_chunks(
    module: Any, domain: str, repo_id: str, path: str, text: str, url: str | None
) -> list[Any]:
    """Build ``repository_docs``/``repository_code`` chunks for one file.

    Uses ``rag_core``'s AST/markdown chunker when importable so code and docs
    are split exactly like a local index; falls back to a single whole-file
    :class:`rag_core.models.Chunk` when the chunker is unavailable. ``module`` is
    the imported ``rag_core`` package.
    """
    text = text or ""
    if not text.strip():
        return []

    # Prefer the real chunker for parity with a local repository index.
    try:
        from rag_core.chunking import chunk_file

        chunks = list(
            chunk_file(path=path, text=text, domain=domain, source_id=repo_id, commit=None)
        )
        if chunks:
            for chunk in chunks:
                if url and getattr(chunk, "canonical_url", None) is None:
                    chunk.canonical_url = url
            return chunks
    except Exception as exc:  # chunker missing or failed -> whole-file fallback
        logger.debug("chunk_file unavailable/failed for %s (%s); whole-file chunk.", path, exc)

    chunk_cls = module.Chunk
    source_type = "CODE" if domain.endswith("code") else "DOC"
    chunk = chunk_cls(
        id=chunk_cls.make_id(domain, repo_id, path, None, None),
        domain=domain,
        text=text,
        source_id=repo_id,
        source_type=source_type,
        canonical_url=url,
        path=path,
    )
    return [chunk]


async def index_repo(owner: str, name: str) -> dict[str, Any]:
    """Fetch README + Python files for ``owner/name`` and index them into RAG.

    Pulls the README (indexed into ``repository_docs``) and up to
    :data:`_MAX_PYTHON_FILES` Python files (indexed into ``repository_code``)
    using the read-only GitHub client, converts them to ``rag_core`` chunks, and
    upserts them via the real pipeline reached through
    :mod:`careerforge_api.rag_service`.

    Returns an index summary::

        {
          "repo": "owner/name",
          "indexed_chunks": int,
          "collections": {domain: count},
          "files_indexed": {"readme": 0|1, "python": int},
          "embedder": str,
          "store": str,
        }

    Raises :class:`GitHubServiceError` when the GitHub subsystem is unavailable
    or the RAG pipeline could not be built; re-raises ``github_client`` errors
    (rate limit / not found) so the router can map them to the right status.
    """
    module = _SERVICE._load_module()
    if module is None:
        raise GitHubServiceError(
            _SERVICE._import_failed_reason or "GitHub subsystem is unavailable."
        )

    # rag_core is required to index; import it eagerly so a missing RAG stack is
    # reported as a service error rather than a 500 deep in the pipeline.
    try:
        import rag_core as _rag_core
        from rag_core.domains import REPOSITORY_CODE, REPOSITORY_DOCS
    except Exception as exc:
        raise GitHubServiceError(f"rag_core is unavailable for indexing: {exc}") from None

    from careerforge_api import rag_service

    repo_id = _repo_id(owner, name)

    # --- Fetch content over the read-only client (single lifecycle) ---------
    client = _SERVICE._new_client()
    readme_indexed = 0
    doc_chunks: list[Any] = []
    code_chunks: list[Any] = []
    python_paths: list[str] = []
    try:
        # README -> repository_docs
        try:
            readme = await client.get_readme(owner, name)
        except module.GitHubClientError:
            raise
        except Exception as exc:  # pragma: no cover - unexpected client failure
            raise GitHubServiceError(f"Failed to fetch README: {exc}") from None
        if readme is not None and readme.text:
            doc_chunks.extend(
                _make_doc_chunks(
                    _rag_core,
                    REPOSITORY_DOCS,
                    repo_id,
                    readme.path or "README.md",
                    readme.text,
                    readme.url,
                )
            )
            readme_indexed = 1

        # Python files -> repository_code
        try:
            python_paths = await client.list_python_files(owner, name, limit=_MAX_PYTHON_FILES)
        except module.GitHubClientError:
            raise
        except Exception as exc:  # pragma: no cover - unexpected client failure
            raise GitHubServiceError(f"Failed to list Python files: {exc}") from None

        for path in python_paths[:_MAX_PYTHON_FILES]:
            try:
                content = await client.get_file(owner, name, path)
            except module.GitHubClientError:
                raise
            except Exception as exc:  # pragma: no cover - unexpected client failure
                logger.debug("Skipping %s: %s", path, exc)
                continue
            if content is None or not content.text:
                continue
            code_chunks.extend(
                _make_doc_chunks(
                    _rag_core,
                    REPOSITORY_CODE,
                    repo_id,
                    content.path or path,
                    content.text,
                    content.url,
                )
            )
    finally:
        try:
            await client.aclose()
        except Exception:  # pragma: no cover - close is best-effort
            logger.debug("github client aclose failed during index_repo")

    # --- Push into the RAG pipeline -----------------------------------------
    try:
        pipeline = await rag_service._SERVICE._ensure_ready()
    except Exception as exc:
        # rag_service raises RagUnavailableError (a RuntimeError) when down.
        reason = getattr(exc, "reason", str(exc))
        raise GitHubServiceError(f"RAG subsystem is unavailable for indexing: {reason}") from None

    collections: dict[str, int] = {}
    indexed_chunks = 0
    embedder = pipeline.used_embedder
    store = pipeline.used_vector_store

    for domain, chunks in ((REPOSITORY_DOCS, doc_chunks), (REPOSITORY_CODE, code_chunks)):
        if not chunks:
            continue
        summary = await pipeline.index_documents(domain, chunks)
        written = int(summary.get("indexed_chunks", 0))
        if written:
            collections[domain] = written
            indexed_chunks += written
        embedder = str(summary.get("embedder", embedder))
        store = str(summary.get("store", store))

    return {
        "repo": repo_id,
        "indexed_chunks": indexed_chunks,
        "collections": collections,
        "files_indexed": {"readme": readme_indexed, "python": len(python_paths)},
        "embedder": embedder,
        "store": store,
    }


__all__ = [
    "GitHubServiceError",
    "get_repo",
    "list_issues",
    "list_pulls",
    "list_commits",
    "list_releases",
    "rate_limit",
    "index_repo",
    "health_label",
]
