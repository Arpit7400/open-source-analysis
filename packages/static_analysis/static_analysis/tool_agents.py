"""Tool-backed static-analysis agents: real ``ruff`` and ``mypy`` runs.

These invoke the actual tools as subprocesses (when present on PATH or in the
active interpreter's environment) and translate their machine-readable output
into typed :class:`~static_analysis.models.Finding` objects. When a tool is not
available, the agent degrades gracefully to an ``ok`` report with a note (it
never fabricates findings), so the AST agents still provide coverage.

Deterministic-tools-first (dev-rule #5): a real linter/type-checker is far more
reliable than asking an LLM whether code lints.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from static_analysis.ast_agents import _fid, iter_python_files
from static_analysis.models import AgentReport, EvidenceRef, Finding

_RUFF_SEVERITY = {"E": "MEDIUM", "F": "HIGH", "W": "LOW"}


def _rel(path: str, root: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(root.resolve())).replace("\\", "/")
    except ValueError:
        return path.replace("\\", "/")


def _run(cmd: list[str], cwd: Path, timeout: int = 120) -> tuple[int, str, str]:
    """Run ``cmd`` capturing output; never raises on a non-zero exit."""
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


def run_ruff_agent(
    root: Path, repo_id: str | None = None, commit: str | None = None, limit: int = 200
) -> AgentReport:
    """Run ``ruff check --output-format json`` and map diagnostics to findings."""
    agent = "static.ruff"
    cmd = [sys.executable, "-m", "ruff", "check", "--output-format", "json", "."]
    try:
        _, out, err = _run(cmd, root)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return AgentReport(agent_id=agent, ok=True, note=f"ruff not run: {exc}")
    try:
        diagnostics = json.loads(out or "[]")
    except json.JSONDecodeError:
        return AgentReport(agent_id=agent, ok=True, note=f"ruff produced no parseable output ({err.strip()[:80]})")

    findings: list[Finding] = []
    for d in diagnostics[:limit]:
        code = str(d.get("code") or "")
        rel = _rel(str(d.get("filename") or ""), root)
        loc = d.get("location") or {}
        end = d.get("end_location") or {}
        start_line = int(loc.get("row") or 1)
        end_line = int(end.get("row") or start_line)
        sev = _RUFF_SEVERITY.get(code[:1], "LOW") if code else "LOW"
        findings.append(
            Finding(
                finding_id=_fid(rel, start_line, "ruff", code),
                category="CODE_QUALITY",
                severity=sev,
                confidence=0.95,
                summary=f"ruff {code}: {d.get('message', '').strip()} ({rel}:{start_line})",
                evidence=[
                    EvidenceRef(
                        repo=repo_id,
                        commit=commit,
                        path=rel,
                        start_line=start_line,
                        end_line=end_line,
                        snippet=str(d.get("message") or "")[:500],
                    )
                ],
                duplicate_search_terms=[code, rel],
                suggested_next_step="Fix the ruff diagnostic or justify an explicit ignore.",
                limitations=["Reflects the target repo's own ruff config if present, else defaults."],
                agent_id=agent,
            )
        )
    return AgentReport(agent_id=agent, ok=True, findings=findings, note=f"{len(findings)} ruff diagnostic(s).")


def run_mypy_agent(
    root: Path, repo_id: str | None = None, commit: str | None = None, limit: int = 200
) -> AgentReport:
    """Run ``mypy`` and map ``file:line: error: ...`` lines to findings."""
    agent = "static.mypy"
    targets = [str(p) for p in iter_python_files(root)][:400]
    if not targets:
        return AgentReport(agent_id=agent, ok=True, note="no Python files to type-check.")
    cmd = [
        sys.executable,
        "-m",
        "mypy",
        "--no-error-summary",
        "--hide-error-context",
        "--no-color-output",
        "--ignore-missing-imports",
        *targets,
    ]
    try:
        _, out, _ = _run(cmd, root)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return AgentReport(agent_id=agent, ok=True, note=f"mypy not run: {exc}")

    findings: list[Finding] = []
    for line in (out or "").splitlines():
        # Format: path:line: error: message  [code]
        if ": error:" not in line and ": warning:" not in line:
            continue
        try:
            path_part, rest = line.split(":", 1)
            line_no_str, rest = rest.split(":", 1)
            line_no = int(line_no_str)
        except ValueError:
            continue
        rel = _rel(path_part, root)
        message = rest.split(":", 1)[-1].strip()
        findings.append(
            Finding(
                finding_id=_fid(rel, line_no, "mypy", message[:40]),
                category="TYPING",
                severity="MEDIUM" if ": error:" in line else "LOW",
                confidence=0.9,
                summary=f"mypy: {message} ({rel}:{line_no})",
                evidence=[
                    EvidenceRef(
                        repo=repo_id,
                        commit=commit,
                        path=rel,
                        start_line=line_no,
                        end_line=line_no,
                        snippet=message[:500],
                    )
                ],
                duplicate_search_terms=["mypy", rel],
                suggested_next_step="Resolve the type error or add a precise annotation.",
                limitations=["Run with --ignore-missing-imports; third-party stub gaps are suppressed."],
                agent_id=agent,
            )
        )
        if len(findings) >= limit:
            break
    return AgentReport(agent_id=agent, ok=True, findings=findings, note=f"{len(findings)} mypy diagnostic(s).")
