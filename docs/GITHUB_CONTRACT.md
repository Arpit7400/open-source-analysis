# CareerForge AI — GitHub Read-Only Client Contract (Phase 3)

> Real, typed, **read-only** GitHub client. No writes ever (handbook §8.3).
> Package: `packages/github_client`. Wired into the API + used to feed real
> repo content into `rag_core` indexing.

## Principles
- **Read-only.** Only GET calls. No method may POST/PATCH/PUT/DELETE. A guard
  rejects any non-GET at the transport layer.
- **Token optional.** Works unauthenticated (low rate limit) OR with a
  fine-grained read-only PAT via `CAREERFORGE_GITHUB_TOKEN`. Token is NEVER
  logged, never in errors, never in returned payloads.
- **Graceful + typed.** Pydantic v2 models. httpx. Handles 403 rate-limit,
  404, network errors cleanly. Cross-platform.

## Package layout
```
packages/github_client/
  github_client/
    __init__.py
    config.py        # GithubSettings (CAREERFORGE_GITHUB_TOKEN, api_url)
    models.py        # Pydantic: RepoMeta, IssueRef, PullRef, CommitRef, ReleaseRef, RateLimit, ContentFile
    client.py        # GitHubClient (async httpx, read-only, secret-redacting)
    redact.py        # redact(text) -> strips tokens/authorization from any string
  tests/
    test_redact.py test_client.py test_readonly.py
  pyproject.toml
```

## Models (Pydantic v2)
```python
RepoMeta:   owner, name, full_name, default_branch, description|None, language|None,
            languages: dict[str,int], license_spdx|None, stargazers, forks, open_issues,
            archived, pushed_at, has_tests_hint: bool, topics: list[str], html_url
IssueRef:   number, title, state, author|None, created_at, updated_at, url, is_pull: bool, labels: list[str]
PullRef:    number, title, state, author|None, created_at, merged: bool, url, base, head
CommitRef:  sha, message, author|None, date, url
ReleaseRef: tag, name|None, published_at|None, prerelease: bool, url
ContentFile:path, size, encoding, text|None, sha, url
RateLimit:  limit, remaining, reset_at, used
```

## GitHubClient methods (ALL async, ALL read-only)
```
get_repo(owner, name) -> RepoMeta
get_languages(owner, name) -> dict[str,int]
list_issues(owner, name, state="open", limit=30) -> list[IssueRef]     # excludes PRs
list_pulls(owner, name, state="open", limit=30) -> list[PullRef]
list_commits(owner, name, limit=30, sha=None) -> list[CommitRef]
list_releases(owner, name, limit=10) -> list[ReleaseRef]
get_readme(owner, name) -> ContentFile | None
get_file(owner, name, path, ref=None) -> ContentFile | None
list_python_files(owner, name, ref=None, limit=200) -> list[str]       # via git/trees recursive
rate_limit() -> RateLimit
search_issues(owner, name, query, limit=20) -> list[IssueRef]          # for duplicate detection later
```
`parse_repo_url(url) -> (owner, name)` helper accepts https/ssh/`owner/name`.

## New API endpoints (extends API_CONTRACT.md)
```
GET  /api/v1/github/repo?owner=&name=            -> RepoMeta
GET  /api/v1/github/repo/issues?owner=&name=&state= -> { issues: IssueRef[] }
GET  /api/v1/github/repo/pulls?owner=&name=&state=  -> { pulls: PullRef[] }
GET  /api/v1/github/repo/commits?owner=&name=       -> { commits: CommitRef[] }
GET  /api/v1/github/repo/releases?owner=&name=      -> { releases: ReleaseRef[] }
GET  /api/v1/github/rate-limit                      -> RateLimit
POST /api/v1/github/index?owner=&name=              -> indexes README + Python files into rag_core
                                                       repository_code/repository_docs; returns index summary
GET  /api/v1/system/health  gains services.github = "authenticated" | "anonymous" | "down"
```

## Tests (hermetic — httpx MockTransport, NO network)
- redact: tokens/`Authorization` headers/`?access_token=` stripped from any string.
- client: get_repo/list_issues/etc parse a mocked GitHub JSON into models correctly; PRs excluded from issues.
- readonly: assert the client's transport REJECTS any non-GET method (a POST attempt raises).
- token never appears in repr/logs/exceptions.
