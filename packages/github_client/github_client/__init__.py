"""Real, typed, read-only GitHub client for CareerForge AI.

Public surface (see ``docs/GITHUB_CONTRACT.md``):

* :class:`GitHubClient` — async, read-only REST client (only GET; a transport
  guard raises :class:`ReadOnlyViolation` on any other method).
* :class:`GithubSettings` / :func:`get_github_settings` — ``CAREERFORGE_``-prefixed
  config (optional ``SecretStr`` token, api url, timeout).
* :func:`parse_repo_url` — parse ``owner/name`` from https/ssh/``owner/name``.
* :func:`redact` — strip tokens / auth headers / ``access_token`` params from
  any string.
* Error types :class:`GitHubClientError`, :class:`ReadOnlyViolation`,
  :class:`RateLimitError`.
* All Pydantic v2 models: :class:`RepoMeta`, :class:`IssueRef`, :class:`PullRef`,
  :class:`CommitRef`, :class:`ReleaseRef`, :class:`ContentFile`,
  :class:`RateLimit`.

The token is never logged, never placed in an error/repr/payload.
"""

from __future__ import annotations

from github_client.client import (
    GitHubClient,
    GitHubClientError,
    RateLimitError,
    ReadOnlyViolation,
    parse_repo_url,
)
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

__all__ = [
    # client + errors
    "GitHubClient",
    "GitHubClientError",
    "ReadOnlyViolation",
    "RateLimitError",
    "parse_repo_url",
    # config
    "GithubSettings",
    "get_github_settings",
    # redaction
    "redact",
    # models
    "RepoMeta",
    "IssueRef",
    "PullRef",
    "CommitRef",
    "ReleaseRef",
    "ContentFile",
    "RateLimit",
]
