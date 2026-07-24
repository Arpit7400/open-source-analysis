# =============================================================================
# CareerForge AI — developer Makefile
# =============================================================================
# Convenience targets for macOS / Linux.
#
# WINDOWS USERS: `make` is usually not available on Windows. Use the PowerShell
# scripts instead:
#     powershell scripts\setup.ps1     (one-time install)
#     powershell scripts\dev.ps1       (start backend + frontend)
#
# These targets assume:
#   * A Python virtual environment at ./.venv (created by `make setup`).
#   * Node.js 18+ with npm on PATH.
# The backend runs in demo mode by default (no Docker / DB / Ollama required).
# =============================================================================

# Resolve the venv's python/pip in a cross-shell way (falls back to system python3).
VENV        := .venv
VENV_BIN    := $(VENV)/bin
PYTHON      := $(VENV_BIN)/python
PIP         := $(VENV_BIN)/pip
API_DIR     := apps/api
WEB_DIR     := apps/web

# Use system python3 to bootstrap the venv if it does not exist yet.
SYS_PYTHON  ?= python3

.DEFAULT_GOAL := help
.PHONY: help setup venv api web dev test lint fmt typecheck clean compose-up compose-down

## help: Show this help.
help:
	@echo "CareerForge AI — make targets"
	@echo ""
	@echo "  setup        One-time install (venv + backend editable install + frontend deps)"
	@echo "  dev          Start backend (:8000) in the background, then frontend (:3000)"
	@echo "  api          Start ONLY the FastAPI backend on :8000"
	@echo "  web          Start ONLY the Next.js frontend on :3000"
	@echo "  test         Run the backend test suite (21 tests)"
	@echo "  lint         Lint backend (ruff) and frontend (next lint)"
	@echo "  fmt          Format backend with ruff"
	@echo "  typecheck    Run mypy on the backend"
	@echo "  compose-up   Start the OPTIONAL real-services stack (docker compose)"
	@echo "  compose-down Stop the optional real-services stack"
	@echo "  clean        Remove caches, .venv, node_modules, build artifacts"
	@echo ""
	@echo "  Windows users: use scripts\\\\setup.ps1 and scripts\\\\dev.ps1 instead."

## venv: Create the Python virtual environment if missing.
venv:
	@test -d $(VENV) || $(SYS_PYTHON) -m venv $(VENV)

## setup: One-time dependency install for backend and frontend.
setup: venv
	$(PIP) install --upgrade pip
	$(PIP) install -e "./$(API_DIR)[dev]"
	npm --prefix $(WEB_DIR) install
	@echo "Setup complete. Run 'make dev' to start everything."

## api: Start ONLY the FastAPI backend (demo mode) on :8000.
api: venv
	$(PYTHON) -m careerforge_api

## web: Start ONLY the Next.js frontend on :3000.
web:
	npm --prefix $(WEB_DIR) run dev

## dev: Start backend in the background, then run the frontend in the foreground.
dev: venv
	@echo "Starting backend on http://localhost:8000 ..."
	@$(PYTHON) -m careerforge_api & echo $$! > .careerforge-api.pid
	@echo "Backend PID $$(cat .careerforge-api.pid). Starting frontend on http://localhost:3000 ..."
	@trap 'kill $$(cat .careerforge-api.pid) 2>/dev/null; rm -f .careerforge-api.pid' EXIT; \
		npm --prefix $(WEB_DIR) run dev

## test: Run the backend test suite.
test: venv
	$(PYTHON) -m pytest $(API_DIR)/tests

## lint: Lint backend (ruff) and frontend (next lint).
lint: venv
	$(PYTHON) -m ruff check $(API_DIR)
	npm --prefix $(WEB_DIR) run lint

## fmt: Format the backend with ruff.
fmt: venv
	$(PYTHON) -m ruff format $(API_DIR)
	$(PYTHON) -m ruff check --fix $(API_DIR)

## typecheck: Run mypy over the backend package.
typecheck: venv
	$(PYTHON) -m mypy $(API_DIR)/careerforge_api

## compose-up: Start the OPTIONAL real-services stack (NOT needed for the demo).
compose-up:
	docker compose up -d

## compose-down: Stop the optional real-services stack.
compose-down:
	docker compose down

## clean: Remove caches, virtualenv, node_modules, and build artifacts.
clean:
	rm -rf $(VENV) $(WEB_DIR)/node_modules $(WEB_DIR)/.next
	rm -rf $(API_DIR)/.pytest_cache $(API_DIR)/.mypy_cache $(API_DIR)/.ruff_cache
	find . -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true
	rm -f .careerforge-api.pid
	@echo "Cleaned."
