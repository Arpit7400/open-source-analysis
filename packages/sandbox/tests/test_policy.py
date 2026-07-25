"""Command policy engine tests — the allowlist must hold."""

from __future__ import annotations

import pytest

from sandbox import validate_command


@pytest.mark.parametrize(
    "cmd",
    [
        ["python", "-m", "pytest", "-q"],
        ["python3", "-m", "pip", "install", "-e", "."],
        ["pytest", "-q"],
        ["ruff", "check", "."],
        ["mypy", "-p", "pkg"],
        ["pip", "install", "requests"],
    ],
)
def test_allowed_commands(cmd: list[str]) -> None:
    assert validate_command(cmd).allowed, cmd


@pytest.mark.parametrize(
    "cmd",
    [
        ["rm", "-rf", "/"],
        ["curl", "http://evil"],
        ["sudo", "pytest"],
        ["python", "-c", "import os; os.system('x')"],   # -c not -m
        ["python", "-m", "os"],                           # module not allowed
        ["bash", "-c", "echo hi"],                        # program not allowed
        ["pytest", "&&", "rm", "-rf", "."],               # metachar
        ["pytest", ";", "curl", "x"],                     # metachar
        ["ruff", "nonsense"],                             # bad subcommand
        ["docker", "run", "x"],                           # denied token
        [],                                               # empty
    ],
)
def test_denied_commands(cmd: list[str]) -> None:
    decision = validate_command(cmd)
    assert not decision.allowed, cmd
    assert decision.reason


def test_llm_cannot_smuggle_shell_pipe() -> None:
    # A plausible "innocent" command with a pipe must be rejected.
    d = validate_command(["python", "-m", "pytest", "|", "tee", "log"])
    assert not d.allowed
    assert "metacharacter" in d.reason
