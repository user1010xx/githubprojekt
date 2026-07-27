#!/usr/bin/env bash
# Lives at /start.sh (NOT under /app) so a volume on /app/data cannot hide it.
# 1) Bot binds PORT immediately
# 2) Ollama starts a few seconds later
set -uo pipefail

export PORT="${PORT:-8080}"
export OLLAMA_HOST="${OLLAMA_HOST:-127.0.0.1:11434}"
export OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://127.0.0.1:11434}"
export OLLAMA_MODEL="${OLLAMA_MODEL:-llama3.2:1b}"
export DATABASE_PATH="${DATABASE_PATH:-/app/data/bot.db}"
export EMBEDDED_OLLAMA="${EMBEDDED_OLLAMA:-1}"
export PYTHONPATH="${PYTHONPATH:-/app}"

cd /app || {
  echo "[start] FATAL: /app missing — is the volume mounted over the whole /app path?"
  echo "[start] Mount volume ONLY at /app/data (not /app)"
  sleep 60
  exit 1
}

if [ ! -d /app/app ]; then
  echo "[start] FATAL: /app/app package missing."
  echo "[start] Your Railway volume is almost certainly mounted on /app and wiped the image files."
  echo "[start] Fix: Volume mount path must be exactly: /app/data"
  ls -la /app || true
  sleep 120
  exit 1
fi

mkdir -p /app/data /root/.ollama

echo "[start] ===== github rising bot ====="
echo "[start] PORT=$PORT MODEL=$OLLAMA_MODEL"
echo "[start] python=$(command -v python3) ollama=$(command -v ollama || echo missing)"

start_ollama_later() {
  if [ "$EMBEDDED_OLLAMA" != "1" ]; then
    echo "[start] EMBEDDED_OLLAMA!=1 — skip ollama"
    return 0
  fi
  sleep 8
  echo "[start] starting ollama serve..."
  ollama serve >>/tmp/ollama.log 2>&1 &
  echo "[start] ollama pid=$!"

  for i in $(seq 1 90); do
    if curl -sf "http://127.0.0.1:11434/api/tags" >/dev/null 2>&1; then
      echo "[start] ollama API ready (${i}s)"
      break
    fi
    sleep 1
  done

  if ollama show "$OLLAMA_MODEL" >/dev/null 2>&1; then
    echo "[start] model present: $OLLAMA_MODEL"
  else
    echo "[start] pulling $OLLAMA_MODEL ..."
    ollama pull "$OLLAMA_MODEL" >>/tmp/ollama.log 2>&1 \
      && echo "[start] model ready" \
      || echo "[start] model pull failed" >&2
  fi
}

start_ollama_later &

echo "[start] launching python -m app.main"
exec python3 -m app.main
