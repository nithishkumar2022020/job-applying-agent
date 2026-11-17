#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
LOG_DIR="$ROOT/logs"
PYTHON=python3
if [ -x "$ROOT/.venv/bin/python" ]; then PYTHON="$ROOT/.venv/bin/python"; fi
mkdir -p "$LOG_DIR"

{
  printf '\n[%s] Starting discovery\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  cd "$ROOT"
  "$PYTHON" -m job_agent discover
  "$PYTHON" -m job_agent dashboard
} >> "$LOG_DIR/discovery.log" 2>&1
