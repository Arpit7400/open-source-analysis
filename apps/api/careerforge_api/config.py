"""Runtime configuration for the CareerForge AI backend.

Configuration is sourced (in precedence order) from:

1. Explicit keyword arguments (mainly for tests).
2. Environment variables.
3. A ``.env`` file located next to the ``apps/api`` project root.
4. The sane defaults declared below.

The defaults are chosen so the whole flagship demo boots with **just Python +
Node**, no Docker, no Ollama, and no external services — see ``APP_ENV`` /
``demo`` mode described in ``docs/API_CONTRACT.md``.

Everything here is cross-platform: paths are resolved with :mod:`pathlib` and
no shell/OS-specific behaviour is assumed.
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# The project root for the API app (the directory that contains ``pyproject.toml``).
# ``config.py`` lives at ``apps/api/careerforge_api/config.py`` → parents[1] is ``apps/api``.
API_ROOT: Path = Path(__file__).resolve().parents[1]

# ``.env`` is looked up at the API project root so the demo works from any CWD.
ENV_FILE: Path = API_ROOT / ".env"


class AppEnv(str, Enum):
    """Deployment/runtime mode for the backend.

    ``DEMO`` is the default and runs a scripted, realistic mission simulation
    so the full flow is live without Docker/Ollama.
    """

    DEMO = "demo"
    LOCAL = "local"
    PRODUCTION = "production"


class Flags(BaseSettings):
    """Feature flags that gate side-effecting behaviour.

    Both default to ``False``: the platform never writes to GitHub and never
    executes untrusted repository code unless explicitly enabled by an operator.
    Mirrors the ``flags`` object in ``GET /api/v1/system/health``.
    """

    model_config = SettingsConfigDict(
        env_prefix="CAREERFORGE_FLAG_",
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    github_writes: bool = False
    repository_execution: bool = False


class Settings(BaseSettings):
    """Top-level application settings.

    Read from environment variables (prefix ``CAREERFORGE_``) and the ``.env``
    file. Service URLs default to conventional localhost ports so a developer
    can flip ``APP_ENV`` to ``local`` and point at real services without code
    changes.
    """

    model_config = SettingsConfigDict(
        env_prefix="CAREERFORGE_",
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Core ---------------------------------------------------------------
    app_env: AppEnv = Field(
        default=AppEnv.DEMO,
        description="Runtime mode. 'demo' runs the scripted simulation with no external deps.",
    )
    app_name: str = Field(default="CareerForge AI")
    version: str = Field(default="1.0.0")

    # --- HTTP server --------------------------------------------------------
    host: str = Field(default="127.0.0.1")
    port: int = Field(default=8000, ge=1, le=65535)
    api_prefix: str = Field(default="/api/v1")

    # CORS origins for the Next.js dev server (and any additional operators).
    # ``NoDecode`` disables pydantic-settings' automatic JSON decoding so the
    # ``field_validator`` below can accept a plain comma-separated env string.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
    )

    # --- External service URLs (only used when APP_ENV != demo) -------------
    database_url: str = Field(
        default="postgresql+asyncpg://careerforge:careerforge@localhost:5432/careerforge",
        description="SQLAlchemy/async database DSN.",
    )
    qdrant_url: str = Field(default="http://localhost:6333")
    redis_url: str = Field(default="redis://localhost:6379/0")
    ollama_url: str = Field(default="http://localhost:11434")
    temporal_url: str = Field(default="localhost:7233")

    # --- Agent orchestration ------------------------------------------------
    max_agent_concurrency: int = Field(
        default=4,
        ge=1,
        le=64,
        description="Maximum number of agents allowed to run concurrently.",
    )

    # --- Feature flags ------------------------------------------------------
    flags: Flags = Field(default_factory=Flags)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        """Allow ``CAREERFORGE_CORS_ORIGINS`` as a comma-separated string.

        pydantic-settings would otherwise try to JSON-decode a bare string for a
        ``list[str]`` field, which breaks the common ``a,b,c`` env-var idiom.
        """
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                # Leave JSON array strings for pydantic's normal parsing.
                return value
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return value

    @property
    def is_demo(self) -> bool:
        """True when running the scripted, dependency-free demo simulation."""
        return self.app_env is AppEnv.DEMO


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance.

    Cached so the ``.env`` file and environment are read once per process.
    Use ``get_settings.cache_clear()`` in tests to force a re-read.
    """
    return Settings()
