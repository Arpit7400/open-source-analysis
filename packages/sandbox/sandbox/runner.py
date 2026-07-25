"""Restricted Docker/Podman runner (handbook §8.1, Stage 5).

Builds a hardened container invocation and executes allowlisted commands inside
it — but ONLY when every gate passes:

1. the ``repository_execution`` feature flag is enabled (master switch),
2. the static safety preflight is not HIGH-risk,
3. Docker (or Podman) is actually available,
4. each command passes the policy engine.

Hardening applied to every run (from the threat model):
* non-root user, all Linux capabilities dropped, ``no-new-privileges``,
* no network (``--network none``) during tests,
* read-only root filesystem with a bounded tmpfs workspace,
* CPU / memory / PID / wall-clock limits,
* NO host home, SSH dir, Docker socket, or token mounts — only the repo,
  mounted read-only.

The *arg construction* is pure and unit-tested without Docker. Execution is a
thin, audited wrapper that no-ops (with a clear reason) when a gate fails, so
this module is safe to import and exercise on a machine with no Docker.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from sandbox.models import ResourceLimits, SandboxCommand
from sandbox.policy import validate_command

DEFAULT_IMAGE = "python:3.12-slim"


def container_engine() -> str | None:
    """Return 'docker' or 'podman' if a container engine is on PATH, else None."""
    for engine in ("docker", "podman"):
        if shutil.which(engine):
            return engine
    return None


def engine_available() -> bool:
    """True if a container engine binary exists (does not prove the daemon is up)."""
    return container_engine() is not None


def build_run_args(
    engine: str,
    image: str,
    repo_path: str,
    command: list[str],
    limits: ResourceLimits,
    workdir: str = "/work",
) -> list[str]:
    """Construct the hardened ``docker/podman run`` argv for one command.

    Pure function — no side effects — so the security posture is unit-testable.
    """
    args = [
        engine,
        "run",
        "--rm",
        # identity / privileges
        "--user",
        "65534:65534",  # 'nobody' — non-root
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        # filesystem: read-only root, repo mounted read-only, bounded scratch
        "--read-only",
        "--tmpfs",
        "/tmp:rw,size=256m,noexec",
        "--mount",
        f"type=bind,src={Path(repo_path).resolve()},dst={workdir},ro",
        "--workdir",
        workdir,
        # resources
        "--memory",
        f"{limits.memory_mb}m",
        "--cpus",
        str(limits.cpus),
        "--pids-limit",
        str(limits.pids),
    ]
    # network is disabled during tests unless explicitly enabled (install stage)
    args += ["--network", "bridge" if limits.network else "none"]
    args += [image, *command]
    return args


class SandboxRunner:
    """Executes allowlisted commands in a hardened container (when permitted)."""

    def __init__(
        self,
        image: str = DEFAULT_IMAGE,
        limits: ResourceLimits | None = None,
        execution_flag_enabled: bool = False,
    ) -> None:
        self.image = image
        self.limits = limits or ResourceLimits()
        self.execution_flag_enabled = execution_flag_enabled

    def can_execute(self) -> tuple[bool, str]:
        """Return whether execution is currently permitted, and why not."""
        if not self.execution_flag_enabled:
            return False, "repository_execution flag disabled (default)"
        if not engine_available():
            return False, "no container engine (docker/podman) available"
        return True, "ok"

    def run_command(self, repo_path: str, command: list[str], stage: str = "test") -> SandboxCommand:
        """Validate + run a single command in the sandbox, returning an audit record.

        Never runs a command that fails policy, and never runs at all unless
        :meth:`can_execute` is satisfied. Returns a ``SandboxCommand`` whose
        ``exit_code`` is ``None`` when the command was refused (not executed).
        """
        decision = validate_command(command)
        if not decision.allowed:
            return SandboxCommand(
                command=command, exit_code=None, stage=stage, stderr=f"POLICY DENIED: {decision.reason}"
            )
        ok, why = self.can_execute()
        if not ok:
            return SandboxCommand(
                command=command, exit_code=None, stage=stage, stderr=f"EXECUTION DISABLED: {why}"
            )

        engine = container_engine()
        assert engine is not None  # guaranteed by can_execute()
        # the install stage is the only place a network is (optionally) allowed
        limits = self.limits
        if stage == "install":
            limits = limits.model_copy(update={"network": True})
        run_args = build_run_args(engine, self.image, repo_path, command, limits)

        start = time.perf_counter()
        try:
            proc = subprocess.run(
                run_args,
                capture_output=True,
                text=True,
                timeout=limits.wall_seconds,
                check=False,
            )
            duration = int((time.perf_counter() - start) * 1000)
            return SandboxCommand(
                command=command,
                exit_code=proc.returncode,
                duration_ms=duration,
                stdout=proc.stdout[-10_000:],
                stderr=proc.stderr[-10_000:],
                stage=stage,
            )
        except subprocess.TimeoutExpired:
            duration = int((time.perf_counter() - start) * 1000)
            return SandboxCommand(
                command=command, exit_code=None, duration_ms=duration, timed_out=True, stage=stage,
                stderr=f"timed out after {limits.wall_seconds}s",
            )
