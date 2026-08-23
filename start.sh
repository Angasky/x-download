#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ -x .venv/bin/python ]]; then
  .venv/bin/python scripts/bootstrap.py "$@"
elif command -v python3 >/dev/null 2>&1; then
  python3 scripts/bootstrap.py "$@"
else
  python scripts/bootstrap.py "$@"
fi
