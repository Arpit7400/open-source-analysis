"""Hermetic patch-generation tests (no LLM, no network)."""

from __future__ import annotations

from pathlib import Path

import pytest

from patch_gen import PatchGenerator, parses
from patch_gen.models import RISK_LEVELS, VERDICTS

_BUGGY = '''\
import subprocess


def run(cmd, opts=[]):
    try:
        subprocess.run(cmd, shell=True)
    except:
        pass
'''


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "bad.py").write_text(_BUGGY, encoding="utf-8")
    return tmp_path


@pytest.mark.asyncio
async def test_bare_except_candidate_has_real_diff(repo: Path) -> None:
    gen = PatchGenerator()  # template mode, no LLM
    cset = await gen.generate_for_finding(
        repo,
        finding_id="f1",
        summary="Bare `except:` swallows all exceptions at pkg/bad.py:7.",
        category="SECURITY_SMELL",
        path="pkg/bad.py",
        line=7,
        snippet="    except:",
    )
    fix = next((c for c in cset.candidates if c.author_agent == "fix.a"), None)
    assert fix is not None
    assert fix.diff and fix.diff[0].hunk  # a real unified-diff hunk exists
    assert "except Exception" in fix.diff[0].new
    assert "@@" in fix.diff[0].hunk
    assert fix.test_snippet
    assert fix.verification_commands


@pytest.mark.asyncio
async def test_always_includes_no_submission(repo: Path) -> None:
    gen = PatchGenerator()
    cset = await gen.generate_for_finding(
        repo,
        finding_id="f1",
        summary="Some low-value style nit.",
        category="CODE_QUALITY",
        path="pkg/bad.py",
        line=4,
    )
    verdicts = {c.verdict for c in cset.candidates}
    assert "NO_SUBMISSION" in verdicts


@pytest.mark.asyncio
async def test_mutable_default_fix(repo: Path) -> None:
    gen = PatchGenerator()
    cset = await gen.generate_for_finding(
        repo,
        finding_id="f2",
        summary="Mutable default argument in `run` at pkg/bad.py:4.",
        category="CODE_QUALITY",
        path="pkg/bad.py",
        line=4,
    )
    fix = next((c for c in cset.candidates if c.author_agent == "fix.a"), None)
    assert fix is not None
    assert "=None" in fix.diff[0].new


@pytest.mark.asyncio
async def test_candidates_match_contract_enums(repo: Path) -> None:
    gen = PatchGenerator()
    cset = await gen.generate_for_finding(
        repo,
        finding_id="f1",
        summary="Bare `except:` at pkg/bad.py:7.",
        category="SECURITY_SMELL",
        path="pkg/bad.py",
        line=7,
    )
    assert cset.candidates
    for c in cset.candidates:
        assert c.verdict in VERDICTS
        assert c.risk_level in RISK_LEVELS
        assert c.candidate_id and c.author_agent


@pytest.mark.asyncio
async def test_deterministic_without_llm(repo: Path) -> None:
    gen = PatchGenerator()
    kw = dict(
        finding_id="f1",
        summary="Bare `except:` at pkg/bad.py:7.",
        category="SECURITY_SMELL",
        path="pkg/bad.py",
        line=7,
    )
    a = await gen.generate_for_finding(repo, **kw)
    b = await gen.generate_for_finding(repo, **kw)
    assert [c.candidate_id for c in a.candidates] == [c.candidate_id for c in b.candidates]


def test_parses_helper() -> None:
    assert parses("x = 1\n")
    assert not parses("def (:\n")
