"""Hermetic tests for the AST-based analysis agents."""

from __future__ import annotations

from pathlib import Path

from static_analysis import analyze_repository, run_ast_agents
from static_analysis.models import CATEGORIES, REPRODUCTION, SEVERITIES


def _by_agent(reports: list) -> dict[str, list]:
    return {r.agent_id: r.findings for r in reports}


def test_security_agent_flags_the_obvious(buggy_repo: Path) -> None:
    reports = run_ast_agents(buggy_repo, repo_id="acme/repo", commit="deadbeef")
    sec = _by_agent(reports)["static.security"]
    summaries = " ".join(f.summary.lower() for f in sec)
    assert "bare `except:`" in summaries
    assert "eval" in summaries
    assert "shell=true" in summaries
    # every finding has real evidence pointing into bad.py with a line number
    for f in sec:
        assert f.evidence and f.evidence[0].path == "pkg/bad.py"
        assert f.evidence[0].start_line and f.evidence[0].start_line >= 1
        assert f.evidence[0].snippet


def test_code_quality_flags_mutable_default(buggy_repo: Path) -> None:
    cq = _by_agent(run_ast_agents(buggy_repo))["static.code_quality"]
    assert any("mutable default" in f.summary.lower() for f in cq)


def test_test_quality_fires_when_no_tests(buggy_repo: Path) -> None:
    tq = _by_agent(run_ast_agents(buggy_repo))["static.test_quality"]
    assert len(tq) == 1
    assert "no test files" in tq[0].summary.lower()


def test_test_quality_quiet_when_tests_present(repo_with_tests: Path) -> None:
    tq = _by_agent(run_ast_agents(repo_with_tests))["static.test_quality"]
    assert tq == []


def test_findings_match_contract_enums(buggy_repo: Path) -> None:
    result = analyze_repository(buggy_repo, repo_id="acme/repo", include_tools=False)
    assert result.findings, "expected findings from the buggy fixture"
    for f in result.findings:
        assert f.category in CATEGORIES
        assert f.severity in SEVERITIES
        assert f.reproduction_status in REPRODUCTION
        assert 0.0 <= f.confidence <= 1.0
        assert f.finding_id and f.agent_id


def test_finding_ids_are_deterministic(buggy_repo: Path) -> None:
    a = analyze_repository(buggy_repo, include_tools=False).findings
    b = analyze_repository(buggy_repo, include_tools=False).findings
    assert [f.finding_id for f in a] == [f.finding_id for f in b]
