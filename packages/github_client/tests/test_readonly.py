"""Read-only + no-secret-leak guarantees."""

from __future__ import annotations

import httpx
import pytest

from github_client import GitHubClient
from github_client.client import ReadOnlyViolation


@pytest.mark.asyncio
async def test_non_get_is_rejected(mock_transport: httpx.MockTransport) -> None:
    """Any non-GET request must be blocked at the transport guard."""
    client = GitHubClient(transport=mock_transport)
    try:
        for method in ("POST", "PATCH", "PUT", "DELETE"):
            with pytest.raises(ReadOnlyViolation):
                await client._client.request(method, "/repos/psf/requests")
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_get_is_allowed(mock_transport: httpx.MockTransport) -> None:
    client = GitHubClient(transport=mock_transport)
    try:
        resp = await client._client.get("/repos/psf/requests")
        assert resp.status_code == 200
    finally:
        await client.aclose()


def test_token_never_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    """A configured token must not appear in the client's repr."""
    monkeypatch.setenv("CAREERFORGE_GITHUB_TOKEN", "ghp_supersecrettokenvalue0123456789abcd")
    # Rebuild settings from env (cache-busted) and construct a client.
    from github_client.config import get_github_settings

    get_github_settings.cache_clear()
    client = GitHubClient()
    text = repr(client) + str(vars(client))
    assert "ghp_supersecret" not in text
    get_github_settings.cache_clear()


@pytest.mark.asyncio
async def test_token_not_in_error_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    """A transport failure must not surface the token in its message."""
    from github_client.client import GitHubClientError
    from github_client.config import get_github_settings

    monkeypatch.setenv("CAREERFORGE_GITHUB_TOKEN", "ghp_supersecrettokenvalue0123456789abcd")
    get_github_settings.cache_clear()

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection failed to ghp_supersecrettokenvalue0123456789abcd")

    client = GitHubClient(transport=httpx.MockTransport(boom))
    try:
        with pytest.raises(GitHubClientError) as exc:
            await client.get_repo("psf", "requests")
        assert "ghp_supersecret" not in str(exc.value)
    finally:
        await client.aclose()
        get_github_settings.cache_clear()
