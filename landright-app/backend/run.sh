#!/usr/bin/env bash
# Run the generator backend with the venv. From repo root: landright-app/backend/run.sh
# Or: cd landright-app/backend && ./run.sh
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"
if [[ ! -d .venv ]]; then
  echo "No .venv found. Create one with: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi
exec .venv/bin/python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
