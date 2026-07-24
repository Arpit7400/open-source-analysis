"""Async, read-only GitHub REST client.

:class:`GitHubClient` is a thin, typed wrapper over :mod:`httpx` that talks to
the GitHub REST API and returns the Pydantic models in :mod:`github_client.models`.

Design guarantees (from ``docs/GITHUB_CONTRACT.md``):

* **Read-only.** Every request is a ``GET``. A transport-level guard
  (:class:`_ReadOnlyTransport`) inspects the outgoing method and raises
  :class:`ReadOnlyViolation` for anything else, so even a future bug that tries
  to write is stopped before a byte leaves the process. No write helpers exist.
* **Token-safe.** The optional PAT is read from :class:`GithubSettings`
  (``CAREERFORGE_GITHUB_TOKEN``) via ``SecretStr`` and only ever placed in the
  ``Authorization`` request header. It is *never* logged, never included in an
  exception message, never returned in a payload, and never in ``repr`` — every
  string that could conceivably contain it is passed through :func:`redact`.
* **Graceful + typed.** ``404`` becomes ``None`` where the contract says
  ``| None``; a ``403``/``429`` rate-limit raises :class:`RateLimitError` with
  the reset time (no token); transport failures raise :class:`GitHubClientError`.

Everything is cross-platform (:mod:`pathlib` for any path handling) and the
client is an async context manager (``async with GitHubClient() as gh: ...``).
"""

from __future__ import annotations

import base64
import binascii
import logging
from datetime import UTC, datetime
from types import TracebackType
from urllib.parse import quote

import httpx

from github_client.config import GithubSettings, get_github_settings
from github_client.models import (
    CommitRef,
    ContentFile,
    IssueRef,
    PullRef,
    RateLimit,
    ReleaseRef,
    RepoMeta,
)
from github_client.redact import redact

logger = logging.getLogger("github_client.client")

#: The only HTTP method this client is permitted to send.
_ALLOWED_METHOD = "GET"

#: Media type requested on every call (stable v3 JSON).
_ACCEPT = "application/vnd.github+json"

#: GitHub API version pin (per GitHub's REST versioning guidance).
_API_VERSION = "2022-11-28"


# --------------------------------------------------------------------------- #
# Errors                                                                       #
# --------------------------------------------------------------------------- #
class GitHubClientError(RuntimeError):
    """Base error for the GitHub client.

    The message is always redacted before it reaches this constructor, so a
    ``GitHubClientError`` can be logged or surfaced verbatim without leaking a
    credential.
    """


class ReadOnlyViolation(GitHubClientError):
    """Raised when any non-``GET`` request is attempted.

    This is the enforcement point for the read-only contract; it fires at the
    transport layer before the request is dispatched.
    """


class RateLimitError(GitHubClientError):
    """Raised on a ``403``/``429`` that is a GitHub rate-limit rejection.

    Carries the parsed :attr:`reset_at` (when the limit resets) and
    :attr:`remaining` so callers can back off. The message never contains the
    token.
    """

    def __init__(
        self,
        message: str,
        *,
        reset_at: datetime | None = None,
        remaining: int | None = None,
    ) -> None:
        super().__init__(message)
        self.reset_at = reset_at
        self.remaining = remaining


# --------------------------------------------------------------------------- #
# Read-only transport guard                                                    #
# --------------------------------------------------------------------------- #
class _ReadOnlyTransport(httpx.AsyncBaseTransport):
    """Wrapping transport that rejects any method other than ``GET``.

    Delegates to an inner :class:`httpx.AsyncBaseTransport` (a real
    :class:`httpx.AsyncHTTPTransport` in production, or a
    :class:`httpx.MockTransport` in hermetic tests) only after confirming the
    method is ``GET`` — so the guard holds regardless of how the client is wired.
    """

    def __init__(self, inner: httpx.AsyncBaseTransport) -> None:
        self._inner = inner

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.method.upper() != _ALLOWED_METHOD:
            # Redact the URL defensively (it could carry an ?access_token=).
            raise ReadOnlyViolation(
                f"Read-only client refused a {request.method} request to "
                f"{redact(str(request.url))}. Only GET is permitted."
            )
        return await self._inner.handle_async_request(request)

    async def aclose(self) -> None:
        await self._inner.aclose()


# --------------------------------------------------------------------------- #
# URL parsing helper                                                           #
# --------------------------------------------------------------------------- #
def parse_repo_url(url: str) -> tuple[str, str]:
    """Parse ``url`` into ``(owner, name)``.

    Accepts the common spellings::

        https://github.com/owner/name
        https://github.com/owner/name.git
        git@github.com:owner/name.git
        ssh://git@github.com/owner/name.git
        owner/name

    Trailing ``.git``, surrounding whitespace, and a trailing slash are
    tolerated. Raises :class:`ValueError` when no ``owner/name`` pair can be
    recovered.
    """
    if not isinstance(url, str) or not url.strip():
        raise ValueError("Repository URL/spec must be a non-empty string.")

    spec = url.strip()

    if "://" in spec:
        # URL form (https/ssh/git): drop the scheme and the host, keep the path.
        after_scheme = spec.split("://", 1)[1]
        spec = after_scheme.split("/", 1)[1] if "/" in after_scheme else ""
    elif ":" in spec and not spec.split(":", 1)[0].isdigit():
        # scp-like SSH form: [user@]host:owner/name(.git). Take the part after
        # the first colon (the host, not a port, since there's no scheme).
        spec = spec.split(":", 1)[1]

    # Strip a leading github.com/ if it survived (e.g. bare "github.com/o/n").
    if spec.startswith("github.com/"):
        spec = spec[len("github.com/") :]

    spec = spec.strip("/")
    if spec.endswith(".git"):
        spec = spec[: -len(".git")]

    parts = [p for p in spec.split("/") if p]
    if len(parts) < 2:
        raise ValueError(f"Could not parse owner/name from repository spec: {url!r}")
    owner, name = parts[0], parts[1]
    return owner, name


# --------------------------------------------------------------------------- #
# Client                                                                       #
# --------------------------------------------------------------------------- #
class GitHubClient:
    """Async, read-only GitHub REST client.

    Construct with default settings (``GitHubClient()``), an explicit
    :class:`GithubSettings`, or — for hermetic tests — an injected
    ``transport`` (typically :class:`httpx.MockTransport`). The injected
    transport is wrapped in the read-only guard just like the production one, so
    tests exercise the exact enforcement path.
    """

    def __init__(
        self,
        settings: GithubSettings | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings or get_github_settings()
        inner = transport if transport is not None else httpx.AsyncHTTPTransport()
        self._client = httpx.AsyncClient(
            base_url=self._settings.github_api_url.rstrip("/"),
            transport=_ReadOnlyTransport(inner),
            headers=self._build_headers(),
            timeout=self._settings.github_timeout,
            follow_redirects=True,
        )

    def _build_headers(self) -> dict[str, str]:
        """Assemble static request headers, adding auth only when a token is set."""
        headers = {
            "Accept": _ACCEPT,
            "X-GitHub-Api-Version": _API_VERSION,
            "User-Agent": "careerforge-github-client",
        }
        if self._settings.is_authenticated:
            token = self._settings.github_token.get_secret_value()
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def __repr__(self) -> str:
        """Repr that reveals config *shape* but never the token."""
        return (
            f"GitHubClient(api_url={self._settings.github_api_url!r}, "
            f"authenticated={self._settings.is_authenticated})"
        )

    # -- lifecycle -----------------------------------------------------------

    async def __aenter__(self) -> GitHubClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the underlying HTTP client (and its transport)."""
        await self._client.aclose()

    # -- low-level request ---------------------------------------------------

    async def _get(
        self, path: str, *, params: dict[str, str | int | None] | None = None
    ) -> httpx.Response:
        """Perform a guarded GET, translating transport failures.

        Rate-limit (``403``/``429`` with the GitHub markers) → :class:`RateLimitError`.
        Any transport/protocol error → :class:`GitHubClientError`. All messages
        are redacted so a token can never surface via an exception.
        """
        try:
            response = await self._client.get(path, params=params)
        except ReadOnlyViolation:
            raise
        except httpx.HTTPError as exc:
            raise GitHubClientError(
                f"GitHub request failed: {redact(str(exc))}"
            ) from None
        if response.status_code in (403, 429) and self._is_rate_limited(response):
            raise self._rate_limit_error(response)
        return response

    @staticmethod
    def _is_rate_limited(response: httpx.Response) -> bool:
        """True when a 403/429 is a rate-limit rejection (not a plain auth 403)."""
        remaining = response.headers.get("x-ratelimit-remaining")
        if remaining is not None and remaining.strip() == "0":
            return True
        if response.headers.get("retry-after") is not None:
            return True
        # Fall back to the documented message body markers.
        try:
            body = response.json()
        except (ValueError, httpx.HTTPError):
            return False
        message = body.get("message", "") if isinstance(body, dict) else ""
        return isinstance(message, str) and "rate limit" in message.lower()

    @staticmethod
    def _rate_limit_error(response: httpx.Response) -> RateLimitError:
        """Build a token-free :class:`RateLimitError` from response headers."""
        reset_at: datetime | None = None
        reset_raw = response.headers.get("x-ratelimit-reset")
        if reset_raw is not None:
            try:
                reset_at = datetime.fromtimestamp(int(reset_raw), tz=UTC)
            except (ValueError, OverflowError, OSError):
                reset_at = None
        remaining: int | None = None
        remaining_raw = response.headers.get("x-ratelimit-remaining")
        if remaining_raw is not None:
            try:
                remaining = int(remaining_raw)
            except ValueError:
                remaining = None
        when = reset_at.isoformat() if reset_at is not None else "an unknown time"
        return RateLimitError(
            f"GitHub API rate limit exceeded; resets at {when}.",
            reset_at=reset_at,
            remaining=remaining,
        )

    def _raise_for_status(self, response: httpx.Response, context: str) -> None:
        """Raise a redacted :class:`GitHubClientError` for a non-2xx response."""
        if response.is_success:
            return
        detail = ""
        try:
            body = response.json()
            if isinstance(body, dict) and isinstance(body.get("message"), str):
                detail = f" ({body['message']})"
        except (ValueError, httpx.HTTPError):
            detail = ""
        raise GitHubClientError(
            redact(f"{context} failed with HTTP {response.status_code}{detail}.")
        )

    @staticmethod
    def _repo_path(owner: str, name: str, suffix: str = "") -> str:
        """Build a ``/repos/{owner}/{name}{suffix}`` path with URL-safe segments."""
        base = f"/repos/{quote(owner, safe='')}/{quote(name, safe='')}"
        return f"{base}{suffix}"

    # -- repository ----------------------------------------------------------

    async def get_repo(self, owner: str, name: str) -> RepoMeta:
        """Return :class:`RepoMeta` for ``owner/name`` (languages + tests hint included)."""
        response = await self._get(self._repo_path(owner, name))
        self._raise_for_status(response, f"get_repo({owner}/{name})")
        data = response.json()

        languages = await self.get_languages(owner, name)
        has_tests_hint = await self._detect_tests_hint(
            owner, name, data.get("default_branch")
        )
        return RepoMeta.from_api(
            data, languages=languages, has_tests_hint=has_tests_hint
        )

    async def get_languages(self, owner: str, name: str) -> dict[str, int]:
        """Return the language → bytes map (``GET /repos/{o}/{n}/languages``)."""
        response = await self._get(self._repo_path(owner, name, "/languages"))
        self._raise_for_status(response, f"get_languages({owner}/{name})")
        data = response.json()
        if not isinstance(data, dict):
            return {}
        return {str(k): int(v) for k, v in data.items() if isinstance(v, (int, float))}

    async def _detect_tests_hint(
        self, owner: str, name: str, default_branch: str | None
    ) -> bool:
        """Heuristic: does the repo tree contain a tests dir / test file?

        Best-effort — any failure (rate limit surfaced separately) yields
        ``False`` rather than breaking ``get_repo``.
        """
        branch = default_branch or "HEAD"
        try:
            paths = await self.list_tree_paths(owner, name, ref=branch)
        except RateLimitError:
            raise
        except GitHubClientError:
            return False
        for path in paths:
            lowered = path.lower()
            leaf = lowered.rsplit("/", 1)[-1]
            if (
                lowered.startswith("tests/")
                or lowered.startswith("test/")
                or "/tests/" in lowered
                or "/test/" in lowered
                or leaf.startswith("test_")
                or leaf.endswith("_test.py")
                or leaf == "conftest.py"
            ):
                return True
        return False

    # -- issues / pulls ------------------------------------------------------

    async def list_issues(
        self, owner: str, name: str, state: str = "open", limit: int = 30
    ) -> list[IssueRef]:
        """List issues, **excluding** pull requests (they lack ``pull_request``)."""
        response = await self._get(
            self._repo_path(owner, name, "/issues"),
            params={"state": state, "per_page": _clamp_per_page(limit)},
        )
        self._raise_for_status(response, f"list_issues({owner}/{name})")
        data = response.json()
        items = data if isinstance(data, list) else []
        issues: list[IssueRef] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            if "pull_request" in item:  # exclude PRs surfaced by the issues API
                continue
            issues.append(IssueRef.from_api(item))
            if len(issues) >= limit:
                break
        return issues

    async def list_pulls(
        self, owner: str, name: str, state: str = "open", limit: int = 30
    ) -> list[PullRef]:
        """List pull requests (``GET /repos/{o}/{n}/pulls``)."""
        response = await self._get(
            self._repo_path(owner, name, "/pulls"),
            params={"state": state, "per_page": _clamp_per_page(limit)},
        )
        self._raise_for_status(response, f"list_pulls({owner}/{name})")
        data = response.json()
        items = data if isinstance(data, list) else []
        pulls = [PullRef.from_api(i) for i in items if isinstance(i, dict)]
        return pulls[:limit]

    # -- commits / releases --------------------------------------------------

    async def list_commits(
        self, owner: str, name: str, limit: int = 30, sha: str | None = None
    ) -> list[CommitRef]:
        """List commits (``GET /repos/{o}/{n}/commits``), optionally from ``sha``."""
        params: dict[str, str | int | None] = {"per_page": _clamp_per_page(limit)}
        if sha:
            params["sha"] = sha
        response = await self._get(
            self._repo_path(owner, name, "/commits"), params=params
        )
        self._raise_for_status(response, f"list_commits({owner}/{name})")
        data = response.json()
        items = data if isinstance(data, list) else []
        commits = [CommitRef.from_api(i) for i in items if isinstance(i, dict)]
        return commits[:limit]

    async def list_releases(
        self, owner: str, name: str, limit: int = 10
    ) -> list[ReleaseRef]:
        """List releases (``GET /repos/{o}/{n}/releases``)."""
        response = await self._get(
            self._repo_path(owner, name, "/releases"),
            params={"per_page": _clamp_per_page(limit)},
        )
        self._raise_for_status(response, f"list_releases({owner}/{name})")
        data = response.json()
        items = data if isinstance(data, list) else []
        releases = [ReleaseRef.from_api(i) for i in items if isinstance(i, dict)]
        return releases[:limit]

    # -- contents ------------------------------------------------------------

    async def get_readme(self, owner: str, name: str) -> ContentFile | None:
        """Return the repo README as a :class:`ContentFile`, or ``None`` if absent."""
        response = await self._get(self._repo_path(owner, name, "/readme"))
        if response.status_code == 404:
            return None
        self._raise_for_status(response, f"get_readme({owner}/{name})")
        return self._content_file_from_api(response.json())

    async def get_file(
        self, owner: str, name: str, path: str, ref: str | None = None
    ) -> ContentFile | None:
        """Return the file at ``path`` as a :class:`ContentFile`, or ``None``.

        Returns ``None`` for a missing path (404) or when ``path`` resolves to a
        directory (the Contents API returns a JSON *array* in that case).
        """
        encoded_path = "/".join(quote(seg, safe="") for seg in path.split("/") if seg)
        params: dict[str, str | int | None] | None = {"ref": ref} if ref else None
        response = await self._get(
            self._repo_path(owner, name, f"/contents/{encoded_path}"),
            params=params,
        )
        if response.status_code == 404:
            return None
        self._raise_for_status(response, f"get_file({owner}/{name}:{path})")
        data = response.json()
        if not isinstance(data, dict):  # directory listing -> not a single file
            return None
        return self._content_file_from_api(data)

    @staticmethod
    def _content_file_from_api(data: dict[str, object]) -> ContentFile:
        """Build a :class:`ContentFile`, decoding base64 content to UTF-8 text."""
        encoding = str(data.get("encoding") or "")
        raw_content = data.get("content")
        text: str | None = None
        if encoding == "base64" and isinstance(raw_content, str):
            try:
                decoded = base64.b64decode(raw_content, validate=False)
                text = decoded.decode("utf-8")
            except (binascii.Error, ValueError, UnicodeDecodeError):
                text = None  # binary or malformed content -> no text
        return ContentFile(
            path=str(data.get("path") or ""),
            size=_as_int(data.get("size")),
            encoding=encoding,
            text=text,
            sha=str(data.get("sha") or ""),
            url=str(data.get("html_url") or data.get("url") or ""),
        )

    # -- trees ---------------------------------------------------------------

    async def list_tree_paths(
        self, owner: str, name: str, ref: str | None = None
    ) -> list[str]:
        """Return every blob path in the tree at ``ref`` (recursive).

        Uses ``GET /repos/{o}/{n}/git/trees/{ref}?recursive=1``. A missing ref
        (404) yields an empty list. This backs both :meth:`list_python_files`
        and the ``has_tests_hint`` heuristic.
        """
        sha = ref or "HEAD"
        response = await self._get(
            self._repo_path(owner, name, f"/git/trees/{quote(sha, safe='')}"),
            params={"recursive": "1"},
        )
        if response.status_code == 404:
            return []
        self._raise_for_status(response, f"list_tree_paths({owner}/{name}@{sha})")
        data = response.json()
        tree = data.get("tree") if isinstance(data, dict) else None
        if not isinstance(tree, list):
            return []
        paths: list[str] = []
        for entry in tree:
            if not isinstance(entry, dict) or entry.get("type") != "blob":
                continue
            entry_path = entry.get("path")
            if isinstance(entry_path, str):
                paths.append(entry_path)
        return paths

    async def list_python_files(
        self, owner: str, name: str, ref: str | None = None, limit: int = 200
    ) -> list[str]:
        """List up to ``limit`` ``.py`` file paths in the repo tree (recursive)."""
        paths = await self.list_tree_paths(owner, name, ref=ref)
        python_files = [p for p in paths if p.endswith(".py")]
        return python_files[: max(0, limit)]

    # -- rate limit ----------------------------------------------------------

    async def rate_limit(self) -> RateLimit:
        """Return the current core :class:`RateLimit` (``GET /rate_limit``)."""
        response = await self._get("/rate_limit")
        self._raise_for_status(response, "rate_limit()")
        return RateLimit.from_api(response.json())

    # -- search --------------------------------------------------------------

    async def search_issues(
        self, owner: str, name: str, query: str, limit: int = 20
    ) -> list[IssueRef]:
        """Search issues in ``owner/name`` (``GET /search/issues``).

        The free-text ``query`` is scoped to the repository automatically. Both
        issues and PRs may be returned; each carries its ``is_pull`` flag.
        """
        q = f"repo:{owner}/{name} {query}".strip()
        response = await self._get(
            "/search/issues",
            params={"q": q, "per_page": _clamp_per_page(limit)},
        )
        self._raise_for_status(response, f"search_issues({owner}/{name})")
        data = response.json()
        items = data.get("items") if isinstance(data, dict) else None
        items = items if isinstance(items, list) else []
        results = [IssueRef.from_api(i) for i in items if isinstance(i, dict)]
        return results[:limit]


def _clamp_per_page(limit: int) -> int:
    """Clamp a caller limit to GitHub's ``per_page`` bounds (1..100)."""
    return max(1, min(100, int(limit)))


def _as_int(value: object) -> int:
    """Coerce an untyped JSON value to ``int`` (0 when missing/non-numeric)."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value)
    return 0


__all__ = [
    "GitHubClient",
    "GitHubClientError",
    "ReadOnlyViolation",
    "RateLimitError",
    "parse_repo_url",
]
