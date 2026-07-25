# verify_swarm — CareerForge AI Phase 10

Independent verification swarm for candidate patches. Given a `patch_gen`
`Candidate`, runs five independent `verify.*` agents (never the patch author):

- `verify.syntax` — patched file still parses.
- `verify.scope` — single file, small change, no unrelated edits.
- `verify.lint` — ruff no worse on the patched file (SKIP if ruff absent).
- `verify.type` — mypy no worse on the patched file (SKIP if mypy absent).
- `verify.adversarial` — a skeptic; rejects empty/no-op diffs, missing root
  cause, or missing test.

A deterministic **quality gate** then sets the verdict:
`ACCEPTED | REJECTED | NO_SUBMISSION`. Any critical FAIL (syntax/scope/
adversarial) or any lint/type regression -> REJECTED.

Enforces the handbook rule that **authors do not verify their own output**:
every `verifier_agent` differs from the candidate's `author_agent`.

```python
from verify_swarm import verify_candidates
verified = verify_candidates(repo_root, candidates)   # candidates from patch_gen
accepted = [c for c in verified if c.verdict == "ACCEPTED"]
```
