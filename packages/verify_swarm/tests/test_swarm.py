"""End-to-end Phase 9 -> Phase 10 verification tests (hermetic)."""

from __future__ import annotations

from pathlib import Path

import pytest
from patch_gen import PatchGenerator
from patch_gen.models import Candidate, DiffLine

from verify_swarm import verify_candidate, verify_candidates

_BUGGY = '''\
def run(cmd):
    try:
        do_work(cmd)
    except:
        pass
'''


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "bad.py").write_text(_BUGGY, encoding="utf-8")
    return tmp_path


@pytest.mark.asyncio
async def test_good_candidate_is_accepted(repo: Path) -> None:
    gen = PatchGenerator()  # template mode
    cset = await gen.generate_for_finding(
        repo,
        finding_id="f1",
        summary="Bare `except:` at bad.py:4.",
        category="SECURITY_SMELL",
        path="bad.py",
        line=4,
        snippet="    except:",
    )
    fix = next(c for c in cset.candidates if c.author_agent == "fix.a")
    verified = verify_candidate(repo, fix)
    assert verified.verdict == "ACCEPTED"
    assert verified.verification, "expected verification checks"
    # independence: no verifier is the author
    assert all(v.verifier_agent != fix.author_agent for v in verified.verification)
    assert all(v.verifier_agent.startswith("verify.") for v in verified.verification)


def test_broken_patch_is_rejected(repo: Path) -> None:
    # A candidate whose diff produces invalid Python must be REJECTED by syntax.
    bad = Candidate(
        candidate_id="x",
        title="broken",
        author_agent="fix.a",
        verdict="PENDING",
        root_cause="stated",
        risk_level="LOW",
        scope_files_changed=1,
        diff=[DiffLine(path="bad.py", old="    except:", new="    except:::", hunk="@@")],
        test_snippet="def test_x():\n    assert True\n",
    )
    verified = verify_candidate(repo, bad)
    assert verified.verdict == "REJECTED"
    syntax = next(v for v in verified.verification if v.check == "syntax")
    assert syntax.status == "FAIL"


def test_no_submission_stays_no_submission(repo: Path) -> None:
    critic = Candidate(
        candidate_id="ns",
        title="NO_SUBMISSION",
        author_agent="fix.critic",
        verdict="NO_SUBMISSION",
        root_cause="insufficient evidence",
        risk_level="SAFE",
        diff=[],
    )
    verified = verify_candidate(repo, critic)
    assert verified.verdict == "NO_SUBMISSION"


def test_unrelated_changes_flagged_as_rejected(repo: Path) -> None:
    cand = Candidate(
        candidate_id="u",
        title="wide",
        author_agent="fix.a",
        verdict="PENDING",
        root_cause="x",
        risk_level="LOW",
        scope_files_changed=1,
        unrelated_changes=True,
        diff=[DiffLine(path="bad.py", old="    except:", new="    except Exception:", hunk="@@")],
        test_snippet="def test():\n    assert True\n",
    )
    verified = verify_candidate(repo, cand)
    assert verified.verdict == "REJECTED"
    scope = next(v for v in verified.verification if v.check == "scope")
    assert scope.status == "FAIL"


@pytest.mark.asyncio
async def test_verify_candidates_batch_mixed(repo: Path) -> None:
    gen = PatchGenerator()
    cset = await gen.generate_for_finding(
        repo,
        finding_id="f1",
        summary="Bare `except:` at bad.py:4.",
        category="SECURITY_SMELL",
        path="bad.py",
        line=4,
    )
    verified = verify_candidates(repo, cset.candidates)
    verdicts = {c.verdict for c in verified}
    # the set should contain at least one ACCEPTED (fix.a/fix.b) and the NO_SUBMISSION
    assert "ACCEPTED" in verdicts
    assert "NO_SUBMISSION" in verdicts
