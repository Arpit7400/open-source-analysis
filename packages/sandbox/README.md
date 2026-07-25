# sandbox — CareerForge AI Phase 6

Restricted execution for untrusted repositories. Three layers, all gated:

1. **Static safety preflight** (`run_preflight`) — read-only scan for install
   hooks, network access, destructive commands, credential access, traversal,
   suspicious subprocess use, and obfuscation. HIGH-risk => execution blocked,
   human review required. No code runs during the scan.
2. **Command policy engine** (`validate_command`) — an allowlist; only known
   Python-toolchain invocations are permitted, shell metacharacters and a
   denylist (rm, curl, sudo, docker, …) are rejected. Even LLM-proposed
   commands must pass, so an agent cannot widen its own permissions.
3. **Hardened container runner** (`SandboxRunner`) — non-root, `--cap-drop ALL`,
   `no-new-privileges`, read-only rootfs + bounded tmpfs, repo mounted
   **read-only**, no host home/SSH/token/Docker-socket mounts, CPU/memory/PID/
   wall-clock limits, and `--network none` during tests.

**Execution is OFF by default** (`repository_execution` flag). The runner
no-ops with a clear reason when the flag is off or no container engine is
present, so the package is safe to import and test anywhere. `build_run_args`
is a pure function so the hardening posture is unit-tested without Docker.

```python
from sandbox import run_preflight, SandboxRunner
pre = run_preflight(repo, execution_flag_enabled=False)   # -> execution_allowed False
runner = SandboxRunner(execution_flag_enabled=True)
rec = runner.run_command(repo, ["python", "-m", "pytest", "-q"], stage="test")
```
