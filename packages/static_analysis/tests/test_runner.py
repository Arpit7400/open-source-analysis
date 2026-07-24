"""Runner-level tests: aggregation, graceful tool degradation, error handling."""

from __future__ import annotations

from pathlib import Path

import pytest

from static_analysis import analyze_repository
from static_analysis.tool_agents import run_ruff_agent


def test_analyze_aggregates_all_agents(buggy_repo: Path) -> None:
    result = analyze_repository(buggy_repo, repo_id="acme/repo", include_tools=True)
    agent_ids = {r.agent_id for r in result.reports}
    # AST agents always present:
    assert {
        "static.security",
        "static.code_quality",
        "static.typing",
        "static.docs_drift",
        "static.test_quality",
    } <= agent_ids
    # tool agents present (ruff/mypy) even if they only produce a note:
    assert "static.ruff" in agent_ids
    assert "static.mypy" in agent_ids
    # every report is ok=True (agents never hard-fail the run)
    assert all(r.ok for r in result.reports)


def test_missing_repo_raises(tmp_path: Path) -> None:
    with pytest.raises(NotADirectoryError):
        analyze_repository(tmp_path / "does-not-exist")


def test_ruff_agent_degrades_when_no_files(tmp_path: Path) -> None:
    # empty dir -> ruff finds nothing; agent stays ok and fabricates nothing.
    report = run_ruff_agent(tmp_path, repo_id="x")
    assert report.ok
    assert report.findings == []
