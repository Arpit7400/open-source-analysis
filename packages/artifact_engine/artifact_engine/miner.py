"""Contribution opportunity miner (Phase 13).

Ranks candidate repositories and scoped contribution types by how well they fit
the user's skill evidence and how healthy/maintainable the repo looks. Scoring
is deterministic and explainable.

Inputs are plain dicts (or RepoSignal) so the miner is decoupled from the
GitHub client; the API layer fetches real repo metadata and maps it in.
"""

from __future__ import annotations

from collections.abc import Iterable

from artifact_engine.models import Opportunity, OpportunityReport, RepoSignal

# Contribution types that are realistic entry points, ordered from lowest to
# highest barrier. The miner recommends the *easiest useful* type a repo needs.
_CONTRIB_ORDER = ("DOCS", "TEST", "TYPING", "BUGFIX", "REFACTOR", "FEATURE")


def _maintainability(sig: RepoSignal) -> float:
    """Health score in [0,1]: active, not archived, reasonable issue load, tested."""
    if sig.archived:
        return 0.0
    score = 0.0
    score += 0.35 if sig.recent_activity else 0.0
    score += 0.2 if sig.has_contributing_guide else 0.0
    score += 0.2 if sig.has_tests else 0.0
    # a moderate open-issue count signals a live but not-abandoned project
    if 1 <= sig.open_issues <= 400:
        score += 0.15
    # popularity gives a small, saturating bump
    score += min(0.1, sig.stars / 100_000)
    return round(min(1.0, score), 4)


def _fit(sig: RepoSignal, user_skills: set[str]) -> tuple[float, list[str]]:
    """Skill fit in [0,1] plus the matched skills."""
    lang = (sig.language or "").lower()
    matched = sorted(s for s in user_skills if s and (s.lower() == lang or s.lower() in lang))
    base = 0.6 if matched else 0.15
    # tested repos are easier to contribute to safely -> better fit for a newcomer
    base += 0.2 if sig.has_tests else 0.0
    base += 0.1 if sig.has_contributing_guide else 0.0
    return round(min(1.0, base), 4), matched


def _recommend_type(sig: RepoSignal) -> tuple[str, str]:
    """Pick the easiest useful contribution type and explain why."""
    if not sig.has_contributing_guide:
        return "DOCS", "no contributing guide — docs improvements are welcome and low-risk"
    if not sig.has_tests:
        return "TEST", "no tests detected — adding coverage is high-value and low-risk"
    if sig.open_issues > 0:
        return "BUGFIX", "has open issues — a small, reproducible bugfix is a strong first PR"
    return "TYPING", "healthy repo — type-annotation or small refactor improvements fit well"


def mine_opportunities(
    repos: Iterable[dict[str, object] | RepoSignal],
    user_skills: Iterable[str],
    limit: int = 10,
) -> OpportunityReport:
    """Rank ``repos`` as contribution opportunities for ``user_skills``."""
    skills = {str(s).strip() for s in user_skills if str(s).strip()}
    opps: list[Opportunity] = []
    for raw in repos:
        sig = raw if isinstance(raw, RepoSignal) else RepoSignal(**raw)  # type: ignore[arg-type]
        maint = _maintainability(sig)
        if maint == 0.0:  # archived / abandoned -> skip
            continue
        fit, matched = _fit(sig, skills)
        ctype, why = _recommend_type(sig)
        rank = round(0.6 * fit + 0.4 * maint, 4)
        opps.append(
            Opportunity(
                repo=sig.full_name,
                url=f"https://github.com/{sig.full_name}",
                contribution_type=ctype,
                fit_score=fit,
                maintainability_score=maint,
                rank_score=rank,
                matched_skills=matched,
                rationale=(
                    f"Fit {fit:.0%} (skills: {', '.join(matched) or 'none direct'}), "
                    f"maintainability {maint:.0%}. Suggested: {ctype} — {why}."
                ),
            )
        )
    opps.sort(key=lambda o: (-o.rank_score, o.repo))
    return OpportunityReport(opportunities=opps[: max(0, limit)])
