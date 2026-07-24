"""Adapter between the API and the real ``static_analysis`` package (Phase 5).

Runs the real static-analysis swarm (AST agents + ruff/mypy) over a local
repository path and returns the findings as plain dicts matching the API
contract. Degrades cleanly if the package cannot be imported.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("careerforge_api.analysis_service")

_import_failed_reason: str | None = None


def _load() -> Any | None:
    """Import ``static_analysis`` lazily; cache a failure reason on error."""
    global _import_failed_reason
    try:
        import static_analysis as _sa
    except Exception as exc:  # ImportError or transitive failure
        _import_failed_reason = f"static_analysis import failed: {exc}"
        logger.warning("Static analysis unavailable: %s", _import_failed_reason)
        return None
    return _sa


def health_label() -> str:
    """``services.static_analysis`` value: 'ready' | 'down'."""
    return "ready" if _load() is not None else "down"


def analyze(
    repo_path: str, repo_id: str | None = None, include_tools: bool = True
) -> dict[str, Any]:
    """Run the static-analysis swarm over ``repo_path`` and return a summary dict.

    Raises ``NotADirectoryError`` if the path is not a directory, or
    ``RuntimeError`` if the subsystem is unavailable.
    """
    module = _load()
    if module is None:
        raise RuntimeError(_import_failed_reason or "static_analysis is unavailable.")

    root = Path(repo_path).expanduser()
    if not root.is_dir():
        raise NotADirectoryError(f"repo_path is not a directory: {repo_path}")

    result = module.analyze_repository(root, repo_id=repo_id, include_tools=include_tools)
    findings = [f.model_dump(mode="json") for f in result.findings]
    agents = [
        {"agent_id": r.agent_id, "ok": r.ok, "finding_count": len(r.findings), "note": r.note}
        for r in result.reports
    ]
    return {
        "repo_path": result.repo_path,
        "repo_id": result.repo_id,
        "commit": result.commit,
        "agents": agents,
        "findings": findings,
        "finding_count": len(findings),
    }
