#!/usr/bin/env bash
# Sets up the project: creates a venv if missing, installs requirements,
# and downloads the default Vosk model if it isn't already present.
#
# Usage:
#   ./setup.sh            # normal setup (requirements.txt)
#   ./setup.sh --dev      # also installs requirements-dev.txt (pytest)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR=".venv"
DEV_MODE=false
for arg in "$@"; do
  if [[ "$arg" == "--dev" ]]; then
    DEV_MODE=true
  fi
done

# --- Find a Python interpreter -----------------------------------------
if command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON=python
else
  echo "Error: no python3/python interpreter found on PATH." >&2
  exit 1
fi

# --- Create the venv if it doesn't exist yet ----------------------------
if [[ -d "$VENV_DIR" ]]; then
  echo "Virtual environment already exists at ./$VENV_DIR, skipping creation."
else
  echo "Creating virtual environment at ./$VENV_DIR ..."
  "$PYTHON" -m venv "$VENV_DIR"
fi

# venv layout differs between POSIX (bin/) and native Windows (Scripts/).
if [[ -f "$VENV_DIR/bin/activate" ]]; then
  ACTIVATE="$VENV_DIR/bin/activate"
elif [[ -f "$VENV_DIR/Scripts/activate" ]]; then
  ACTIVATE="$VENV_DIR/Scripts/activate"
else
  echo "Error: could not find activate script inside $VENV_DIR." >&2
  exit 1
fi

# shellcheck disable=SC1090
source "$ACTIVATE"
echo "Using $(python --version) from $(command -v python)"

# --- Install requirements ------------------------------------------------
python -m pip install --upgrade pip
if [[ "$DEV_MODE" == true ]]; then
  echo "Installing requirements-dev.txt ..."
  pip install -r requirements-dev.txt
else
  echo "Installing requirements.txt ..."
  pip install -r requirements.txt
fi

# --- Download the Vosk model if needed -----------------------------------
# download_vosk_model.py already no-ops if the model directory exists, so
# it's safe to call unconditionally.
echo "Checking Vosk model..."
python scripts/download_vosk_model.py

echo ""
echo "Setup complete. Start the app with:"
echo "  ./run.sh"
echo "(that activates the venv for you; add -v for verbose logging, or --config <path> for a different config file)"
