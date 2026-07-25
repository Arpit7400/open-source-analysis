"""Runtime investigation tests (hermetic: execution disabled by default)."""

from __future__ import annotations

from pathlib import Path

import pytest

from runtime_investigation import RuntimeInvestigator, detect_environment


def _make_repo(tmp_path: Path, *, tests: bool, pyproject: bool, unsafe: bool = False) -> Path:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "core.py").write_text('"""m."""\n\n\ndef add(a: int, b: int) -> int:\n    return a + b\n', encoding="utf-8")
    if pyproject:
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "x"\nrequires-python = ">=3.12"\n', encoding="utf-8"
        )
    if tests:
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_core.py").write_text('def test_add():\n    assert 1 == 1\n', encoding="utf-8")
    if unsafe:
        (tmp_path / "setup.py").write_text('import os\nos.system("rm -rf /")\n', encoding="utf-8")
    return tmp_path


def test_detect_environment(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, tests=True, pyproject=True)
    env = detect_environment(repo)
    assert env.has_pyproject is True
    assert env.has_tests is True
    assert env.test_runner == "pytest"
    assert env.declared_python == ">=3.12"
    assert env.python_files >= 2


def test_planned_report_when_execution_disabled(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, tests=True, pyproject=True)
    report = RuntimeInvestigator(execution_flag_enabled=False).investigate(repo)
    assert report.executed is False
    assert report.environment.has_tests is True
    # a full plan is present even though nothing ran
    names = [s.name for s in report.steps]
    assert "tests" in names and "lint" in names and "type" in names
    # every step is marked not-executed with a refusal reason
    assert all(s.executed is False for s in report.steps)
    assert all(s.exit_code is None for s in report.steps)
    assert report.reproduction_status == "PENDING"


def test_high_risk_repo_refused(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, tests=True, pyproject=True, unsafe=True)
    report = RuntimeInvestigator(execution_flag_enabled=True).investigate(repo)
    assert report.executed is False
    assert "BLOCKED" in report.reason
    assert report.reproduction_status == "NOT_REQUIRED"


def test_no_tests_skips_test_step(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, tests=False, pyproject=True)
    report = RuntimeInvestigator(execution_flag_enabled=False).investigate(repo)
    names = [s.name for s in report.steps]
    assert "tests" not in names
    assert "lint" in names


def test_missing_repo_raises(tmp_path: Path) -> None:
    with pytest.raises(NotADirectoryError):
        RuntimeInvestigator().investigate(tmp_path / "nope")
