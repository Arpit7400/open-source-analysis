#!/usr/bin/env bash
# =============================================================================
# CareerForge AI — dev launcher (macOS / Linux)
# =============================================================================
# Starts the FastAPI backend (:8000) in the background, then runs the Next.js
# frontend (:3000) in the foreground. When you Ctrl-C the frontend, the backend
# is stopped too.
#
# Assumes `scripts/setup.sh` has already been run (a .venv exists and the web
# deps are installed). If not, this script will run setup automatically.
#
# Usage:
#     bash scripts/dev.sh
# =============================================================================
set -euo pipefail

# Resolve the repository root regardless of where this is invoked from.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"

VENV_DIR="${ROOT_DIR}/.venv"
API_DIR="${ROOT_DIR}/apps/api"
WEB_DIR="${ROOT_DIR}/apps/web"

# --- Ensure dependencies are installed --------------------------------------
if [[ ! -d "${VENV_DIR}" || ! -d "${WEB_DIR}/node_modules" ]]; then
  echo "[dev] Dependencies missing; running one-time setup..."
  bash "${SCRIPT_DIR}/setup.sh"
fi

# --- Activate the virtual environment ---------------------------------------
# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

# --- Start the backend in the background ------------------------------------
echo "[dev] Starting backend on http://localhost:8000 (demo mode)..."
python -m careerforge_api &
API_PID=$!

# --- Ensure the backend is stopped when this script exits -------------------
cleanup() {
  echo ""
  echo "[dev] Shutting down backend (PID ${API_PID})..."
  # Kill the backend if it is still running; ignore errors.
  kill "${API_PID}" 2>/dev/null || true
  wait "${API_PID}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# --- Give the backend a moment, then start the frontend ---------------------
sleep 1
echo "[dev] Starting frontend on http://localhost:3000 ..."
echo ""
echo "  Backend  : http://localhost:8000        (API docs: http://localhost:8000/docs)"
echo "  Frontend : http://localhost:3000"
echo ""
echo "  Press Ctrl-C to stop both."
echo ""

# Run the frontend in the foreground. When it exits (or Ctrl-C), the trap
# above tears down the backend.
npm --prefix "${WEB_DIR}" run dev
