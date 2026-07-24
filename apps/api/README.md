# CareerForge AI — API (`careerforge_api`)

Local-first, multi-agent **career-intelligence** backend. FastAPI + Server-Sent
Events. Runs the flagship repository-analysis mission as a **scripted, realistic
simulation** in *demo mode* — no Docker, no database, no Ollama, no GPU required.
Cross-platform: Windows, macOS, and Linux with just Python.

- Base URL: `http://localhost:8000`
- REST prefix: `/api/v1`
- Live stream: SSE at `/api/v1/events/stream?mission_id=...`
- Interactive docs: `http://localhost:8000/docs`

The full request/response contract lives in
[`../../docs/API_CONTRACT.md`](../../docs/API_CONTRACT.md).

---

## Requirements

- **Python 3.12+**
- No external services in demo mode (the default).

---

## Quick start

The commands below create a virtual environment, install the package (with its
dev extras), and start the server on port **8000**.

### macOS / Linux

```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
python -m careerforge_api
```

### Windows (PowerShell)

```powershell
cd apps\api
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -e ".[dev]"
python -m careerforge_api
```

### Windows (cmd.exe)

```bat
cd apps\api
py -3 -m venv .venv
.venv\Scripts\activate.bat
pip install --upgrade pip
pip install -e ".[dev]"
python -m careerforge_api
```

You should see a banner like:

```
CareerForge AI API v1.0.0 [demo] profile=WORKSTATION python=3.12.x platform=...
Serving on http://127.0.0.1:8000  (docs: /docs, API base: /api/v1)
```

Then open <http://localhost:8000/docs> or hit
<http://localhost:8000/api/v1/system/health>.

> The frontend dev server (`apps/web`) runs on `http://localhost:3000`, which is
> already whitelisted in CORS.

---

## Demo mode (default)

With no external services configured, the backend runs in `APP_ENV=demo`:

- `GET /api/v1/system/health` reports every backing service (`database`,
  `qdrant`, `redis`, `ollama`, `temporal`) as **`mock`** and both safety flags
  (`github_writes`, `repository_execution`) as **`false`**.
- `POST /api/v1/repositories/analyze` kicks off a **scripted multi-agent
  mission**. The mission timeline (agents, edges, findings, fix candidates,
  independent verifiers, and a human-approval gate) streams over SSE with the
  exact same JSON shapes as a real run — deterministic per `repo_url`.
- Resume ingestion (`POST /api/v1/profile/ingest-resume`) returns extracted
  skill **claims only**, always at `SELF_DECLARED`. It never fabricates a higher
  verification level.
- Approvals (`POST /api/v1/approvals/{mission_id}`) **never** perform a GitHub
  write: the response is always `{ "github_write": false, "action_taken":
  "DRAFT_SAVED_LOCALLY" }` (or `DRAFT_DISCARDED` on reject). The human-approval
  draft is marked `submittable: false` while writes are disabled.

### Configuration

Configuration is read from environment variables (prefix `CAREERFORGE_`) and an
optional `.env` file at the API project root. Common knobs:

| Variable | Default | Purpose |
| --- | --- | --- |
| `CAREERFORGE_APP_ENV` | `demo` | `demo` \| `local` \| `production` |
| `CAREERFORGE_HOST` | `127.0.0.1` | Bind host |
| `CAREERFORGE_PORT` | `8000` | Bind port |
| `CAREERFORGE_CORS_ORIGINS` | `http://localhost:3000,...` | Comma-separated origins |

Example (serve on a different port):

```bash
# macOS / Linux
CAREERFORGE_PORT=9000 python -m careerforge_api
```

```powershell
# Windows PowerShell
$env:CAREERFORGE_PORT=9000; python -m careerforge_api
```

---

## Endpoints

| Method | Path | Description |
| --- | --- | --- |
| GET | `/` | JSON banner |
| GET | `/api/v1/system/health` | Service health, flags, hardware profile |
| GET | `/api/v1/system/resources` | Live CPU / RAM / agent gauges |
| GET | `/api/v1/profile` | Profile Brain summary |
| GET | `/api/v1/skills` | Scored skill list |
| GET | `/api/v1/skills/{id}/evidence` | Evidence backing a skill |
| POST | `/api/v1/profile/ingest-resume` | Extract `SELF_DECLARED` skill claims |
| POST | `/api/v1/repositories/analyze` | Start a multi-agent analysis mission |
| GET | `/api/v1/missions/{mission_id}` | Full mission snapshot |
| POST | `/api/v1/approvals/{mission_id}` | Human decision (never writes to GitHub) |
| GET | `/api/v1/pulse` | Industry-pulse feed |
| GET | `/api/v1/events/stream?mission_id=...` | SSE mission event stream |

### SSE stream

`GET /api/v1/events/stream?mission_id=...` returns `text/event-stream`. Event
types: `mission.status`, `agent.update`, `edge.update`, `finding.new`,
`candidate.update`, `log`, `resource`, `approval.required`, `mission.complete`.
Reconnecting clients may send the `Last-Event-ID` header to replay from where
they left off; the server also emits periodic heartbeat comments.

---

## Running the tests

```bash
# from apps/api, with the venv active and dev extras installed
pytest
```

The suite uses FastAPI's `TestClient` and requires **no database or external
services**. The mission test advances the simulation synchronously (via
`careerforge_api.main.run_mission_sync`) rather than sleeping on the live
stream, so it is fast and deterministic.

---

## Project layout

```
apps/api/
├── pyproject.toml
├── README.md
├── careerforge_api/
│   ├── __init__.py
│   ├── __main__.py        # python -m careerforge_api  → uvicorn on :8000
│   ├── config.py          # Settings (pydantic-settings)
│   ├── hardware.py        # cross-platform hardware profiling
│   ├── schemas.py         # Pydantic models + enums (the contract)
│   ├── seed_data.py       # deterministic Profile-Brain seeds
│   ├── simulation.py      # scripted mission engine (store + simulator)
│   └── main.py            # FastAPI app, routers, SSE, error handler
└── tests/
    ├── test_health.py
    ├── test_profile.py
    └── test_mission.py
```
