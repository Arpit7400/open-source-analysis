"""Typed GitHub domain models (Pydantic v2).

These mirror ``docs/GITHUB_CONTRACT.md`` § *Models* **exactly** — field names,
optionality, and types. They are intentionally thin projections of GitHub's REST
responses: only the fields CareerForge needs are kept, and none of them can ever
carry a credential (the client never persists auth material into a payload).

Each model exposes a ``from_api`` classmethod that maps a raw GitHub JSON object
(a ``dict``) onto the typed shape, tolerating GitHub's ``null`` fields and nested
objects (e.g. ``owner.login`` for the author, ``license.spdx_id``). The mapping
is total and defensive so a slightly-unexpected payload degrades to ``None``
rather than raising deep in parsing.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def _get(data: dict[str, Any], key: str) -> Any:
    """Return ``data[key]`` or ``None`` — never raise on a missing key."""
    return data.get(key)


def _login(obj: Any) -> str | None:
    """Extract a ``login`` from a GitHub user sub-object (``author``/``owner``)."""
    if isinstance(obj, dict):
        login = obj.get("login")
        return login if isinstance(login, str) else None
    return None


class RepoMeta(BaseModel):
    """Repository metadata (projection of ``GET /repos/{owner}/{name}``)."""

    model_config = ConfigDict(extra="ignore")

    owner: str
    name: str
    full_name: str
    default_branch: str
    description: str | None = None
    language: str | None = None
    languages: dict[str, int] = Field(default_factory=dict)
    license_spdx: str | None = None
    stargazers: int = 0
    forks: int = 0
    open_issues: int = 0
    archived: bool = False
    pushed_at: datetime | None = None
    has_tests_hint: bool = False
    topics: list[str] = Field(default_factory=list)
    html_url: str

    @classmethod
    def from_api(
        cls,
        data: dict[str, Any],
        *,
        languages: dict[str, int] | None = None,
        has_tests_hint: bool = False,
    ) -> RepoMeta:
        """Build a :class:`RepoMeta` from a repo JSON object.

        ``languages`` (from ``GET /repos/{o}/{n}/languages``) and
        ``has_tests_hint`` (derived by the client from the repo tree) are passed
        in because they are separate API calls / heuristics.
        """
        owner_obj = _get(data, "owner")
        owner = _login(owner_obj) or ""
        license_obj = _get(data, "license")
        license_spdx = (
            license_obj.get("spdx_id") if isinstance(license_obj, dict) else None
        )
        if license_spdx in (None, "", "NOASSERTION"):
            license_spdx = None
        topics = _get(data, "topics")
        return cls(
            owner=owner,
            name=_get(data, "name") or "",
            full_name=_get(data, "full_name") or "",
            default_branch=_get(data, "default_branch") or "main",
            description=_get(data, "description"),
            language=_get(data, "language"),
            languages=dict(languages) if languages else {},
            license_spdx=license_spdx,
            stargazers=int(_get(data, "stargazers_count") or 0),
            forks=int(_get(data, "forks_count") or 0),
            open_issues=int(_get(data, "open_issues_count") or 0),
            archived=bool(_get(data, "archived") or False),
            pushed_at=_get(data, "pushed_at"),
            has_tests_hint=has_tests_hint,
            topics=[t for t in topics if isinstance(t, str)]
            if isinstance(topics, list)
            else [],
            html_url=_get(data, "html_url") or "",
        )


class IssueRef(BaseModel):
    """A single issue (or, when ``is_pull`` is true, a pull request stub).

    ``list_issues`` filters PRs out; ``search_issues`` may surface either, so the
    ``is_pull`` flag is always populated from the presence of ``pull_request``.
    """

    model_config = ConfigDict(extra="ignore")

    number: int
    title: str
    state: str
    author: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    url: str
    is_pull: bool = False
    labels: list[str] = Field(default_factory=list)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> IssueRef:
        """Build an :class:`IssueRef` from an issue/search JSON object."""
        raw_labels = _get(data, "labels")
        labels: list[str] = []
        if isinstance(raw_labels, list):
            for label in raw_labels:
                if isinstance(label, str):
                    labels.append(label)
                elif isinstance(label, dict):
                    name = label.get("name")
                    if isinstance(name, str):
                        labels.append(name)
        return cls(
            number=int(_get(data, "number") or 0),
            title=_get(data, "title") or "",
            state=_get(data, "state") or "",
            author=_login(_get(data, "user")),
            created_at=_get(data, "created_at"),
            updated_at=_get(data, "updated_at"),
            url=_get(data, "html_url") or "",
            is_pull="pull_request" in data,
            labels=labels,
        )


class PullRef(BaseModel):
    """A pull request (projection of ``GET /repos/{o}/{n}/pulls``)."""

    model_config = ConfigDict(extra="ignore")

    number: int
    title: str
    state: str
    author: str | None = None
    created_at: datetime | None = None
    merged: bool = False
    url: str
    base: str
    head: str

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> PullRef:
        """Build a :class:`PullRef` from a pull-request JSON object."""

        def _ref(obj: Any) -> str:
            if isinstance(obj, dict):
                ref = obj.get("ref")
                return ref if isinstance(ref, str) else ""
            return ""

        merged = bool(_get(data, "merged") or _get(data, "merged_at"))
        return cls(
            number=int(_get(data, "number") or 0),
            title=_get(data, "title") or "",
            state=_get(data, "state") or "",
            author=_login(_get(data, "user")),
            created_at=_get(data, "created_at"),
            merged=merged,
            url=_get(data, "html_url") or "",
            base=_ref(_get(data, "base")),
            head=_ref(_get(data, "head")),
        )


class CommitRef(BaseModel):
    """A commit (projection of ``GET /repos/{o}/{n}/commits``)."""

    model_config = ConfigDict(extra="ignore")

    sha: str
    message: str
    author: str | None = None
    date: datetime | None = None
    url: str

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> CommitRef:
        """Build a :class:`CommitRef` from a commit JSON object.

        Prefers the GitHub *account* login (``author.login``) and falls back to
        the git commit author name (``commit.author.name``); the date comes from
        the git author metadata.
        """
        commit_obj = _get(data, "commit")
        commit_obj = commit_obj if isinstance(commit_obj, dict) else {}
        git_author = commit_obj.get("author")
        git_author = git_author if isinstance(git_author, dict) else {}

        author = _login(_get(data, "author"))
        if author is None:
            name = git_author.get("name")
            author = name if isinstance(name, str) else None

        date = git_author.get("date")
        return cls(
            sha=_get(data, "sha") or "",
            message=commit_obj.get("message") or "",
            author=author,
            date=date,
            url=_get(data, "html_url") or "",
        )


class ReleaseRef(BaseModel):
    """A release (projection of ``GET /repos/{o}/{n}/releases``)."""

    model_config = ConfigDict(extra="ignore")

    tag: str
    name: str | None = None
    published_at: datetime | None = None
    prerelease: bool = False
    url: str

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> ReleaseRef:
        """Build a :class:`ReleaseRef` from a release JSON object."""
        return cls(
            tag=_get(data, "tag_name") or "",
            name=_get(data, "name"),
            published_at=_get(data, "published_at"),
            prerelease=bool(_get(data, "prerelease") or False),
            url=_get(data, "html_url") or "",
        )


class ContentFile(BaseModel):
    """A file's contents (projection of the Contents API / README endpoint).

    ``text`` holds the decoded UTF-8 body when the content was base64-encoded and
    decodable; it is ``None`` for binary or otherwise undecodable content.
    """

    model_config = ConfigDict(extra="ignore")

    path: str
    size: int = 0
    encoding: str
    text: str | None = None
    sha: str
    url: str


class RateLimit(BaseModel):
    """Rate-limit status (projection of ``GET /rate_limit`` core resource)."""

    model_config = ConfigDict(extra="ignore")

    limit: int
    remaining: int
    reset_at: datetime
    used: int = 0

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> RateLimit:
        """Build a :class:`RateLimit` from the ``resources.core`` object.

        Accepts either the full ``/rate_limit`` envelope (``{"resources": {...},
        "rate": {...}}``) or a bare core object. ``reset`` is an epoch second.
        """
        core: dict[str, Any]
        resources = _get(data, "resources")
        if isinstance(resources, dict) and isinstance(resources.get("core"), dict):
            core = resources["core"]
        elif isinstance(_get(data, "rate"), dict):
            core = data["rate"]
        else:
            core = data
        reset_epoch = int(core.get("reset") or 0)
        return cls(
            limit=int(core.get("limit") or 0),
            remaining=int(core.get("remaining") or 0),
            reset_at=datetime.fromtimestamp(reset_epoch, tz=UTC),
            used=int(core.get("used") or 0),
        )


__all__ = [
    "RepoMeta",
    "IssueRef",
    "PullRef",
    "CommitRef",
    "ReleaseRef",
    "ContentFile",
    "RateLimit",
]
