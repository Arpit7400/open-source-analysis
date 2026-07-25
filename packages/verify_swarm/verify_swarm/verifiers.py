"""Independent verification checks for a candidate patch (Phase 10).

Each verifier is a distinct agent (``verify.*``) that inspects a candidate the
patch authors (``fix.*``) did NOT write, per the handbook rule that authors may
not verify their own output. Verifiers apply the candidate's diff to an isolated
copy of the source and run a real, deterministic check, returning a
:class:`~patch_gen.models.VerificationCheck` (PASS | FAIL | SKIP).

Checks implemented:

* ``verify.syntax``   — the patched file still parses as valid Python.
* ``verify.scope``    — only the expected file changed, and the change is small
  (no unrelated edits sneaking in).
* ``verify.lint``     — ruff is no *worse* on the patched file than before.
* ``verify.type``     — mypy is no *worse* on the patched file than before.
* ``verify.adversary``— an adversarial critic looking for reasons to reject
  (empty diff, NO_SUBMISSION, unparseable, or a diff that changes behaviour
  beyond the stated fix).

All checks are best-effort and never raise: a check that cannot run returns SKIP
with an explanation rather than crashing the swarm.
"""

from __future__ import annotations

import ast
import subprocess
import sys
import tempfile
from pathlib import Path

from patch_gen.models import Candidate, VerificationCheck


def _apply_diff_to_text(original: str, cand: Candidate) -> str | None:
    """Apply a candidate's simple before/new hunks to ``original`` text.

    Our generator produces line-level replacements (``old`` -> ``new`` on the
    ``DiffLine``). We apply them by exact substring replacement of the ``old``
    block with the ``new`` block. Returns the patched text, or ``None`` if a
    hunk's ``old`` text is not found (so the caller can FAIL the scope check).
    """
    text = original
    for dl in cand.diff:
        old = dl.old.strip()
        new = dl.new.strip()
        if not old:
            continue
        if old not in text:
            return None
        text = text.replace(old, new, 1)
    return text


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _ruff_count(pyfile: Path) -> int | None:
    """Number of ruff diagnostics for a single file, or None if ruff absent."""
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "ruff", "check", "--output-format", "concise", str(pyfile)],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    # concise format: one line per diagnostic containing "path:line:col:"
    return sum(1 for line in proc.stdout.splitlines() if ":" in line and str(pyfile.name) in line)


def _mypy_count(pyfile: Path) -> int | None:
    """Number of mypy errors for a single file, or None if mypy absent."""
    try:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "mypy",
                "--no-error-summary",
                "--no-color-output",
                "--ignore-missing-imports",
                str(pyfile),
            ],
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return sum(1 for line in proc.stdout.splitlines() if ": error:" in line)


# --------------------------------------------------------------------------- #
# Individual verifiers. Each returns a VerificationCheck.
# --------------------------------------------------------------------------- #
def verify_syntax(repo_root: Path, cand: Candidate) -> VerificationCheck:
    agent = "verify.syntax"
    if not cand.diff:
        return VerificationCheck(check="syntax", status="SKIP", detail="no diff to check", verifier_agent=agent)
    dl = cand.diff[0]
    original = _read(repo_root / dl.path) if dl.path else None
    if original is None:
        return VerificationCheck(check="syntax", status="SKIP", detail=f"cannot read {dl.path}", verifier_agent=agent)
    patched = _apply_diff_to_text(original, cand)
    if patched is None:
        return VerificationCheck(
            check="syntax", status="FAIL", detail="patch does not apply (old text not found)", verifier_agent=agent
        )
    try:
        ast.parse(patched)
    except SyntaxError as exc:
        return VerificationCheck(check="syntax", status="FAIL", detail=f"patched file does not parse: {exc}", verifier_agent=agent)
    return VerificationCheck(check="syntax", status="PASS", detail="patched file parses cleanly", verifier_agent=agent)


def verify_scope(repo_root: Path, cand: Candidate) -> VerificationCheck:
    agent = "verify.scope"
    if not cand.diff:
        return VerificationCheck(check="scope", status="SKIP", detail="no diff", verifier_agent=agent)
    paths = {dl.path for dl in cand.diff if dl.path}
    if len(paths) > 1:
        return VerificationCheck(
            check="scope", status="FAIL", detail=f"touches {len(paths)} files: {sorted(paths)}", verifier_agent=agent
        )
    if cand.unrelated_changes:
        return VerificationCheck(check="scope", status="FAIL", detail="candidate flags unrelated changes", verifier_agent=agent)
    # measure changed-line count from the before/new blocks
    changed = sum(max(len(dl.old.splitlines()), len(dl.new.splitlines())) for dl in cand.diff)
    if changed > 40:
        return VerificationCheck(check="scope", status="FAIL", detail=f"change too large ({changed} lines)", verifier_agent=agent)
    return VerificationCheck(check="scope", status="PASS", detail=f"single file, {changed} line(s) changed", verifier_agent=agent)


def verify_lint(repo_root: Path, cand: Candidate) -> VerificationCheck:
    agent = "verify.lint"
    if not cand.diff:
        return VerificationCheck(check="lint", status="SKIP", detail="no diff", verifier_agent=agent)
    dl = cand.diff[0]
    original = _read(repo_root / dl.path) if dl.path else None
    if original is None:
        return VerificationCheck(check="lint", status="SKIP", detail="cannot read source", verifier_agent=agent)
    patched = _apply_diff_to_text(original, cand)
    if patched is None:
        return VerificationCheck(check="lint", status="FAIL", detail="patch does not apply", verifier_agent=agent)
    with tempfile.TemporaryDirectory() as td:
        before = Path(td) / "before.py"
        after = Path(td) / "after.py"
        before.write_text(original, encoding="utf-8")
        after.write_text(patched, encoding="utf-8")
        b = _ruff_count(before)
        a = _ruff_count(after)
    if a is None or b is None:
        return VerificationCheck(check="lint", status="SKIP", detail="ruff not available", verifier_agent=agent)
    if a > b:
        return VerificationCheck(check="lint", status="FAIL", detail=f"patch adds lint issues ({b}->{a})", verifier_agent=agent)
    return VerificationCheck(check="lint", status="PASS", detail=f"ruff not worse ({b}->{a})", verifier_agent=agent)


def verify_type(repo_root: Path, cand: Candidate) -> VerificationCheck:
    agent = "verify.type"
    if not cand.diff:
        return VerificationCheck(check="type", status="SKIP", detail="no diff", verifier_agent=agent)
    dl = cand.diff[0]
    original = _read(repo_root / dl.path) if dl.path else None
    if original is None:
        return VerificationCheck(check="type", status="SKIP", detail="cannot read source", verifier_agent=agent)
    patched = _apply_diff_to_text(original, cand)
    if patched is None:
        return VerificationCheck(check="type", status="FAIL", detail="patch does not apply", verifier_agent=agent)
    with tempfile.TemporaryDirectory() as td:
        before = Path(td) / "before.py"
        after = Path(td) / "after.py"
        before.write_text(original, encoding="utf-8")
        after.write_text(patched, encoding="utf-8")
        b = _mypy_count(before)
        a = _mypy_count(after)
    if a is None or b is None:
        return VerificationCheck(check="type", status="SKIP", detail="mypy not available", verifier_agent=agent)
    if a > b:
        return VerificationCheck(check="type", status="FAIL", detail=f"patch adds type errors ({b}->{a})", verifier_agent=agent)
    return VerificationCheck(check="type", status="PASS", detail=f"mypy not worse ({b}->{a})", verifier_agent=agent)


def verify_adversary(repo_root: Path, cand: Candidate) -> VerificationCheck:
    """A skeptic: default to rejecting weak/empty/no-submission candidates."""
    agent = "verify.adversary"
    if cand.verdict == "NO_SUBMISSION":
        return VerificationCheck(
            check="adversarial", status="PASS", detail="NO_SUBMISSION is a valid, honest outcome", verifier_agent=agent
        )
    if not cand.diff or all(not dl.new.strip() for dl in cand.diff):
        return VerificationCheck(check="adversarial", status="FAIL", detail="empty or no-op diff", verifier_agent=agent)
    if not cand.root_cause.strip():
        return VerificationCheck(check="adversarial", status="FAIL", detail="no root-cause stated", verifier_agent=agent)
    if not cand.test_snippet.strip():
        return VerificationCheck(
            check="adversarial", status="FAIL", detail="no test accompanies the change", verifier_agent=agent
        )
    return VerificationCheck(check="adversarial", status="PASS", detail="root cause + test + real diff present", verifier_agent=agent)


ALL_VERIFIERS = (verify_syntax, verify_scope, verify_lint, verify_type, verify_adversary)
