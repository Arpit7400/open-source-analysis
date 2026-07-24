# github_client

A real, typed, **read-only** GitHub REST client for CareerForge AI (Phase 3).

It fetches repository metadata, issues, pull requests, commits, releases, the
README, arbitrary files, and the Python file tree from `api.github.com`, and
returns strongly-typed [Pydantic v2](https://docs.pydantic.dev) models. The
output feeds the `rag_core` indexing pipeline so real repository content can be
retrieved and cited.

## Guarantees

- **Read-only.** Every request is a `GET`. A transport-level guard
  (`_ReadOnlyTransport`) rejects any other method with `ReadOnlyViolation`
  *before* the request is dispatched. No write helpers exist.
- **Token-safe.** The optional PAT (`CAREERFORGE_GITHUB_TOKEN`) is stored as a
  `pydantic.SecretStr` and only ever placed in the `Authorization` header. It is
  **never** logged, never in an exception, never in a returned payload, and
  never in `repr`. Every outward-facing string is passed through `redact()`.
- **Works unauthenticated.** With no token, requests are anonymous (GitHub's
  lower rate limit applies). With a fine-grained read-only PAT, the higher limit
  applies.
- **Graceful + typed.** `404` becomes `None` where the contract says `| None`;
  a rate-limit `403`/`429` raises `RateLimitError` (with `reset_at`); transport
  failures raise `GitHubClientError`.
- **Cross-platform.** Pure `pathlib`/stdlib; no shell or OS assumptions.

## Configuration

All keys use the shared `CAREERFORGE_` prefix (same `.env` as the API and
`rag_core`):

| Env var                       | Default                    | Meaning                              |
| ----------------------------- | -------------------------- | ------------------------------------ |
| `CAREERFORGE_GITHUB_TOKEN`    | *(empty)*                  | Optional read-only PAT (`SecretStr`) |
| `CAREERFORGE_GITHUB_API_URL`  | `https://api.github.com`   | API base URL (override for GHE)      |
| `CAREERFORGE_GITHUB_TIMEOUT`  | `30.0`                     | Per-request timeout (seconds)        |

## Usage

```python
import asyncio
from github_client import GitHubClient, parse_repo_url

async def main() -> None:
    owner, name = parse_repo_url("https://github.com/psf/requests")
    async with GitHubClient() as gh:
        repo = await gh.get_repo(owner, name)
        print(repo.full_name, repo.language, repo.stargazers)

        issues = await gh.list_issues(owner, name, state="open", limit=10)
        readme = await gh.get_readme(owner, name)  # ContentFile | None
        py_files = await gh.list_python_files(owner, name, limit=200)
        print(await gh.rate_limit())

asyncio.run(main())
```

### Methods

| Method | Returns |
| --- | --- |
| `get_repo(owner, name)` | `RepoMeta` |
| `get_languages(owner, name)` | `dict[str, int]` |
| `list_issues(owner, name, state="open", limit=30)` | `list[IssueRef]` (PRs excluded) |
| `list_pulls(owner, name, state="open", limit=30)` | `list[PullRef]` |
| `list_commits(owner, name, limit=30, sha=None)` | `list[CommitRef]` |
| `list_releases(owner, name, limit=10)` | `list[ReleaseRef]` |
| `get_readme(owner, name)` | `ContentFile \| None` |
| `get_file(owner, name, path, ref=None)` | `ContentFile \| None` |
| `list_python_files(owner, name, ref=None, limit=200)` | `list[str]` |
| `rate_limit()` | `RateLimit` |
| `search_issues(owner, name, query, limit=20)` | `list[IssueRef]` |

`parse_repo_url(url)` accepts `https://…`, `git@github.com:owner/name.git`,
`ssh://…`, and bare `owner/name`, and returns `(owner, name)`.

## Testing

Tests are **hermetic** — no network. Inject an `httpx.MockTransport` and the
client wraps it in the same read-only guard used in production:

```python
import httpx
from github_client import GitHubClient

def handler(request: httpx.Request) -> httpx.Response:
    assert request.method == "GET"
    return httpx.Response(200, json={"full_name": "psf/requests", ...})

client = GitHubClient(transport=httpx.MockTransport(handler))
```

```bash
python -m pytest packages/github_client/tests
```

## License

MIT.
