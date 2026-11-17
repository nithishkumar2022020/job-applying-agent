#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"

{
  printf '\n[%s] Starting discovery\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  cd "$ROOT"
  python3 -m job_agent discover
  python3 -m job_agent dashboard
} >> "$LOG_DIR/discovery.log" 2>&1
