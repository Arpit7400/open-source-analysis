"""Hermetic duplicate-detection tests: exact, near, and false-friend cases."""

from __future__ import annotations

import pytest

from dup_detect import Candidate, DuplicateQuery, detect_duplicates

# A tiny deterministic embedder so the semantic path is exercised without a
# network/model. It hashes tokens into a small fixed-dim bag-of-words vector,
# so texts sharing vocabulary get a high cosine — good enough to test wiring.
_DIM = 64


class _BowEmbedder:
    name = "bow-test"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vecs: list[list[float]] = []
        for t in texts:
            v = [0.0] * _DIM
            for tok in t.lower().split():
                v[hash(tok) % _DIM] += 1.0
            vecs.append(v)
        return vecs


_QUERY = DuplicateQuery(
    title="Timeout not honored on redirect",
    body="When following a 301 redirect, requests.adapters.HTTPAdapter ignores the timeout "
    "and hangs. Raises ReadTimeout only sometimes.",
    error_strings=["ReadTimeout"],
    symbols=["requests.adapters.HTTPAdapter"],
)

_EXACT_DUP = Candidate(
    id="c1",
    number=101,
    url="https://github.com/psf/requests/issues/101",
    title="Timeout ignored when following redirect",
    body="requests.adapters.HTTPAdapter does not honor the timeout across a redirect; "
    "we see ReadTimeout intermittently.",
)

_NEAR_DUP = Candidate(
    id="c2",
    number=88,
    url="https://github.com/psf/requests/issues/88",
    title="Redirects and timeouts behave inconsistently",
    body="Sometimes a redirect makes the request hang; timeout handling seems off.",
)

_FALSE_FRIEND = Candidate(
    id="c3",
    number=500,
    url="https://github.com/psf/requests/issues/500",
    title="Add async support to Session",
    body="It would be great if Session supported asyncio for concurrent requests.",
)


@pytest.mark.asyncio
async def test_exact_duplicate_ranks_first_and_is_flagged() -> None:
    report = await detect_duplicates(
        _QUERY, [_FALSE_FRIEND, _NEAR_DUP, _EXACT_DUP], embedder=_BowEmbedder()
    )
    assert report.best is not None
    assert report.best.candidate_id == "c1"
    assert report.best.dup_class in ("EXACT", "NEAR")
    assert report.has_duplicate
    # the exact signal (dotted symbol / error string) was detected
    assert any("httpadapter" in s or "readtimeout" in s for s in report.best.shared_signals)


@pytest.mark.asyncio
async def test_false_friend_is_not_a_duplicate() -> None:
    report = await detect_duplicates(_QUERY, [_FALSE_FRIEND], embedder=_BowEmbedder())
    m = report.matches[0]
    assert m.candidate_id == "c3"
    assert m.dup_class in ("WEAK", "NONE")
    assert not report.has_duplicate


@pytest.mark.asyncio
async def test_ordering_exact_gt_near_gt_false() -> None:
    report = await detect_duplicates(
        _QUERY, [_FALSE_FRIEND, _NEAR_DUP, _EXACT_DUP], embedder=_BowEmbedder()
    )
    order = [m.candidate_id for m in report.matches]
    assert order.index("c1") < order.index("c2") < order.index("c3")


@pytest.mark.asyncio
async def test_works_without_embedder() -> None:
    # No embedder -> semantic weight redistributed; exact+lexical still detect it.
    report = await detect_duplicates(_QUERY, [_EXACT_DUP, _FALSE_FRIEND], embedder=None)
    assert report.used_embedder == "none"
    assert report.best is not None
    assert report.best.candidate_id == "c1"
    assert report.best.semantic_score == 0.0


@pytest.mark.asyncio
async def test_deterministic() -> None:
    a = await detect_duplicates(_QUERY, [_EXACT_DUP, _NEAR_DUP], embedder=None)
    b = await detect_duplicates(_QUERY, [_EXACT_DUP, _NEAR_DUP], embedder=None)
    assert [m.confidence for m in a.matches] == [m.confidence for m in b.matches]


@pytest.mark.asyncio
async def test_confidence_in_range_and_explanations_present() -> None:
    report = await detect_duplicates(
        _QUERY, [_EXACT_DUP, _NEAR_DUP, _FALSE_FRIEND], embedder=_BowEmbedder()
    )
    for m in report.matches:
        assert 0.0 <= m.confidence <= 1.0
        assert m.explanation
        assert m.dup_class in ("EXACT", "NEAR", "WEAK", "NONE")
