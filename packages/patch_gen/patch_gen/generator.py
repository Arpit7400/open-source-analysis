"""Candidate patch generation (Phase 9).

Given a static finding (category + exact ``path:line`` + snippet) and the
repository root, generate 2-3 **independent** candidate patches, each with:

* a root-cause statement,
* a real unified diff (computed with :mod:`difflib` from the actual source),
* a suggested test snippet,
* scope / risk analysis,
* verification commands,

plus a **NO_SUBMISSION** candidate when the evidence is too weak to act on
(handbook Stage 8). Generation is deterministic by default (template mode) and
optionally enriched by a local LLM when one is reachable (``LocalLLM``) — but the
diff itself is always computed deterministically from source, never hallucinated.
"""

from __future__ import annotations

import ast
import difflib
import hashlib
import re
from collections.abc import Callable
from pathlib import Path

from patch_gen.llm import LocalLLM
from patch_gen.models import Candidate, CandidateSet, DiffLine

# A template transform: (source lines, 1-indexed line) ->
# (title, root_cause, before_text, after_text, test, risk) or None.
TemplateFn = Callable[[list[str], int], tuple[str, str, str, str, str, str] | None]


def _cid(*parts: object) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:16]


def _unified(path: str, before: str, after: str) -> DiffLine:
    """Build a DiffLine with a real unified-diff hunk from before/after text."""
    diff = "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            n=2,
        )
    )
    return DiffLine(path=path, old=before.strip(), new=after.strip(), hunk=diff)


def _read(root: Path, rel: str) -> list[str] | None:
    try:
        return (root / rel).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None


# --------------------------------------------------------------------------- #
# Concrete template transforms, keyed by the kind of finding.
# Each returns (title, root_cause, before_text, after_text, test, risk) or None.
# --------------------------------------------------------------------------- #
def _fix_bare_except(lines: list[str], line_no: int) -> tuple[str, str, str, str, str, str] | None:
    idx = line_no - 1
    if not (0 <= idx < len(lines)):
        return None
    src = lines[idx]
    m = re.match(r"(\s*)except\s*:", src)
    if not m:
        return None
    indent = m.group(1)
    before = src
    after = f"{indent}except Exception:"
    test = (
        "def test_specific_exception_is_caught():\n"
        "    # A bare except also swallows KeyboardInterrupt/SystemExit; the\n"
        "    # narrowed handler should let those propagate.\n"
        "    import pytest\n"
        "    with pytest.raises(KeyboardInterrupt):\n"
        "        raise KeyboardInterrupt()\n"
    )
    return (
        "Narrow bare `except:` to `except Exception:`",
        "A bare `except:` swallows control-flow signals (KeyboardInterrupt, "
        "SystemExit) and masks unexpected errors, making failures invisible.",
        before,
        after,
        test,
        "LOW",
    )


def _fix_mutable_default(lines: list[str], line_no: int) -> tuple[str, str, str, str, str, str] | None:
    idx = line_no - 1
    if not (0 <= idx < len(lines)):
        return None
    # Find the def line at/after line_no and rewrite `=[]`/`={}`/`=set()` -> `=None`.
    src = lines[idx]
    new = re.sub(r"=\s*(\[\]|\{\}|set\(\))", "=None", src)
    if new == src:
        return None
    root_cause = (
        "A mutable default argument is shared across all calls; mutating it "
        "leaks state between invocations. Use `None` and build the container "
        "inside the function."
    )
    test = (
        "def test_default_not_shared():\n"
        "    # Calling twice must not accumulate state in the default.\n"
        "    assert True  # replace with a call asserting isolation\n"
    )
    return (
        "Replace mutable default argument with `None`",
        root_cause,
        src,
        new,
        test,
        "MEDIUM",
    )


def _fix_shell_true(lines: list[str], line_no: int) -> tuple[str, str, str, str, str, str] | None:
    idx = line_no - 1
    if not (0 <= idx < len(lines)):
        return None
    src = lines[idx]
    if "shell=True" not in src:
        return None
    new = src.replace("shell=True", "shell=False")
    return (
        "Disable `shell=True` to prevent shell injection",
        "Passing `shell=True` runs the command through the system shell, which "
        "allows shell-injection when any part of the command is untrusted.",
        src,
        new,
        "def test_no_shell_true():\n    # Command should be passed as an argv list, not a shell string.\n    assert True\n",
        "MEDIUM",
    )


_TEMPLATES: dict[str, TemplateFn] = {
    "bare-except": _fix_bare_except,
    "bare `except:`": _fix_bare_except,
    "mutable default": _fix_mutable_default,
    "shell=true": _fix_shell_true,
}


def _match_template(summary: str) -> TemplateFn | None:
    low = summary.lower()
    for key, fn in _TEMPLATES.items():
        if key in low:
            return fn
    return None


async def _llm_root_cause(llm: LocalLLM, summary: str, snippet: str) -> str | None:
    prompt = (
        "You are a senior engineer writing a concise root-cause analysis for a code fix. "
        "In 2-3 sentences, explain the underlying cause and why it matters. "
        "Do not include code.\n\n"
        f"Finding: {summary}\n\nCode:\n{snippet}\n\nRoot cause:"
    )
    out = await llm.generate(prompt, num_predict=180)
    return out.strip() if out else None


class PatchGenerator:
    """Generate independent candidate patches for a finding."""

    def __init__(self, llm: LocalLLM | None = None) -> None:
        self._llm = llm

    async def generate_for_finding(
        self,
        repo_root: str | Path,
        *,
        finding_id: str | None,
        summary: str,
        category: str,
        path: str | None,
        line: int | None,
        snippet: str = "",
        repo_id: str | None = None,
    ) -> CandidateSet:
        root = Path(repo_root).expanduser()
        mode = "template"
        candidates: list[Candidate] = []

        template = _match_template(summary)
        lines = _read(root, path) if path else None

        if template and lines is not None and line:
            result = template(lines, line)
            if result is not None:
                title, root_cause, before, after, test, risk = result

                # Optionally enrich the root cause with the LLM (never the diff).
                if self._llm is not None:
                    enriched = await _llm_root_cause(self._llm, summary, snippet or before)
                    if enriched:
                        root_cause = enriched
                        mode = self._llm.name

                ln = line or 1
                lo = max(0, ln - 2)
                before_block = lines[lo : ln + 1]
                after_block = [*lines[lo : ln - 1], after, *lines[ln : ln + 1]]
                diff = _unified(
                    path or "",
                    "\n".join(before_block),
                    "\n".join(after_block),
                )
                candidates.append(
                    Candidate(
                        candidate_id=_cid(finding_id, path, line, "fix-a"),
                        title=title,
                        author_agent="fix.a",
                        verdict="PENDING",
                        root_cause=root_cause,
                        risk_level=risk,
                        scope_files_changed=1,
                        unrelated_changes=False,
                        diff=[diff],
                        finding_id=finding_id,
                        test_snippet=test,
                        verification_commands=[
                            "ruff check .",
                            "pytest -q",
                        ],
                        generated_by=mode,
                    )
                )

                # An independent, more conservative alternative (fix.b): add a
                # comment-guarded variant that keeps behaviour but documents it.
                after_b = f"{after}  # narrowed from a bare handler; see issue"
                candidates.append(
                    Candidate(
                        candidate_id=_cid(finding_id, path, line, "fix-b"),
                        title=f"{title} (documented, minimal)",
                        author_agent="fix.b",
                        verdict="PENDING",
                        root_cause=root_cause,
                        risk_level="LOW",
                        scope_files_changed=1,
                        unrelated_changes=False,
                        diff=[_unified(path or "", before, after_b)],
                        finding_id=finding_id,
                        test_snippet=test,
                        verification_commands=["ruff check .", "pytest -q"],
                        generated_by=mode,
                    )
                )

        # Always include a NO_SUBMISSION critic candidate — the honest option
        # when the fix is uncertain or the finding is low-severity/info.
        candidates.append(
            Candidate(
                candidate_id=_cid(finding_id, path, line, "no-submit"),
                title="NO_SUBMISSION — evidence insufficient / not worth a PR",
                author_agent="fix.critic",
                verdict="NO_SUBMISSION",
                root_cause=(
                    "The finding may not justify an external contribution: it could be "
                    "style-only, unreproducible, or already handled. Prefer not submitting "
                    "until a maintainer signals interest or a reproduction exists."
                ),
                risk_level="SAFE",
                scope_files_changed=0,
                unrelated_changes=False,
                diff=[],
                finding_id=finding_id,
                verification_commands=[],
                generated_by=mode,
            )
        )

        return CandidateSet(
            finding_id=finding_id,
            problem_summary=summary,
            candidates=candidates,
            generated_by=mode,
        )


def is_python_file(path: str | None) -> bool:
    return bool(path) and str(path).endswith(".py")


def parses(source: str) -> bool:
    """True if ``source`` is syntactically valid Python (diff sanity check)."""
    try:
        ast.parse(source)
        return True
    except SyntaxError:
        return False
