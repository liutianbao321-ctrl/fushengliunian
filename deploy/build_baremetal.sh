#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/opt/fushengliunian}"
UV="${UV:-/opt/fushengliunian-tools/bin/uv}"
RUNTIME_VENV="${RUNTIME_VENV:-/opt/fushengliunian-runtime/venv}"
UV_INDEX_URL="${UV_INDEX_URL:-}"
NEXT_PUBLIC_BASE_PATH="${NEXT_PUBLIC_BASE_PATH:-}"
NEXT_PUBLIC_API_BASE="${NEXT_PUBLIC_API_BASE:-${NEXT_PUBLIC_BASE_PATH}/api}"

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this script as root" >&2
    exit 1
fi

if ! command -v antiword >/dev/null 2>&1; then
    apt-get update
    apt-get install -y --no-install-recommends antiword
fi

mkdir -p "$(dirname "$RUNTIME_VENV")"
if ! "$RUNTIME_VENV/bin/python" -c "import sys" >/dev/null 2>&1; then
    python3 -m venv --clear "$RUNTIME_VENV"
fi
"$RUNTIME_VENV/bin/python" -m pip install --upgrade pip
"$RUNTIME_VENV/bin/python" -m pip install -r "$ROOT/backend/requirements.txt"

# Release directories are immutable and do not contain ignored runtime secrets.
# Carry the existing local database/JWT settings forward before switching the symlink.
if [ ! -f "$ROOT/backend/.env" ] && [ -f /opt/fushengliunian/backend/.env ]; then
    install -m 0600 -o www-data -g www-data /opt/fushengliunian/backend/.env "$ROOT/backend/.env"
fi
# Schema compatibility is versioned in code; a stale operational override can prevent startup after migration.
sed -i '/^EXPECTED_SCHEMA_REVISION=/d' /etc/fushengliunian/backend.env

cd "$ROOT/frontend"
npm ci
NEXT_PUBLIC_BASE_PATH="$NEXT_PUBLIC_BASE_PATH" NEXT_PUBLIC_API_BASE="$NEXT_PUBLIC_API_BASE" npm run build
mkdir -p .next/standalone/.next .next/standalone/public
cp -R .next/static .next/standalone/.next/
cp -R public/. .next/standalone/public/

install -m 0644 "$ROOT/deploy/fushengliunian.service" /etc/systemd/system/fushengliunian.service
install -m 0644 "$ROOT/deploy/fushengliunian-web.service" /etc/systemd/system/fushengliunian-web.service
systemctl daemon-reload

sudo -u postgres env \
    DATABASE_URL="postgresql+asyncpg:///fushengliunian?host=/var/run/postgresql" \
    APP_ENV=development \
    REQUIRE_MIGRATIONS=false \
    sh -c "cd '$ROOT/backend' && '$RUNTIME_VENV/bin/python' -m alembic upgrade head"

systemctl enable --now fushengliunian.service
systemctl enable --now fushengliunian-web.service
