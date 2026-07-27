#!/usr/bin/env bash
# 1) Bot binds PORT immediately (Railway health / runtime)
# 2) Ollama starts a few seconds later (must not block HTTP)
set -uo pipefail

export PORT="${PORT:-8080}"
export OLLAMA_HOST="${OLLAMA_HOST:-127.0.0.1:11434}"
export OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://127.0.0.1:11434}"
export OLLAMA_MODEL="${OLLAMA_MODEL:-llama3.2:1b}"
export DATABASE_PATH="${DATABASE_PATH:-/app/data/bot.db}"
export EMBEDDED_OLLAMA="${EMBEDDED_OLLAMA:-1}"

mkdir -p /app/data /root/.ollama

echo "[start] ===== github rising bot ====="
echo "[start] PORT=$PORT"
echo "[start] MODEL=$OLLAMA_MODEL"
echo "[start] EMBEDDED_OLLAMA=$EMBEDDED_OLLAMA"
echo "[start] python: $(command -v python3) $($(command -v python3) --version 2>&1)"
echo "[start] ollama: $(command -v ollama || echo missing)"

start_ollama_later() {
  if [ "$EMBEDDED_OLLAMA" != "1" ]; then
    echo "[start] EMBEDDED_OLLAMA!=1 — skipping ollama"
    return 0
  fi
  # Let HTTP come up first so healthcheck / process stay alive
  sleep 8
  echo "[start] starting ollama serve..."
  ollama serve >>/tmp/ollama.log 2>&1 &
  echo "[start] ollama pid=$!"

  for i in $(seq 1 90); do
    if curl -sf "http://127.0.0.1:11434/api/tags" >/dev/null 2>&1; then
      echo "[start] ollama API ready (${i}s after serve)"
      break
    fi
    sleep 1
  done

  if ollama show "$OLLAMA_MODEL" >/dev/null 2>&1; then
    echo "[start] model present: $OLLAMA_MODEL"
  else
    echo "[start] pulling $OLLAMA_MODEL (background, may take minutes)..."
    ollama pull "$OLLAMA_MODEL" >>/tmp/ollama.log 2>&1 \
      && echo "[start] model ready: $OLLAMA_MODEL" \
      || echo "[start] model pull failed — see /tmp/ollama.log" >&2
  fi
}

start_ollama_later &

echo "[start] launching python -m app.main on 0.0.0.0:$PORT"
# If python crashes, log and keep container visible in Railway logs
if ! exec python3 -m app.main; then
  echo "[start] FATAL: python exited $?" >&2
  tail -n 50 /tmp/ollama.log 2>/dev/null || true
  sleep 30
  exit 1
fi
