"""Static safety preflight (handbook Stage 2 / §8.1).

Before ANY untrusted repository code is executed, scan its install scripts,
build config, and source for high-risk patterns: install hooks, network access,
destructive commands, credential/secret access, path traversal, suspicious
subprocess use, and obfuscation. A HIGH-risk result stops automatic execution
and requires human review.

This is a deterministic, read-only scan (no code runs), so it is fully testable
without Docker or a network.
"""

from __future__ import annotations

import re
from pathlib import Path

from sandbox.models import PreflightIssue, PreflightResult

_IGNORE_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build", ".next"}

# Files most likely to carry install-time execution.
_HOT_FILES = {
    "setup.py",
    "setup.cfg",
    "pyproject.toml",
    "conftest.py",
    "Makefile",
    "install.sh",
    "postinstall.sh",
    ".pre-commit-config.yaml",
}

# (category, severity, regex, explanation). Ordered roughly by danger.
_PATTERNS: list[tuple[str, str, re.Pattern[str], str]] = [
    ("DESTRUCTIVE", "HIGH", re.compile(r"\brm\s+-rf\b|\brmtree\b|\bshutil\.rmtree\b"), "recursive deletion"),
    ("DESTRUCTIVE", "HIGH", re.compile(r"\bos\.remove\b|\bos\.unlink\b|\bformat\s+[A-Za-z]:"), "file/disk destruction"),
    ("CREDENTIAL", "HIGH", re.compile(r"\.ssh/|id_rsa|\.aws/credentials|\.netrc|GITHUB_TOKEN|AWS_SECRET"), "credential/secret access"),
    ("NETWORK", "HIGH", re.compile(r"\bcurl\b|\bwget\b|urllib\.request|requests\.(get|post)|socket\.socket|http[s]?://"), "network access"),
    ("SUBPROCESS", "HIGH", re.compile(r"subprocess\.(run|Popen|call|check_output)\s*\(.*shell\s*=\s*True", re.DOTALL), "shell subprocess (injection risk)"),
    ("INSTALL_HOOK", "MEDIUM", re.compile(r"cmdclass\s*=|class\s+\w*(Install|Develop|BuildPy)\b|os\.system\s*\("), "install-time code execution hook"),
    ("SUBPROCESS", "MEDIUM", re.compile(r"\beval\s*\(|\bexec\s*\(|__import__\s*\("), "dynamic code execution"),
    ("TRAVERSAL", "MEDIUM", re.compile(r"\.\./\.\./|os\.path\.join\([^)]*\.\.\)"), "path traversal"),
    ("OBFUSCATION", "MEDIUM", re.compile(r"base64\.b64decode\s*\(|codecs\.decode\([^)]*rot|marshal\.loads"), "obfuscated payload"),
    ("NETWORK", "LOW", re.compile(r"pip\s+install\b|npm\s+install\b"), "dependency install (network at install time)"),
]

_SEV_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
_RISK_BY_MAXSEV = {0: "SAFE", 1: "LOW", 2: "MEDIUM", 3: "HIGH"}


def _iter_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if any(part in _IGNORE_DIRS for part in p.parts):
            continue
        # scan text-ish, execution-relevant files only
        if p.name in _HOT_FILES or p.suffix in {".py", ".sh", ".bash", ".cfg", ".toml", ".yaml", ".yml", ".cmd", ".ps1"}:
            out.append(p)
    return out


def run_preflight(repo_path: str | Path, execution_flag_enabled: bool = False) -> PreflightResult:
    """Scan ``repo_path`` for high-risk patterns before any execution.

    ``execution_flag_enabled`` reflects the ``repository_execution`` feature
    flag. Even a SAFE result yields ``execution_allowed=False`` when the flag is
    off — the flag is the master switch, the preflight is an additional gate.
    """
    root = Path(repo_path).expanduser()
    if not root.is_dir():
        raise NotADirectoryError(f"repo_path is not a directory: {repo_path}")

    files = _iter_files(root)
    issues: list[PreflightIssue] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = str(path.relative_to(root)).replace("\\", "/")
        hot = path.name in _HOT_FILES
        for lineno, line in enumerate(text.splitlines(), start=1):
            for category, severity, pattern, explanation in _PATTERNS:
                if pattern.search(line):
                    # An install hook in a hot file is more dangerous than the
                    # same pattern in an example; bump severity for hot files.
                    sev = severity
                    if hot and category in {"INSTALL_HOOK", "SUBPROCESS", "NETWORK"} and severity == "MEDIUM":
                        sev = "HIGH"
                    issues.append(
                        PreflightIssue(
                            category=category,
                            severity=sev,
                            path=rel,
                            line=lineno,
                            snippet=line.strip()[:200],
                            explanation=explanation,
                        )
                    )

    max_sev = max((_SEV_RANK[i.severity] for i in issues), default=0)
    risk = _RISK_BY_MAXSEV[max_sev]

    # HIGH risk blocks automatic execution regardless of the flag.
    if risk == "HIGH":
        allowed = False
        reason = "HIGH-risk static findings — automatic execution blocked; human review required."
    elif not execution_flag_enabled:
        allowed = False
        reason = "repository_execution flag is disabled (default) — execution not permitted."
    else:
        allowed = True
        reason = f"{risk}-risk repository; execution permitted under resource limits."

    return PreflightResult(
        repo_path=str(root),
        risk_level="BLOCKED" if (risk == "HIGH") else risk,
        issues=issues,
        files_scanned=len(files),
        execution_allowed=allowed,
        reason=reason,
    )
