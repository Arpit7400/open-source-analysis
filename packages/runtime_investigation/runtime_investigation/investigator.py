"""Runtime investigation orchestrator (Phase 7).

Plans a sequence of runtime steps for a repository (install -> import check ->
tests -> lint -> type), runs each through the **gated** sandbox (Phase 6), and
turns the results into typed runtime findings + a reproduction report.

Everything runs through ``sandbox.SandboxRunner``, so:
* nothing executes unless the ``repository_execution`` flag is on AND a
  container engine is present AND the command passes the policy engine;
* when execution is disabled (the default), the investigator still returns a
  complete PLANNED report (environment + the steps it *would* run, each marked
  ``executed=False`` with the refusal reason) — so the pipeline is exercisable
  and testable everywhere, and does real work on the user's machine when armed.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from sandbox import SandboxRunner, run_preflight
from sandbox.models import ResourceLimits

from runtime_investigation.detect import detect_environment
from runtime_investigation.models import (
    RuntimeFinding,
    RuntimeReport,
    RuntimeStep,
)


def _fid(*parts: object) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:16]


# The planned step sequence. install runs first (network allowed there only);
# the rest run with network disabled.
def _plan_steps(env_has_requirements: bool, env_has_tests: bool) -> list[tuple[str, list[str]]]:
    steps: list[tuple[str, list[str]]] = []
    if env_has_requirements:
        steps.append(("install", ["pip", "install", "-e", "."]))
    steps.append(("import_check", ["python", "-m", "pip", "list"]))
    if env_has_tests:
        steps.append(("tests", ["python", "-m", "pytest", "-q"]))
    steps.append(("lint", ["ruff", "check", "."]))
    steps.append(("type", ["mypy", "-p", "."]))
    return steps


class RuntimeInvestigator:
    """Runs (or plans) sandboxed runtime steps and produces findings."""

    def __init__(
        self,
        execution_flag_enabled: bool = False,
        image: str = "python:3.12-slim",
        limits: ResourceLimits | None = None,
    ) -> None:
        self._runner = SandboxRunner(
            image=image,
            limits=limits or ResourceLimits(),
            execution_flag_enabled=execution_flag_enabled,
        )
        self._flag = execution_flag_enabled

    def investigate(self, repo_path: str | Path) -> RuntimeReport:
        root = Path(repo_path).expanduser()
        if not root.is_dir():
            raise NotADirectoryError(f"repo_path is not a directory: {repo_path}")

        env = detect_environment(root)

        # Safety gate: a HIGH-risk preflight blocks runtime work outright.
        pre = run_preflight(root, execution_flag_enabled=self._flag)
        if pre.risk_level == "BLOCKED":
            return RuntimeReport(
                repo_path=str(root),
                executed=False,
                reason="Static preflight BLOCKED this repository — runtime investigation refused.",
                environment=env,
                reproduction_status="NOT_REQUIRED",
            )

        can_execute, why = self._runner.can_execute()
        steps_out: list[RuntimeStep] = []
        findings: list[RuntimeFinding] = []

        for name, command in _plan_steps(env.has_requirements, env.has_tests):
            rec = self._runner.run_command(str(root), command, stage=_stage_for(name))
            executed = rec.exit_code is not None and not rec.stderr.startswith(
                ("POLICY DENIED", "EXECUTION DISABLED")
            )
            passed = (rec.exit_code == 0) if executed else None
            step = RuntimeStep(
                name=name,
                command=command,
                executed=executed,
                exit_code=rec.exit_code,
                passed=passed,
                duration_ms=rec.duration_ms,
                summary=(
                    f"{name}: {'passed' if passed else 'failed' if passed is False else 'not executed'}"
                ),
                stdout_tail=rec.stdout[-1000:],
                stderr_tail=rec.stderr[-1000:],
            )
            steps_out.append(step)

            # A failing executed step becomes a reproduced runtime finding.
            if executed and passed is False:
                findings.append(
                    RuntimeFinding(
                        finding_id=_fid(str(root), name, rec.exit_code),
                        severity="HIGH" if name in ("tests", "import_check") else "MEDIUM",
                        confidence=0.85,
                        summary=f"Runtime step '{name}' failed (exit {rec.exit_code}).",
                        evidence=[{"step": name, "command": command, "stderr_tail": rec.stderr[-400:]}],
                        reproduction_required=True,
                        reproduction_status="REPRODUCED",
                        suggested_next_step=f"Investigate the '{name}' failure; see stderr for the first error.",
                        limitations=["Ran in an isolated container; environment may differ from maintainer CI."],
                    )
                )

        executed_any = any(s.executed for s in steps_out)
        repro = "REPRODUCED" if findings else ("NOT_REPRODUCED" if executed_any else "PENDING")
        reason = "ok" if can_execute else why

        return RuntimeReport(
            repo_path=str(root),
            executed=executed_any,
            reason=reason,
            environment=env,
            steps=steps_out,
            findings=findings,
            reproduction_status=repro,
        )


def _stage_for(step_name: str) -> str:
    return "install" if step_name == "install" else step_name
