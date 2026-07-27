#!/usr/bin/env bash
# Simple entry — no Ollama
set -uo pipefail

export PORT="${PORT:-8080}"
export DATABASE_PATH="${DATABASE_PATH:-/app/data/bot.db}"
export PYTHONPATH="${PYTHONPATH:-/app}"
export GROK_MODEL="${GROK_MODEL:-grok-4.3}"
export GROK_BASE_URL="${GROK_BASE_URL:-https://api.x.ai/v1}"

cd /app || { echo "[start] FATAL: /app missing"; sleep 60; exit 1; }
if [ ! -d /app/app ]; then
  echo "[start] FATAL: app package missing — volume must be /app/data only"
  ls -la /app || true
  sleep 120
  exit 1
fi

mkdir -p /app/data
echo "[start] GitHub Rising bot | AI=Grok model=$GROK_MODEL | PORT=$PORT"
exec python3 -m app.main
