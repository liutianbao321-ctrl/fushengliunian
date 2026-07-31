#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/backend"
exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8100 --workers 1
