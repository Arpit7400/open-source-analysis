#!/usr/bin/env bash
# =============================================================================
# CareerForge AI — one-time setup (macOS / Linux)
# =============================================================================
# Creates the Python virtual environment, installs the backend package (with
# dev extras), and installs the frontend dependencies. Safe to re-run.
#
# Nothing here requires Docker, a GPU, or any external service — the demo runs
# with just Python 3.12+ and Node 18+.
#
# Usage:
#     bash scripts/setup.sh
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"

VENV_DIR="${ROOT_DIR}/.venv"
API_DIR="${ROOT_DIR}/apps/api"
WEB_DIR="${ROOT_DIR}/apps/web"

# --- Pick a Python interpreter (prefer python3) -----------------------------
if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
else
  echo "[setup] ERROR: Python 3.12+ is required but neither 'python3' nor 'python' was found." >&2
  exit 1
fi

echo "[setup] Using Python: $(${PYTHON_BIN} --version 2>&1)"

# --- Check Node.js is present -----------------------------------------------
if ! command -v node >/dev/null 2>&1; then
  echo "[setup] ERROR: Node.js 18+ is required but 'node' was not found on PATH." >&2
  exit 1
fi
echo "[setup] Using Node: $(node --version)"

# --- Create the virtual environment -----------------------------------------
if [[ ! -d "${VENV_DIR}" ]]; then
  echo "[setup] Creating virtual environment at ${VENV_DIR} ..."
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
else
  echo "[setup] Reusing existing virtual environment at ${VENV_DIR}"
fi

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

# --- Install the backend (editable, with dev extras) ------------------------
echo "[setup] Upgrading pip ..."
python -m pip install --upgrade pip

echo "[setup] Installing backend (editable + dev extras) from ${API_DIR} ..."
python -m pip install -e "${API_DIR}[dev]"

# --- Copy .env if the user has not created one ------------------------------
if [[ ! -f "${ROOT_DIR}/.env" && -f "${ROOT_DIR}/.env.example" ]]; then
  cp "${ROOT_DIR}/.env.example" "${ROOT_DIR}/.env"
  echo "[setup] Created .env from .env.example (demo defaults)."
fi

# --- Install frontend dependencies ------------------------------------------
echo "[setup] Installing frontend dependencies in ${WEB_DIR} ..."
npm --prefix "${WEB_DIR}" install

echo ""
echo "[setup] Done. Next steps:"
echo "  * Start everything:   bash scripts/dev.sh"
echo "  * Or run separately:  make api   and   make web"
echo ""
