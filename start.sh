#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

if command -v python3 >/dev/null 2>&1; then
  PY_BOOT=python3
else
  PY_BOOT=python
fi

if [[ -f .venv/bin/python ]]; then
  PY=.venv/bin/python
  PIP=.venv/bin/pip
elif [[ -f .venv/Scripts/python.exe ]]; then
  PY=.venv/Scripts/python.exe
  PIP=.venv/Scripts/pip.exe
else
  echo "Creating virtual environment..."
  "$PY_BOOT" -m venv .venv
  if [[ -f .venv/bin/python ]]; then
    PY=.venv/bin/python
    PIP=.venv/bin/pip
  else
    PY=.venv/Scripts/python.exe
    PIP=.venv/Scripts/pip.exe
  fi
  "$PIP" install -r requirements.txt
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "[ERROR] DATABASE_URL is not set."
  echo "Create a .env file from .env.example and paste your Supabase connection string."
  exit 1
fi

export FLASK_DEBUG=1
export PORT=5000

echo
echo "  Finance tracker"
echo "  Open: http://127.0.0.1:${PORT}"
echo "  DB:   Postgres (DATABASE_URL)"
echo "  Stop: Ctrl+C"
echo

exec "$PY" app.py
