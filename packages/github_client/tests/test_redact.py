"""Secret-redaction tests — tokens must never survive in any string."""

from __future__ import annotations

from github_client import redact

REDACTED = "***REDACTED***"


def test_redacts_classic_pat() -> None:
    assert "ghp_" not in redact("token ghp_0123456789abcdefABCDEF0123456789abcd")
    assert REDACTED in redact("ghp_0123456789abcdefABCDEF0123456789abcd")


def test_redacts_fine_grained_pat() -> None:
    out = redact("github_pat_11ABCDEFG0_aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789")
    assert "github_pat_" not in out
    assert REDACTED in out


def test_redacts_authorization_header() -> None:
    out = redact("Authorization: Bearer ghp_secretsecretsecretsecretsecret1234")
    assert "ghp_secret" not in out
    assert REDACTED in out


def test_redacts_token_query_param() -> None:
    out = redact("https://api.github.com/x?access_token=ghp_qwErTyUiOpAsDfGhJkLzXcVbNm012345")
    assert "ghp_qwErTy" not in out
    assert "access_token" in out  # the key may remain; the value must not
    assert REDACTED in out


def test_leaves_ordinary_text_untouched() -> None:
    text = "A normal sentence with no secrets in it."
    assert redact(text) == text
