# runtime_investigation — CareerForge AI Phase 7

Runs a repository's runtime steps **safely**, through the gated Phase 6 sandbox.

- **Environment detection** (`detect_environment`) — read-only: pyproject /
  setup.py / requirements, tests presence + runner, declared Python version.
- **Investigator** (`RuntimeInvestigator`) — plans install → import check →
  tests → lint → type, runs each via `sandbox.SandboxRunner`, and turns
  failures into typed RUNTIME findings with a reproduction status.

Safety: a HIGH-risk static preflight refuses runtime work outright. Nothing
executes unless the `repository_execution` flag is on AND a container engine is
present AND each command passes the policy engine. When execution is disabled
(the default), it returns a complete **planned** report (environment + the steps
it would run, each `executed=False`) — so the pipeline is testable everywhere
and does real container work on the user's machine when armed.

```python
from runtime_investigation import RuntimeInvestigator
report = RuntimeInvestigator(execution_flag_enabled=False).investigate(repo)
print(report.environment, report.reproduction_status)
```
