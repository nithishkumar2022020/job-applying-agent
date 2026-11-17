#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ ! -f profile.json ]]; then
  cp profile.example.json profile.json
  echo "Created profile.json from the example. Customize it before relying on matches."
fi

exec python3 -m job_agent serve --host 127.0.0.1 --port "${PORT:-8765}" --open
