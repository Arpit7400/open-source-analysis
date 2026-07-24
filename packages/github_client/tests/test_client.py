"""Client parsing tests over a hermetic MockTransport (no network)."""

from __future__ import annotations

import httpx
import pytest

from github_client import GitHubClient, parse_repo_url


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://github.com/psf/requests", ("psf", "requests")),
        ("https://github.com/psf/requests.git", ("psf", "requests")),
        ("git@github.com:psf/requests.git", ("psf", "requests")),
        ("psf/requests", ("psf", "requests")),
        ("https://github.com/psf/requests/", ("psf", "requests")),
    ],
)
def test_parse_repo_url(url: str, expected: tuple[str, str]) -> None:
    assert parse_repo_url(url) == expected


@pytest.mark.asyncio
async def test_get_repo(mock_transport: httpx.MockTransport) -> None:
    client = GitHubClient(transport=mock_transport)
    try:
        repo = await client.get_repo("psf", "requests")
    finally:
        await client.aclose()
    assert repo.full_name == "psf/requests"
    assert repo.owner == "psf"
    assert repo.name == "requests"
    assert repo.default_branch == "main"
    assert repo.language == "Python"
    assert repo.license_spdx == "Apache-2.0"
    assert repo.stargazers == 52000
    assert repo.languages == {"Python": 900000, "HTML": 1200}
    # tests hint should be True — the tree contains tests/test_requests.py
    assert repo.has_tests_hint is True


@pytest.mark.asyncio
async def test_list_issues_excludes_pulls(mock_transport: httpx.MockTransport) -> None:
    client = GitHubClient(transport=mock_transport)
    try:
        issues = await client.list_issues("psf", "requests")
    finally:
        await client.aclose()
    numbers = [i.number for i in issues]
    assert 101 in numbers
    assert 102 not in numbers, "PRs (items with pull_request) must be excluded from issues"
    assert all(i.is_pull is False for i in issues)
    assert issues[0].labels == ["bug"]


@pytest.mark.asyncio
async def test_list_pulls_and_commits(mock_transport: httpx.MockTransport) -> None:
    client = GitHubClient(transport=mock_transport)
    try:
        pulls = await client.list_pulls("psf", "requests")
        commits = await client.list_commits("psf", "requests")
    finally:
        await client.aclose()
    assert pulls[0].number == 102
    assert pulls[0].merged is False
    assert commits[0].sha == "abc123def456"
    assert "redirect timeout" in commits[0].message.lower()


@pytest.mark.asyncio
async def test_get_readme_decodes_base64(mock_transport: httpx.MockTransport) -> None:
    client = GitHubClient(transport=mock_transport)
    try:
        readme = await client.get_readme("psf", "requests")
    finally:
        await client.aclose()
    assert readme is not None
    assert readme.path == "README.md"
    assert readme.text is not None
    assert "Python HTTP for Humans." in readme.text


@pytest.mark.asyncio
async def test_list_python_files(mock_transport: httpx.MockTransport) -> None:
    client = GitHubClient(transport=mock_transport)
    try:
        files = await client.list_python_files("psf", "requests")
    finally:
        await client.aclose()
    assert "requests/api.py" in files
    assert "tests/test_requests.py" in files
    assert "README.md" not in files


@pytest.mark.asyncio
async def test_rate_limit(mock_transport: httpx.MockTransport) -> None:
    client = GitHubClient(transport=mock_transport)
    try:
        rl = await client.rate_limit()
    finally:
        await client.aclose()
    assert rl.limit == 5000
    assert rl.remaining == 4990
    assert rl.used == 10


@pytest.mark.asyncio
async def test_missing_repo_returns_error_or_none(mock_transport: httpx.MockTransport) -> None:
    from github_client.client import GitHubClientError

    client = GitHubClient(transport=mock_transport)
    try:
        with pytest.raises(GitHubClientError):
            await client.get_repo("psf", "ghost")
    finally:
        await client.aclose()
