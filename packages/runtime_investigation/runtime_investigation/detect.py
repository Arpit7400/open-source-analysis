"""Environment detection (Phase 7) — read-only, no execution.

Inspects a repository to decide what runtime steps make sense: does it declare
dependencies, does it have tests, which runner, what Python version. This is a
static read so it works with no sandbox and no Docker.
"""

from __future__ import annotations

import re
from pathlib import Path

from runtime_investigation.models import EnvironmentInfo

_IGNORE = {".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build", ".next"}
_PY_REQ = re.compile(r"(?:python_requires|requires-python)\s*[=:]\s*['\"]?([^'\"\n]+)")


def _py_files(root: Path) -> list[Path]:
    return [
        p
        for p in root.rglob("*.py")
        if not any(part in _IGNORE for part in p.parts)
    ]


def _is_test(p: Path) -> bool:
    name = p.name
    return name.startswith("test_") or name.endswith("_test.py") or "tests" in p.parts


def detect_environment(repo_path: str | Path) -> EnvironmentInfo:
    """Detect the repository's Python environment characteristics."""
    root = Path(repo_path).expanduser()
    if not root.is_dir():
        raise NotADirectoryError(f"repo_path is not a directory: {repo_path}")

    pyproject = root / "pyproject.toml"
    setup_py = root / "setup.py"
    has_pyproject = pyproject.is_file()
    has_setup_py = setup_py.is_file()
    has_requirements = any((root / n).is_file() for n in ("requirements.txt", "requirements-dev.txt"))

    py_files = _py_files(root)
    has_tests = any(_is_test(p) for p in py_files)

    declared: str | None = None
    for cfg in (pyproject, setup_py, root / "setup.cfg"):
        if cfg.is_file():
            m = _PY_REQ.search(cfg.read_text(encoding="utf-8", errors="replace"))
            if m:
                declared = m.group(1).strip()
                break

    return EnvironmentInfo(
        has_pyproject=has_pyproject,
        has_setup_py=has_setup_py,
        has_requirements=has_requirements,
        has_tests=has_tests,
        test_runner="pytest" if has_tests else "none",
        python_files=len(py_files),
        declared_python=declared,
    )
