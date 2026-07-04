#!/usr/bin/env bash
# Activates the venv (must already exist -- run ./setup.sh first) and starts
# the speech-to-keyboard app. Any arguments are passed through to src/main.py.
#
# Usage:
#   ./run.sh                      # uses config.yaml, activation mode from config
#   ./run.sh -v                   # verbose/debug logging
#   ./run.sh --config other.yaml
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR=".venv"

if [[ ! -d "$VENV_DIR" ]]; then
  echo "Error: no virtual environment found at ./$VENV_DIR." >&2
  echo "Run ./setup.sh first." >&2
  exit 1
fi

# venv layout differs between POSIX (bin/) and native Windows (Scripts/).
if [[ -f "$VENV_DIR/bin/activate" ]]; then
  ACTIVATE="$VENV_DIR/bin/activate"
elif [[ -f "$VENV_DIR/Scripts/activate" ]]; then
  ACTIVATE="$VENV_DIR/Scripts/activate"
else
  echo "Error: ./$VENV_DIR exists but has no activate script. Delete it and run ./setup.sh again." >&2
  exit 1
fi

# shellcheck disable=SC1090
source "$ACTIVATE"

python -m src.main "$@"
