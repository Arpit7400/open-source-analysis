"""Console entrypoint: ``python -m careerforge_api``.

Boots the FastAPI app with uvicorn on ``:8000`` (host/port overridable via
settings / environment). Cross-platform: pure-Python, no shell assumptions,
no Docker or external services required in demo mode.

Examples
--------
    python -m careerforge_api                # serve on 127.0.0.1:8000
    CAREERFORGE_PORT=9000 python -m careerforge_api
"""

from __future__ import annotations

from typing import Any


def _resolve_host_port() -> tuple[str, int]:
    """Read host/port from Settings when available, else use safe defaults."""
    host, port = "127.0.0.1", 8000
    try:
        from careerforge_api.config import get_settings

        settings = get_settings()
        host = str(getattr(settings, "host", host))
        port = int(getattr(settings, "port", port))
    except Exception:
        pass
    return host, port


def main() -> None:
    """Run the ASGI server."""
    import uvicorn

    host, port = _resolve_host_port()

    # Report a short banner so the operator knows what booted.
    try:
        from careerforge_api.main import app_info

        info: dict[str, Any] = app_info()
        print(
            "CareerForge AI API "
            f"v{info.get('version')} "
            f"[{info.get('app_env')}] "
            f"profile={info.get('hardware_profile')} "
            f"python={info.get('python')} "
            f"platform={info.get('platform')}"
        )
    except Exception:
        pass

    print(f"Serving on http://{host}:{port}  (docs: /docs, API base: /api/v1)")

    # Import string form enables uvicorn reload support if ever desired; we
    # pass the app object directly for a dependency-light, cross-platform boot.
    uvicorn.run(
        "careerforge_api.main:app",
        host=host,
        port=port,
        log_level="info",
        reload=False,
    )


if __name__ == "__main__":
    main()
