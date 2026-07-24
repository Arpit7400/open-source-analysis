# dup_detect — CareerForge AI Phase 8

Duplicate issue/PR detection. Given a proposed issue/finding and a set of
candidate issues/PRs, ranks candidates by duplicate likelihood using:

- **Exact signals** — shared error strings, dotted symbols, stack frames (§5.3).
- **Lexical overlap** — token Jaccard over title+body.
- **Semantic similarity** — embedding cosine (optional; via `rag_core` embedder).

Each match has a confidence in [0,1] and a class: `EXACT | NEAR | WEAK | NONE`,
plus a human-readable explanation. Deterministic given a fixed embedder.

```python
from dup_detect import detect_duplicates, DuplicateQuery, Candidate
report = await detect_duplicates(query, candidates)   # embedder optional
if report.has_duplicate:
    print(report.best.url, report.best.explanation)
```
