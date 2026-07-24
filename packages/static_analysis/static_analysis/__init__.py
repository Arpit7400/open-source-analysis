"""Real static-analysis agents for CareerForge AI (Phase 5).

Deterministic AST agents + tool-backed ruff/mypy agents that produce typed
:class:`Finding` objects matching the API contract, with exact ``path:line``
evidence. Replaces the simulated static swarm with real analysis.
"""

from __future__ import annotations

from static_analysis.ast_agents import run_ast_agents
from static_analysis.models import AgentReport, AnalysisResult, EvidenceRef, Finding
from static_analysis.runner import analyze_repository
from static_analysis.tool_agents import run_mypy_agent, run_ruff_agent

__all__ = [
    "AgentReport",
    "AnalysisResult",
    "EvidenceRef",
    "Finding",
    "analyze_repository",
    "run_ast_agents",
    "run_mypy_agent",
    "run_ruff_agent",
]
