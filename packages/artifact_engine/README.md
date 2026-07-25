# artifact_engine — CareerForge AI Phase 13

Two capabilities:

**Skill-to-artifact engine** — turns a verified skill gap into a concrete,
evidence-producing project assignment: problem statement, prerequisites,
architecture, milestones with acceptance criteria, tests, an evaluation rubric,
a demo, a README outline, a portfolio blurb, an effort estimate, and the exact
evidence it will produce. Prefers building/testing/documenting over passive study.

```python
from artifact_engine import assignments_for_skills
skills = [{"name": "RAG systems", "confidence": 0.4}]
assignments = assignments_for_skills(skills)   # deterministic
```

**Opportunity miner** — ranks candidate repositories and scoped contribution
types (DOCS / TEST / TYPING / BUGFIX / REFACTOR / FEATURE) by skill fit and
maintainability signals (activity, tests, contributing guide, issue load).
Archived/abandoned repos are skipped. Explainable, deterministic scoring.

```python
from artifact_engine import mine_opportunities
report = mine_opportunities(repo_signals, user_skills=["Python"])
```

Deterministic — testable with no network or model.
