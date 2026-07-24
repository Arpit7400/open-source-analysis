"""Shared hermetic fixtures: a fake GitHub served via ``httpx.MockTransport``.

No network is ever touched. The mock routes requests by path and returns canned
GitHub-shaped JSON, so the tests are deterministic and pass anywhere (macOS,
Windows, CI) regardless of TLS/proxy conditions.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Callable

import httpx
import pytest

_REPO = {
    "id": 1,
    "name": "requests",
    "full_name": "psf/requests",
    "owner": {"login": "psf"},
    "default_branch": "main",
    "description": "Python HTTP for Humans.",
    "language": "Python",
    "license": {"spdx_id": "Apache-2.0"},
    "stargazers_count": 52000,
    "forks_count": 9400,
    "open_issues_count": 200,
    "archived": False,
    "pushed_at": "2026-07-01T10:00:00Z",
    "topics": ["python", "http"],
    "html_url": "https://github.com/psf/requests",
}

_LANGUAGES = {"Python": 900000, "HTML": 1200}

# One real issue and one PR — the PR carries a ``pull_request`` key and MUST be
# excluded from list_issues().
_ISSUES = [
    {
        "number": 101,
        "title": "Timeout not honored on redirect",
        "state": "open",
        "user": {"login": "alice"},
        "created_at": "2026-06-01T00:00:00Z",
        "updated_at": "2026-06-02T00:00:00Z",
        "html_url": "https://github.com/psf/requests/issues/101",
        "labels": [{"name": "bug"}],
    },
    {
        "number": 102,
        "title": "Fix timeout handling",
        "state": "open",
        "user": {"login": "bob"},
        "created_at": "2026-06-03T00:00:00Z",
        "updated_at": "2026-06-03T00:00:00Z",
        "html_url": "https://github.com/psf/requests/pull/102",
        "labels": [],
        "pull_request": {"url": "https://api.github.com/repos/psf/requests/pulls/102"},
    },
]

_PULLS = [
    {
        "number": 102,
        "title": "Fix timeout handling",
        "state": "open",
        "user": {"login": "bob"},
        "created_at": "2026-06-03T00:00:00Z",
        "merged_at": None,
        "html_url": "https://github.com/psf/requests/pull/102",
        "base": {"ref": "main"},
        "head": {"ref": "fix-timeout"},
    }
]

_COMMITS = [
    {
        "sha": "abc123def456",
        "commit": {
            "message": "Fix redirect timeout",
            "author": {"name": "Alice", "date": "2026-06-01T12:00:00Z"},
        },
        "author": {"login": "alice"},
        "html_url": "https://github.com/psf/requests/commit/abc123def456",
    }
]

_RELEASES = [
    {
        "tag_name": "v2.32.0",
        "name": "2.32.0",
        "published_at": "2026-05-01T00:00:00Z",
        "prerelease": False,
        "html_url": "https://github.com/psf/requests/releases/tag/v2.32.0",
    }
]

_README = {
    "path": "README.md",
    "size": 42,
    "encoding": "base64",
    "content": base64.b64encode(b"# Requests\n\nPython HTTP for Humans.").decode(),
    "sha": "readmesha",
    "html_url": "https://github.com/psf/requests/blob/main/README.md",
}

_TREE = {
    "sha": "treesha",
    "truncated": False,
    "tree": [
        {"path": "requests/__init__.py", "type": "blob"},
        {"path": "requests/api.py", "type": "blob"},
        {"path": "tests/test_requests.py", "type": "blob"},
        {"path": "README.md", "type": "blob"},
        {"path": "docs", "type": "tree"},
    ],
}

_RATE_LIMIT = {
    "resources": {
        "core": {
            "limit": 5000,
            "remaining": 4990,
            "reset": 1893456000,
            "used": 10,
        }
    },
    "rate": {"limit": 5000, "remaining": 4990, "reset": 1893456000, "used": 10},
}


def _handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path

    def ok(payload: object) -> httpx.Response:
        return httpx.Response(200, content=json.dumps(payload), headers={"content-type": "application/json"})

    if path == "/repos/psf/requests":
        return ok(_REPO)
    if path == "/repos/psf/requests/languages":
        return ok(_LANGUAGES)
    if path == "/repos/psf/requests/issues":
        return ok(_ISSUES)
    if path == "/repos/psf/requests/pulls":
        return ok(_PULLS)
    if path == "/repos/psf/requests/commits":
        return ok(_COMMITS)
    if path == "/repos/psf/requests/releases":
        return ok(_RELEASES)
    if path == "/repos/psf/requests/readme":
        return ok(_README)
    if path.startswith("/repos/psf/requests/git/trees/"):
        return ok(_TREE)
    if path == "/rate_limit":
        return ok(_RATE_LIMIT)
    if path == "/repos/psf/ghost":  # missing repo
        return httpx.Response(404, content=json.dumps({"message": "Not Found"}))
    if path.startswith("/repos/psf/requests/contents/"):
        return ok(_README)  # reuse a content payload
    # default: 404 so unrouted paths are obvious
    return httpx.Response(404, content=json.dumps({"message": "Not Found", "path": path}))


@pytest.fixture
def mock_transport() -> httpx.MockTransport:
    """A MockTransport backed by the canned GitHub responses above."""
    return httpx.MockTransport(_handler)


@pytest.fixture
def handler() -> Callable[[httpx.Request], httpx.Response]:
    return _handler
