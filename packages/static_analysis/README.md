# static_analysis — CareerForge AI Phase 5

Real static-analysis agents that produce typed `Finding` objects (matching the
API contract) with exact `path:line` evidence.

- **AST agents** (no external tools, cross-platform): `static.security` (bare
  except, eval/exec, `shell=True`, `verify=False`), `static.code_quality`
  (mutable defaults, long functions, TODO/FIXME), `static.typing` (missing
  return annotations), `static.docs_drift` (missing docstrings),
  `static.test_quality` (no tests present).
- **Tool agents** (run real `ruff` / `mypy` when installed): `static.ruff`,
  `static.mypy`. Degrade to an `ok` note when the tool is absent — never fabricate.

```python
from static_analysis import analyze_repository
result = analyze_repository("/path/to/repo", repo_id="owner/name", include_tools=True)
for f in result.findings:
    print(f.agent_id, f.severity, f.summary)
```

Tests are hermetic (a bundled buggy fixture; `include_tools=False`).
