"""Retrieval domains for the RAG subsystem (handbook §5.1).

The six collection names are **FIXED** by ``docs/RAG_CONTRACT.md`` and are used
verbatim as Qdrant collection names. Do not rename, alias, or reorder them —
every track (indexer, retriever, pipeline, API layer) keys off these strings.

Per-domain metadata field notes
--------------------------------
Each domain populates the :class:`rag_core.models.Chunk` provenance fields with
slightly different emphasis. The notes below document the *expected* fields for
each domain so indexers stay consistent. They are advisory (all provenance
fields are optional on :class:`Chunk`), not enforced at the type level.

``profile_evidence``
    User's own evidence (commits, tests, docs, PRs, projects) that back skill
    claims. Expect: ``source_id`` = evidence id, ``source_type`` = ``EVIDENCE``,
    ``canonical_url``, ``published_at``.

``industry_sources``
    External industry pulse material (arXiv papers, blogs, advisories, GitHub
    releases). Expect: ``source_type`` in ``{PAPER, RELEASE, DOC}``,
    ``canonical_url``, ``published_at``, ``version``.

``repository_code``
    Implementation and test source extracted by the AST chunker. Expect:
    ``source_id`` = ``owner/name``, ``source_type`` in ``{CODE, TEST}``,
    ``path``, ``symbol``, ``start_line``, ``end_line``, ``language``,
    ``imports``, ``commit``.

``repository_docs``
    Markdown/README/doc-section chunks from a repository. Expect:
    ``source_id`` = ``owner/name``, ``source_type`` = ``DOC``, ``path``,
    ``symbol`` = heading text, ``start_line``, ``end_line``, ``commit``.

``github_issues_prs``
    Issue and pull-request bodies/threads. Expect: ``source_id`` =
    ``owner/name``, ``source_type`` in ``{ISSUE, PR}``, ``canonical_url``,
    ``published_at``.

``evaluation_memory``
    Prior evaluation/mission outcomes retained for reflective retrieval.
    Expect: ``source_type`` = ``EVIDENCE``, ``published_at``, freeform
    ``metadata``.
"""

from __future__ import annotations

from typing import Final

# --- FIXED collection names (handbook §5.1 / RAG_CONTRACT.md) ---------------
PROFILE_EVIDENCE: Final[str] = "profile_evidence"
INDUSTRY_SOURCES: Final[str] = "industry_sources"
REPOSITORY_CODE: Final[str] = "repository_code"
REPOSITORY_DOCS: Final[str] = "repository_docs"
GITHUB_ISSUES_PRS: Final[str] = "github_issues_prs"
EVALUATION_MEMORY: Final[str] = "evaluation_memory"

#: The canonical, ordered tuple of all six retrieval domains.
DOMAINS: Final[tuple[str, ...]] = (
    PROFILE_EVIDENCE,
    INDUSTRY_SOURCES,
    REPOSITORY_CODE,
    REPOSITORY_DOCS,
    GITHUB_ISSUES_PRS,
    EVALUATION_MEMORY,
)

#: Set form for O(1) membership checks.
DOMAIN_SET: Final[frozenset[str]] = frozenset(DOMAINS)


class UnknownDomainError(ValueError):
    """Raised when a domain string is not one of the six fixed collections."""


def is_valid_domain(domain: str) -> bool:
    """Return ``True`` if ``domain`` is one of the six fixed collections."""
    return domain in DOMAIN_SET


def validate_domain(domain: str) -> str:
    """Validate and return ``domain``.

    Raises
    ------
    UnknownDomainError
        If ``domain`` is not one of the six fixed collection names.
    """
    if domain not in DOMAIN_SET:
        allowed = ", ".join(DOMAINS)
        raise UnknownDomainError(
            f"Unknown RAG domain {domain!r}; expected one of: {allowed}"
        )
    return domain


__all__ = [
    "DOMAINS",
    "DOMAIN_SET",
    "EVALUATION_MEMORY",
    "GITHUB_ISSUES_PRS",
    "INDUSTRY_SOURCES",
    "PROFILE_EVIDENCE",
    "REPOSITORY_CODE",
    "REPOSITORY_DOCS",
    "UnknownDomainError",
    "is_valid_domain",
    "validate_domain",
]
