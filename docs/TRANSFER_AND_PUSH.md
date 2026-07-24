# Transferring this repo to Windows & pushing to your own remote

This project is developed on macOS in steps (one commit per phase). You will
transfer the code to Windows and push it to **your own** Git remote. Here's the
clean, safe way to do that.

## What to transfer

The repository is self-contained. **Do NOT copy generated/installed folders** —
they are large, machine-specific, and already ignored by Git:

```
apps/api/.venv/            # Python virtualenv  — recreate on Windows
apps/web/node_modules/     # npm packages       — recreate with `npm install`
apps/web/.next/            # Next.js build cache
**/__pycache__/  **/.mypy_cache/  **/.ruff_cache/  *.egg-info/
```

Two clean transfer options:

### Option A — Git bundle (recommended, preserves full history)
On macOS:
```bash
cd careerforge-ai
git bundle create careerforge-ai.bundle --all
```
Copy `careerforge-ai.bundle` to Windows, then:
```powershell
git clone careerforge-ai.bundle careerforge-ai
cd careerforge-ai
```

### Option B — Copy the folder
Copy the whole `careerforge-ai/` folder **including the `.git/` directory** but
**excluding** the ignored folders above. Because `.gitignore` already excludes
them, a `git clone <local-path>` or an archive of `git ls-files` is cleanest:
```bash
# macOS: archive only tracked files (no venv/node_modules)
git archive --format=zip -o careerforge-ai-src.zip HEAD
```
Unzip on Windows (note: this loses history — use Option A if you want history).

## Pushing to your own remote (on Windows)

```powershell
cd careerforge-ai
# point at YOUR repo (create an empty one on GitHub/your host first)
git remote add origin https://github.com/<you>/<your-repo>.git
# (if a remote already exists) git remote set-url origin <url>

git branch -M main          # optional: rename master -> main
git push -u origin main
```

If you used a bundle (Option A), the history and all phase commits come with it.

## First run on Windows (demo mode — no Docker needed)

```powershell
# one-time setup
./scripts/setup.ps1
# start backend (:8000) + frontend (:3000)
./scripts/dev.ps1
```

Or manually:
```powershell
# backend
cd apps/api
python -m venv .venv
.\.venv\Scripts\pip install -e .
.\.venv\Scripts\pip install -e ..\..\packages\rag_core
.\.venv\Scripts\python -m careerforge_api

# frontend (new terminal)
cd apps/web
npm install
npm run dev
```

## Line endings

`.gitattributes` normalizes line endings (LF in the repo; `.ps1`/`.bat` as CRLF).
This prevents Windows from showing every file as "modified" after transfer.
If you ever see a mass "modified" diff right after cloning, run once:
```powershell
git add --renormalize .
git commit -m "Normalize line endings"
```

## RAG on Windows

`rag_core` uses `qdrant-client` in **in-process local mode** by default — no
Docker or Qdrant server required. Real embeddings need Ollama running with the
`nomic-embed-text` model (`ollama pull nomic-embed-text`); without Ollama it
falls back to a deterministic hash embedder so everything still runs and tests
stay green.
