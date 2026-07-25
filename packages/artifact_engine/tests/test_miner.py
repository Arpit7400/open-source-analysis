"""Tests for the contribution opportunity miner."""

from __future__ import annotations

from artifact_engine import RepoSignal, mine_opportunities

_REPOS = [
    # A healthy, tested Python repo with a contributing guide -> strong fit.
    {
        "full_name": "acme/weblib",
        "language": "Python",
        "stars": 3000,
        "open_issues": 40,
        "has_tests": True,
        "has_contributing_guide": True,
        "archived": False,
        "recent_activity": True,
    },
    # A repo with no tests -> miner should suggest TEST.
    {
        "full_name": "acme/untested",
        "language": "Python",
        "stars": 200,
        "open_issues": 5,
        "has_tests": False,
        "has_contributing_guide": True,
        "archived": False,
        "recent_activity": True,
    },
    # Archived -> must be skipped entirely.
    {
        "full_name": "acme/dead",
        "language": "Python",
        "stars": 10,
        "open_issues": 0,
        "has_tests": True,
        "has_contributing_guide": True,
        "archived": True,
        "recent_activity": False,
    },
    # A non-Python repo -> lower fit for a Python user.
    {
        "full_name": "acme/rustthing",
        "language": "Rust",
        "stars": 5000,
        "open_issues": 20,
        "has_tests": True,
        "has_contributing_guide": True,
        "archived": False,
        "recent_activity": True,
    },
]


def test_archived_repos_skipped() -> None:
    report = mine_opportunities(_REPOS, user_skills=["Python"])
    names = [o.repo for o in report.opportunities]
    assert "acme/dead" not in names


def test_python_repo_ranks_above_rust_for_python_user() -> None:
    report = mine_opportunities(_REPOS, user_skills=["Python"])
    names = [o.repo for o in report.opportunities]
    assert names.index("acme/weblib") < names.index("acme/rustthing")


def test_untested_repo_suggests_test_contribution() -> None:
    report = mine_opportunities(_REPOS, user_skills=["Python"])
    untested = next(o for o in report.opportunities if o.repo == "acme/untested")
    assert untested.contribution_type == "TEST"


def test_scores_in_range_and_explained() -> None:
    report = mine_opportunities(_REPOS, user_skills=["Python"])
    assert report.opportunities
    for o in report.opportunities:
        assert 0.0 <= o.fit_score <= 1.0
        assert 0.0 <= o.maintainability_score <= 1.0
        assert 0.0 <= o.rank_score <= 1.0
        assert o.rationale
        assert o.contribution_type in ("DOCS", "TEST", "TYPING", "BUGFIX", "REFACTOR", "FEATURE")


def test_accepts_reposignal_objects() -> None:
    sig = RepoSignal(full_name="x/y", language="Python", has_tests=True, recent_activity=True)
    report = mine_opportunities([sig], user_skills=["Python"])
    assert report.opportunities[0].repo == "x/y"
