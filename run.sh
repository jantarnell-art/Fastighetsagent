#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d ".venv" ]; then
  echo "Skapar virtuell Python-miljö..."
  python3 -m venv .venv
fi

source .venv/bin/activate
echo "Installerar beroenden..."
pip install -r requirements.txt --quiet

echo ""
echo "  Fastighetsaffärsagent startar på → http://localhost:8000"
echo ""
uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}" --reload
