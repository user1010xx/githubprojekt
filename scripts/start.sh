#!/usr/bin/env bash
# /start.sh — outside /app (volume-safe)
# Start Ollama ASAP + pull model in background; bot binds PORT immediately.
set -uo pipefail

export PORT="${PORT:-8080}"
# Listen on all interfaces inside container (client still uses 127.0.0.1)
export OLLAMA_HOST="${OLLAMA_HOST:-0.0.0.0:11434}"
export OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://127.0.0.1:11434}"
export OLLAMA_MODEL="${OLLAMA_MODEL:-llama3.2:1b}"
export DATABASE_PATH="${DATABASE_PATH:-/app/data/bot.db}"
export EMBEDDED_OLLAMA="${EMBEDDED_OLLAMA:-1}"
export PYTHONPATH="${PYTHONPATH:-/app}"

cd /app || {
  echo "[start] FATAL: /app missing — mount volume at /app/data only"
  sleep 60
  exit 1
}

if [ ! -d /app/app ]; then
  echo "[start] FATAL: /app/app missing — volume probably mounted on /app"
  ls -la /app || true
  sleep 120
  exit 1
fi

mkdir -p /app/data /root/.ollama

echo "[start] ===== github rising bot ====="
echo "[start] PORT=$PORT MODEL=$OLLAMA_MODEL EMBEDDED_OLLAMA=$EMBEDDED_OLLAMA"
echo "[start] python=$(command -v python3) ollama=$(command -v ollama || echo missing)"

start_ollama() {
  if [ "$EMBEDDED_OLLAMA" != "1" ]; then
    echo "[start] EMBEDDED_OLLAMA!=1 — skip ollama"
    return 0
  fi

  echo "[start] starting ollama serve immediately..."
  # Keep logs visible in Railway via stdout tee
  ollama serve 2>&1 | sed -u 's/^/[ollama] /' &
  echo "[start] ollama serve launched"

  for i in $(seq 1 120); do
    if curl -sf "http://127.0.0.1:11434/api/tags" >/dev/null 2>&1; then
      echo "[start] Ollama API ready (${i}s)"
      break
    fi
    sleep 1
  done

  if ! curl -sf "http://127.0.0.1:11434/api/tags" >/dev/null 2>&1; then
    echo "[start] WARNING: Ollama API not up after 120s — AI fallback until fixed" >&2
    tail -n 30 /tmp/ollama.log 2>/dev/null || true
    return 0
  fi

  if ollama show "$OLLAMA_MODEL" >/dev/null 2>&1; then
    echo "[start] model already present: $OLLAMA_MODEL"
  else
    echo "[start] pulling $OLLAMA_MODEL (first time can take several minutes)..."
    if ollama pull "$OLLAMA_MODEL"; then
      echo "[start] model ready: $OLLAMA_MODEL"
    else
      echo "[start] WARNING: ollama pull failed for $OLLAMA_MODEL" >&2
    fi
  fi
}

# Run Ollama bootstrap in background so Python binds /health quickly
start_ollama &

echo "[start] launching python -m app.main"
exec python3 -m app.main
