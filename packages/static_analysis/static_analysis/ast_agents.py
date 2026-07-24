"""Deterministic AST-based static-analysis agents.

Each agent walks a repository's Python files with the stdlib :mod:`ast` module
and emits typed :class:`~static_analysis.models.Finding` objects with exact
``path:line`` evidence and a real code snippet. No external tools are required,
so these run identically on macOS, Windows, and Linux.

Agents implemented here (handbook §4.1 static swarm):

* ``static.security``   — SECURITY_SMELL: bare ``except:``, ``eval``/``exec``,
  ``subprocess(..., shell=True)``, ``pickle.loads``, ``yaml.load`` w/o Loader,
  ``assert`` used for validation, hard-coded ``verify=False``.
* ``static.code_quality`` — CODE_QUALITY: bare ``except:``, mutable default
  args, overly long functions, TODO/FIXME markers.
* ``static.typing``     — TYPING: public functions missing return annotations.
* ``static.docs_drift`` — DOCS_DRIFT: public modules/classes/functions missing
  docstrings.
* ``static.test_quality`` — TEST_QUALITY: source files with no adjacent test.

The heavier ``ruff``/``mypy`` agents live in :mod:`static_analysis.tool_agents`.
"""

from __future__ import annotations

import ast
import hashlib
from collections.abc import Iterable
from pathlib import Path

from static_analysis.models import AgentReport, EvidenceRef, Finding

IGNORE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
    ".next",
    ".tox",
    "site-packages",
}


def iter_python_files(root: Path) -> list[Path]:
    """Return all ``.py`` files under ``root``, skipping vendored/build dirs."""
    out: list[Path] = []
    for p in sorted(root.rglob("*.py")):
        if any(part in IGNORE_DIRS for part in p.parts):
            continue
        out.append(p)
    return out


def _fid(*parts: object) -> str:
    """Deterministic finding id from its salient parts."""
    raw = "|".join(str(x) for x in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _snippet(lines: list[str], start: int, end: int | None = None) -> str:
    """Return source text for 1-indexed ``start``..``end`` (clamped)."""
    end = end or start
    lo = max(0, start - 1)
    hi = min(len(lines), end)
    return "\n".join(lines[lo:hi]).rstrip()


def _evidence(
    repo_id: str | None, commit: str | None, rel: str, start: int, end: int, snippet: str
) -> EvidenceRef:
    return EvidenceRef(
        repo=repo_id,
        commit=commit,
        path=rel,
        start_line=start,
        end_line=end,
        snippet=snippet[:500],
    )


class _FileCtx:
    """Parsed context for one file passed to every per-file check."""

    def __init__(self, path: Path, root: Path, repo_id: str | None, commit: str | None) -> None:
        self.path = path
        self.root = root
        self.rel = _rel(path, root)
        self.repo_id = repo_id
        self.commit = commit
        self.source = path.read_text(encoding="utf-8", errors="replace")
        self.lines = self.source.splitlines()
        try:
            self.tree: ast.AST | None = ast.parse(self.source, filename=str(path))
        except SyntaxError:
            self.tree = None

    def ev(self, node: ast.AST) -> EvidenceRef:
        start = getattr(node, "lineno", 1)
        end = getattr(node, "end_lineno", start) or start
        return _evidence(
            self.repo_id, self.commit, self.rel, start, end, _snippet(self.lines, start, end)
        )


# --------------------------------------------------------------------------- #
# Security smell agent
# --------------------------------------------------------------------------- #
def _security_findings(ctx: _FileCtx) -> Iterable[Finding]:
    if ctx.tree is None:
        return
    agent = "static.security"
    for node in ast.walk(ctx.tree):
        # bare except:
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            yield Finding(
                finding_id=_fid(ctx.rel, node.lineno, "bare-except"),
                category="SECURITY_SMELL",
                severity="MEDIUM",
                confidence=0.9,
                summary=f"Bare `except:` swallows all exceptions (incl. KeyboardInterrupt/SystemExit) at {ctx.rel}:{node.lineno}.",
                evidence=[ctx.ev(node)],
                duplicate_search_terms=["bare except", "except: pass", ctx.rel],
                suggested_next_step="Catch a specific exception type (e.g. `except ValueError:`) and re-raise control-flow signals.",
                limitations=["Static heuristic; runtime impact depends on the surrounding logic."],
                agent_id=agent,
            )
        # eval / exec
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"}:
            yield Finding(
                finding_id=_fid(ctx.rel, node.lineno, node.func.id),
                category="SECURITY_SMELL",
                severity="HIGH",
                confidence=0.85,
                summary=f"Use of `{node.func.id}()` at {ctx.rel}:{node.lineno} can execute arbitrary code.",
                evidence=[ctx.ev(node)],
                duplicate_search_terms=[f"{node.func.id}(", ctx.rel],
                suggested_next_step=f"Avoid `{node.func.id}`; use a safe parser (ast.literal_eval, json) or explicit dispatch.",
                limitations=["Flagged regardless of whether the input is trusted."],
                agent_id=agent,
            )
        # subprocess(..., shell=True)
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                    yield Finding(
                        finding_id=_fid(ctx.rel, node.lineno, "shell-true"),
                        category="SECURITY_SMELL",
                        severity="HIGH",
                        confidence=0.8,
                        summary=f"`shell=True` at {ctx.rel}:{node.lineno} risks shell injection.",
                        evidence=[ctx.ev(node)],
                        duplicate_search_terms=["shell=True", "subprocess", ctx.rel],
                        suggested_next_step="Pass an argument list and `shell=False`; never interpolate untrusted input into a shell string.",
                        limitations=["Does not trace whether the command is attacker-controlled."],
                        agent_id=agent,
                    )
                if kw.arg == "verify" and isinstance(kw.value, ast.Constant) and kw.value.value is False:
                    yield Finding(
                        finding_id=_fid(ctx.rel, node.lineno, "verify-false"),
                        category="SECURITY_SMELL",
                        severity="MEDIUM",
                        confidence=0.75,
                        summary=f"TLS verification disabled (`verify=False`) at {ctx.rel}:{node.lineno}.",
                        evidence=[ctx.ev(node)],
                        duplicate_search_terms=["verify=False", ctx.rel],
                        suggested_next_step="Keep certificate verification on; pin a CA bundle if a custom CA is needed.",
                        limitations=["Static match; may be test-only code."],
                        agent_id=agent,
                    )


# --------------------------------------------------------------------------- #
# Code quality agent
# --------------------------------------------------------------------------- #
_MUTABLE_DEFAULTS = (ast.List, ast.Dict, ast.Set)


def _code_quality_findings(ctx: _FileCtx) -> Iterable[Finding]:
    if ctx.tree is None:
        return
    agent = "static.code_quality"
    for node in ast.walk(ctx.tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            # mutable default arguments
            for default in node.args.defaults + node.args.kw_defaults:
                if isinstance(default, _MUTABLE_DEFAULTS):
                    yield Finding(
                        finding_id=_fid(ctx.rel, node.lineno, "mutable-default", node.name),
                        category="CODE_QUALITY",
                        severity="MEDIUM",
                        confidence=0.9,
                        summary=f"Mutable default argument in `{node.name}` at {ctx.rel}:{node.lineno}.",
                        evidence=[ctx.ev(node)],
                        duplicate_search_terms=["mutable default argument", node.name, ctx.rel],
                        suggested_next_step="Use `None` as the default and create the container inside the function body.",
                        limitations=["Reported for all mutable literals used as defaults."],
                        agent_id=agent,
                    )
            # very long functions
            length = (getattr(node, "end_lineno", node.lineno) or node.lineno) - node.lineno
            if length > 80:
                yield Finding(
                    finding_id=_fid(ctx.rel, node.lineno, "long-func", node.name),
                    category="CODE_QUALITY",
                    severity="LOW",
                    confidence=0.6,
                    summary=f"Function `{node.name}` is {length} lines at {ctx.rel}:{node.lineno} — hard to test/maintain.",
                    evidence=[ctx.ev(node)],
                    duplicate_search_terms=[node.name, "long function", ctx.rel],
                    suggested_next_step="Extract cohesive helpers to reduce the function below ~80 lines.",
                    limitations=["Line-count heuristic; some long functions are justified."],
                    agent_id=agent,
                )
    # TODO / FIXME markers
    for i, line in enumerate(ctx.lines, start=1):
        stripped = line.strip()
        for marker in ("TODO", "FIXME", "XXX", "HACK"):
            if f"# {marker}" in line or stripped.startswith(f"#{marker}"):
                yield Finding(
                    finding_id=_fid(ctx.rel, i, "marker", marker),
                    category="CODE_QUALITY",
                    severity="INFO",
                    confidence=0.7,
                    summary=f"`{marker}` marker at {ctx.rel}:{i}.",
                    evidence=[_evidence(ctx.repo_id, ctx.commit, ctx.rel, i, i, line.rstrip())],
                    duplicate_search_terms=[marker, ctx.rel],
                    suggested_next_step="Resolve or file an issue linking to this location.",
                    limitations=["Comment-text match."],
                    agent_id=agent,
                )
                break


# --------------------------------------------------------------------------- #
# Typing agent
# --------------------------------------------------------------------------- #
def _typing_findings(ctx: _FileCtx) -> Iterable[Finding]:
    if ctx.tree is None:
        return
    agent = "static.typing"
    for node in ast.walk(ctx.tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            if node.name.startswith("_"):
                continue  # only flag public API surface
            if node.returns is None and node.name != "__init__":
                yield Finding(
                    finding_id=_fid(ctx.rel, node.lineno, "no-return-anno", node.name),
                    category="TYPING",
                    severity="LOW",
                    confidence=0.65,
                    summary=f"Public function `{node.name}` has no return type annotation at {ctx.rel}:{node.lineno}.",
                    evidence=[ctx.ev(node)],
                    duplicate_search_terms=[node.name, "return annotation", ctx.rel],
                    suggested_next_step="Add a return annotation (`-> T`) to make the public contract explicit.",
                    limitations=["Only inspects the signature; does not run a type checker."],
                    agent_id=agent,
                )


# --------------------------------------------------------------------------- #
# Docs-drift agent
# --------------------------------------------------------------------------- #
def _docs_findings(ctx: _FileCtx) -> Iterable[Finding]:
    if ctx.tree is None or not isinstance(ctx.tree, ast.Module):
        return
    agent = "static.docs_drift"
    if ast.get_docstring(ctx.tree) is None and ctx.lines:
        yield Finding(
            finding_id=_fid(ctx.rel, 1, "module-docstring"),
            category="DOCS_DRIFT",
            severity="INFO",
            confidence=0.6,
            summary=f"Module `{ctx.rel}` has no docstring.",
            evidence=[_evidence(ctx.repo_id, ctx.commit, ctx.rel, 1, 1, _snippet(ctx.lines, 1, 1))],
            duplicate_search_terms=["module docstring", ctx.rel],
            suggested_next_step="Add a one-line module docstring describing its purpose.",
            limitations=["Presence check only; does not judge quality."],
            agent_id=agent,
        )
    for node in ast.walk(ctx.tree):
        if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            if node.name.startswith("_"):
                continue
            if ast.get_docstring(node) is None:
                kind = "class" if isinstance(node, ast.ClassDef) else "function"
                yield Finding(
                    finding_id=_fid(ctx.rel, node.lineno, "docstring", node.name),
                    category="DOCS_DRIFT",
                    severity="INFO",
                    confidence=0.55,
                    summary=f"Public {kind} `{node.name}` has no docstring at {ctx.rel}:{node.lineno}.",
                    evidence=[ctx.ev(node)],
                    duplicate_search_terms=[node.name, "docstring", ctx.rel],
                    suggested_next_step=f"Document `{node.name}` with a short docstring.",
                    limitations=["Presence check only."],
                    agent_id=agent,
                )


# --------------------------------------------------------------------------- #
# Test-quality agent (repo-level)
# --------------------------------------------------------------------------- #
def _is_test_file(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return name.startswith("test_") or name.endswith("_test.py") or "/tests/" in f"/{rel}"


def _test_quality_findings(files: list[Path], root: Path, repo_id: str | None, commit: str | None) -> list[Finding]:
    agent = "static.test_quality"
    rels = [_rel(p, root) for p in files]
    has_any_test = any(_is_test_file(r) for r in rels)
    findings: list[Finding] = []
    if not has_any_test and files:
        findings.append(
            Finding(
                finding_id=_fid(repo_id or str(root), "no-tests"),
                category="TEST_QUALITY",
                severity="MEDIUM",
                confidence=0.8,
                summary="Repository has Python source but no test files (no test_*.py / *_test.py / tests/).",
                evidence=[EvidenceRef(repo=repo_id, commit=commit, path=".", snippet="(no test files found)")],
                reproduction_required=False,
                duplicate_search_terms=["no tests", "missing test coverage"],
                suggested_next_step="Add a `tests/` directory with pytest cases covering the public API.",
                limitations=["Detects presence of test files, not their coverage or quality."],
                agent_id=agent,
            )
        )
    return findings


_PER_FILE_AGENTS = (
    _security_findings,
    _code_quality_findings,
    _typing_findings,
    _docs_findings,
)


def run_ast_agents(
    root: Path, repo_id: str | None = None, commit: str | None = None
) -> list[AgentReport]:
    """Run all AST-based agents over ``root`` and return one report per agent."""
    files = iter_python_files(root)
    buckets: dict[str, list[Finding]] = {}
    for path in files:
        try:
            ctx = _FileCtx(path, root, repo_id, commit)
        except OSError:
            continue
        for check in _PER_FILE_AGENTS:
            for finding in check(ctx):
                buckets.setdefault(finding.agent_id, []).append(finding)

    # repo-level test-quality agent
    tq = _test_quality_findings(files, root, repo_id, commit)
    if tq or files:
        buckets.setdefault("static.test_quality", []).extend(tq)

    reports: list[AgentReport] = []
    for agent_id in (
        "static.security",
        "static.code_quality",
        "static.typing",
        "static.docs_drift",
        "static.test_quality",
    ):
        reports.append(
            AgentReport(
                agent_id=agent_id,
                ok=True,
                findings=buckets.get(agent_id, []),
                note=f"{len(buckets.get(agent_id, []))} finding(s) over {len(files)} Python file(s).",
            )
        )
    return reports
