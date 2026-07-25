"""Command policy engine (handbook §8.1: allowlisted command patterns).

Any command that will run inside the sandbox — including one proposed by an LLM
— MUST pass this policy first. The policy is an allowlist: only known-safe
program invocations for the supported (Python) toolchain are permitted, and a
denylist of dangerous tokens is rejected even inside otherwise-allowed commands.

Deterministic and independent of the model, so a compromised or hallucinating
agent cannot widen its own permissions.
"""

from __future__ import annotations

from sandbox.models import PolicyDecision

# Allowed leading programs and the subcommands/args permitted for each.
_ALLOWED: dict[str, set[str]] = {
    "python": set(),      # e.g. python -m pytest / -m pip (further checked below)
    "python3": set(),
    "pytest": set(),
    "ruff": {"check", "format", "--version"},
    "mypy": set(),
    "pyright": set(),
    "pip": {"install", "list", "show", "--version"},
    "uv": {"pip", "sync", "run", "--version"},
    "coverage": {"run", "report", "xml"},
}

# Modules permitted after ``python -m``.
_ALLOWED_PY_MODULES = {"pytest", "pip", "mypy", "ruff", "coverage", "unittest", "build"}

# Tokens that are NEVER allowed anywhere in a command (defence in depth).
# NOTE: the shell builtins ``source``/``.`` are only dangerous as the *program*
# (argv[0]); a bare ``.`` argument legitimately means "current directory" for
# e.g. ``ruff check .`` / ``pip install -e .``, so those are handled by the
# program-position check below, not this any-position denylist.
_DENY_TOKENS = {
    "sudo", "su", "chmod", "chown", "curl", "wget", "nc", "ncat", "ssh", "scp",
    "rm", "rmdir", "mv", "dd", "mkfs", "kill", "pkill", "reboot", "shutdown",
    "docker", "podman", "systemctl", "apt", "apt-get", "yum", "brew",
    "eval", "exec",
}

# Programs that must never appear at argv[0] (shell builtins / sourcing).
_DENY_PROGRAMS = {"source", ".", "sh", "bash", "zsh", "fish", "cmd", "powershell"}

# Shell metacharacters that indicate an attempt to chain/redirect/expand.
_SHELL_METACHARS = {"&&", "||", "|", ";", ">", ">>", "<", "`", "$(", "&"}


def validate_command(command: list[str]) -> PolicyDecision:
    """Return whether ``command`` (an argv list) is allowed in the sandbox."""
    if not command or not isinstance(command, list):
        return PolicyDecision(command=command or [], allowed=False, reason="empty or malformed command")

    # Reject shell metacharacters anywhere (argv should be a plain program call).
    for tok in command:
        for meta in _SHELL_METACHARS:
            if meta in tok:
                return PolicyDecision(
                    command=command, allowed=False, reason=f"shell metacharacter not allowed: {meta!r}"
                )

    # Reject denied tokens anywhere in the command.
    lowered = [t.lower() for t in command]
    for t in lowered:
        base = t.rsplit("/", 1)[-1]  # normalise /usr/bin/rm -> rm
        if base in _DENY_TOKENS:
            return PolicyDecision(command=command, allowed=False, reason=f"denied program/token: {base!r}")

    program = command[0].rsplit("/", 1)[-1].lower()
    if program in _DENY_PROGRAMS:
        return PolicyDecision(command=command, allowed=False, reason=f"shell/builtin program not allowed: {program!r}")
    if program not in _ALLOWED:
        return PolicyDecision(command=command, allowed=False, reason=f"program not on allowlist: {program!r}")

    # python/python3 -m <module> must target an allowed module.
    if program in {"python", "python3"}:
        if len(command) >= 3 and command[1] == "-m":
            module = command[2].split(".", 1)[0]
            if module not in _ALLOWED_PY_MODULES:
                return PolicyDecision(
                    command=command, allowed=False, reason=f"python module not allowed: {module!r}"
                )
            return PolicyDecision(command=command, allowed=True, reason=f"allowed: python -m {module}")
        # bare `python script.py` is allowed (runs inside the sandbox anyway)
        return PolicyDecision(command=command, allowed=True, reason="allowed: python invocation")

    # For programs with a required subcommand set, check the first arg.
    allowed_subs = _ALLOWED[program]
    if allowed_subs and (len(command) < 2 or command[1] not in allowed_subs):
        return PolicyDecision(
            command=command,
            allowed=False,
            reason=f"{program} subcommand not allowed (expected one of {sorted(allowed_subs)})",
        )
    return PolicyDecision(command=command, allowed=True, reason=f"allowed: {program}")


def validate_all(commands: list[list[str]]) -> list[PolicyDecision]:
    """Validate a batch of commands, returning one decision each."""
    return [validate_command(c) for c in commands]
