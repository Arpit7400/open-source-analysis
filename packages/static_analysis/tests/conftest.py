"""A bundled, intentionally-buggy fixture repo for hermetic analysis tests."""

from __future__ import annotations

from pathlib import Path

import pytest

# A module that trips several agents deterministically.
_BUGGY = '''\
import subprocess


def run(cmd, opts=[]):
    try:
        subprocess.run(cmd, shell=True)
    except:
        pass
    return eval("1 + 1")
'''

# A clean, well-documented module (should produce few/no high findings).
_CLEAN = '''\
"""A tidy module."""


def add(a: int, b: int) -> int:
    """Return the sum of two integers."""
    return a + b
'''


@pytest.fixture
def buggy_repo(tmp_path: Path) -> Path:
    """Create a temp repo containing one buggy module and one clean module.

    Deliberately has NO test files so the test-quality agent fires too.
    """
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("")
    (tmp_path / "pkg" / "bad.py").write_text(_BUGGY, encoding="utf-8")
    (tmp_path / "pkg" / "good.py").write_text(_CLEAN, encoding="utf-8")
    return tmp_path


@pytest.fixture
def repo_with_tests(tmp_path: Path) -> Path:
    """A repo that DOES contain a test file (test-quality agent stays quiet)."""
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "good.py").write_text(_CLEAN, encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_good.py").write_text(
        '"""t."""\n\n\ndef test_add() -> None:\n    assert 1 == 1\n', encoding="utf-8"
    )
    return tmp_path
