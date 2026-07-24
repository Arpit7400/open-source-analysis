"""Runtime configuration for the read-only GitHub client.

:class:`GithubSettings` reads the ``CAREERFORGE_`` environment prefix (matching
``apps/api/careerforge_api/config.py`` and ``packages/rag_core``) so a single
``.env`` configures the whole platform. Exactly three keys are consumed:

* ``CAREERFORGE_GITHUB_TOKEN`` — an *optional* fine-grained **read-only** PAT.
  Stored as a :class:`pydantic.SecretStr` so it never leaks through ``repr``,
  logs, or serialisation. Defaults to empty → the client works unauthenticated
  (subject to GitHub's lower anonymous rate limit).
* ``CAREERFORGE_GITHUB_API_URL`` — the API base URL (default
  ``https://api.github.com``; override for GitHub Enterprise).
* ``CAREERFORGE_GITHUB_TIMEOUT`` — per-request timeout in seconds.

Everything is cross-platform: no shell/OS-specific behaviour is assumed.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class GithubSettings(BaseSettings):
    """GitHub client settings (env prefix ``CAREERFORGE_``).

    Field names map to env vars by upper-casing and prefixing, e.g.
    ``github_token`` → ``CAREERFORGE_GITHUB_TOKEN``.
    """

    model_config = SettingsConfigDict(
        env_prefix="CAREERFORGE_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    #: Optional read-only PAT. Empty (default) → unauthenticated requests.
    #: A ``SecretStr`` so the value is masked in ``repr``/logs/serialisation.
    github_token: SecretStr = Field(default=SecretStr(""))

    #: Base API URL. Override for GitHub Enterprise.
    github_api_url: str = Field(default="https://api.github.com")

    #: Per-request timeout in seconds.
    github_timeout: float = Field(default=30.0, gt=0.0)

    @property
    def is_authenticated(self) -> bool:
        """True when a non-empty token is configured.

        Reads through ``SecretStr.get_secret_value`` only to test emptiness; the
        raw value is never returned or logged here.
        """
        return bool(self.github_token.get_secret_value().strip())


@lru_cache(maxsize=1)
def get_github_settings() -> GithubSettings:
    """Return a cached :class:`GithubSettings` instance.

    Cached so the ``.env`` file and environment are read once per process. Use
    ``get_github_settings.cache_clear()`` in tests to force a re-read.
    """
    return GithubSettings()


__all__ = [
    "GithubSettings",
    "get_github_settings",
]
