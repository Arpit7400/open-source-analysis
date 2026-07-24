"""Top-level entry point: run the full static-analysis swarm over a repo."""

from __future__ import annotations

from pathlib import Path

from static_analysis.ast_agents import run_ast_agents
from static_analysis.models import AnalysisResult
from static_analysis.tool_agents import run_mypy_agent, run_ruff_agent


def analyze_repository(
    repo_path: str | Path,
    repo_id: str | None = None,
    commit: str | None = None,
    *,
    include_tools: bool = True,
) -> AnalysisResult:
    """Run all static-analysis agents over ``repo_path``.

    Combines the deterministic AST agents (always available) with the
    tool-backed ruff/mypy agents (when those tools are installed). Every finding
    carries exact ``path:line`` evidence and cites the target repo/commit.

    ``include_tools=False`` skips the subprocess-based ruff/mypy agents (useful
    for fast, fully-hermetic runs).
    """
    root = Path(repo_path).expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"repo_path is not a directory: {root}")

    reports = list(run_ast_agents(root, repo_id=repo_id, commit=commit))
    if include_tools:
        reports.append(run_ruff_agent(root, repo_id=repo_id, commit=commit))
        reports.append(run_mypy_agent(root, repo_id=repo_id, commit=commit))

    return AnalysisResult(
        repo_path=str(root),
        repo_id=repo_id,
        commit=commit,
        reports=reports,
    )
