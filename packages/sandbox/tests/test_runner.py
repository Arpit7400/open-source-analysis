"""Runner tests: hardening posture (pure) + gating (no Docker needed)."""

from __future__ import annotations

from pathlib import Path

from sandbox import SandboxRunner, build_run_args
from sandbox.models import ResourceLimits


def test_build_run_args_is_hardened(tmp_path: Path) -> None:
    args = build_run_args(
        "docker",
        "python:3.12-slim",
        str(tmp_path),
        ["python", "-m", "pytest", "-q"],
        ResourceLimits(),
    )
    joined = " ".join(args)
    # non-root, caps dropped, no new privileges
    assert "--user" in args and "65534:65534" in args
    assert "--cap-drop" in args and "ALL" in args
    assert "no-new-privileges" in joined
    # read-only root + bounded tmpfs
    assert "--read-only" in args
    assert any("tmpfs" in a or a == "--tmpfs" for a in args)
    # repo mounted READ-ONLY
    assert any(a.startswith("type=bind") and a.endswith(",ro") for a in args)
    # network disabled by default (test stage)
    assert "none" in args
    # resource limits present
    assert "--memory" in args and "--cpus" in args and "--pids-limit" in args
    # NO host secret / socket mounts
    assert "/var/run/docker.sock" not in joined
    assert ".ssh" not in joined
    assert "docker.sock" not in joined


def test_install_stage_allows_network(tmp_path: Path) -> None:
    args = build_run_args(
        "docker", "img", str(tmp_path), ["pip", "install", "x"],
        ResourceLimits(network=True),
    )
    assert "bridge" in args
    assert "none" not in args


def test_execution_disabled_by_default(tmp_path: Path) -> None:
    runner = SandboxRunner(execution_flag_enabled=False)
    ok, why = runner.can_execute()
    assert ok is False
    assert "flag disabled" in why
    rec = runner.run_command(str(tmp_path), ["python", "-m", "pytest"])
    assert rec.exit_code is None  # not executed
    assert "EXECUTION DISABLED" in rec.stderr


def test_policy_denied_command_never_runs(tmp_path: Path) -> None:
    runner = SandboxRunner(execution_flag_enabled=True)
    rec = runner.run_command(str(tmp_path), ["rm", "-rf", "/"])
    assert rec.exit_code is None
    assert "POLICY DENIED" in rec.stderr
