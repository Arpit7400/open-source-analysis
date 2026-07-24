"""Secret redaction for the GitHub client.

:func:`redact` strips anything that could carry a credential out of an arbitrary
string before it is logged, put in an exception message, or returned to a
caller. It is deliberately **pure** (no I/O, no state) and defensive: it never
raises on odd input and always returns a string.

It handles the three ways a token can appear in text the client touches:

1. **Raw GitHub tokens** — the documented prefixes ``ghp_``, ``github_pat_``,
   ``gho_``, ``ghs_``, ``ghu_``, ``ghr_`` followed by their token body.
2. **Authorization headers** — ``Authorization: Bearer <token>`` /
   ``Authorization: token <token>`` (case-insensitive), including the bare
   ``Bearer <token>`` / ``token <token>`` forms.
3. **Query parameters** — ``?access_token=<token>`` / ``&access_token=<token>``.

Every match is replaced with the fixed sentinel :data:`REDACTED`.
"""

from __future__ import annotations

import re

#: Replacement sentinel for every redacted secret.
REDACTED = "***REDACTED***"

# 1) Raw GitHub token literals. Fine-grained PATs (``github_pat_``) contain
#    underscores in their body, so allow ``[A-Za-z0-9_]`` after the prefix.
#    ``github_pat_`` must precede the ``gh*_`` alternatives so the longer prefix
#    wins under alternation.
_TOKEN_RE = re.compile(
    r"\b(?:github_pat_|ghp_|gho_|ghs_|ghu_|ghr_)[A-Za-z0-9_]+",
)

# 2) Authorization scheme + credential (with or without the header name).
#    Consumes the scheme keyword and the credential that follows it so the
#    whole "Bearer <token>" / "token <token>" pair becomes the sentinel.
_AUTH_RE = re.compile(
    r"(?i)(?:authorization\s*:\s*)?\b(?:bearer|token)\s+[^\s,;]+",
)

# 3) ``access_token`` query parameter value (leading ? or &, or bare).
_QUERY_RE = re.compile(
    r"(?i)([?&]?access_token=)[^&\s#]+",
)


def redact(text: str) -> str:
    """Return ``text`` with any GitHub token / auth credential masked.

    Pure and total: non-``str`` input is coerced with ``str()`` and a value
    with no secrets is returned unchanged (modulo the substitutions above).
    """
    if not isinstance(text, str):
        text = str(text)
    text = _AUTH_RE.sub(REDACTED, text)
    text = _QUERY_RE.sub(lambda m: f"{m.group(1)}{REDACTED}", text)
    text = _TOKEN_RE.sub(REDACTED, text)
    return text


__all__ = [
    "REDACTED",
    "redact",
]
