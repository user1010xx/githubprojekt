#!/usr/bin/env bash
# Embedded Ollama + bot — tek container.
# ONEMLI: Bot HEMEN baslar (/health). Ollama arka planda gelir.
# Railway healthcheck "service unavailable" olmasin diye Python'u bekletmeyiz.
set -uo pipefail

MODEL="${OLLAMA_MODEL:-llama3.2:1b}"
OLLAMA_HOST_BIND="${OLLAMA_HOST:-0.0.0.0:11434}"
export OLLAMA_HOST="$OLLAMA_HOST_BIND"
export OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://127.0.0.1:11434}"
export OLLAMA_MODEL="$MODEL"
export DATABASE_PATH="${DATABASE_PATH:-/app/data/bot.db}"

# Railway PORT enjekte eder; yoksa 8080
export PORT="${PORT:-8080}"

mkdir -p /app/data /root/.ollama

echo "[start] PORT=$PORT MODEL=$MODEL OLLAMA_BASE_URL=$OLLAMA_BASE_URL"
echo "[start] Starting embedded Ollama in background..."

ollama serve &
OLLAMA_PID=$!
echo "[start] ollama serve pid=$OLLAMA_PID"

cleanup() {
  echo "[start] cleanup ollama pid=$OLLAMA_PID"
  kill "$OLLAMA_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Model pull tamamen arka planda (healthcheck'i bloke ETMEZ)
(
  echo "[start] Waiting for Ollama API (background pull worker)..."
  for i in $(seq 1 180); do
    if curl -sf "http://127.0.0.1:11434/api/tags" >/dev/null 2>&1; then
      echo "[start] Ollama API ready after ${i}s"
      break
    fi
    sleep 1
  done

  if ! curl -sf "http://127.0.0.1:11434/api/tags" >/dev/null 2>&1; then
    echo "[start] WARNING: Ollama API still down — bot will use fallback summaries" >&2
    exit 0
  fi

  if ollama show "$MODEL" >/dev/null 2>&1; then
    echo "[start] Model already present: $MODEL"
  else
    echo "[start] Pulling model $MODEL (may take several minutes)..."
    if ollama pull "$MODEL"; then
      echo "[start] Model ready: $MODEL"
    else
      echo "[start] WARNING: model pull failed" >&2
    fi
  fi
) &

# Kisa nefes: process table otursun, sonra bot = /health acik
sleep 2

echo "[start] Starting Telegram bot (health on :$PORT/health)..."
# exec: bot on plana gecer; ollama arka planda kalir (reparent)
trap - EXIT
exec python3 -m app.main
