#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -f .env ]]; then
  echo "[ERROR] File .env not found."
  echo "  cp .env.example .env   # then edit DATABASE_URL"
  exit 1
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

"$PY" -c "import config, os, sys; sys.exit(0 if os.environ.get('DATABASE_URL') else 1)" || {
  echo "[ERROR] DATABASE_URL is empty in .env"
  exit 1
}

export FLASK_DEBUG=1
export PORT=5000

echo
echo "  Finance tracker"
echo "  Open: http://127.0.0.1:${PORT}"
echo "  Stop: Ctrl+C"
echo

exec "$PY" app.py
