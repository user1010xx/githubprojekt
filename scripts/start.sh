#!/usr/bin/env bash
# Embedded Ollama + bot.
# Bot immediately binds PORT for Railway /health; Ollama starts in parallel.
set -uo pipefail

MODEL="${OLLAMA_MODEL:-llama3.2:1b}"
export OLLAMA_HOST="${OLLAMA_HOST:-0.0.0.0:11434}"
export OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://127.0.0.1:11434}"
export OLLAMA_MODEL="$MODEL"
export DATABASE_PATH="${DATABASE_PATH:-/app/data/bot.db}"
export PORT="${PORT:-8080}"

mkdir -p /app/data /root/.ollama

echo "[start] PORT=$PORT MODEL=$MODEL"

# Ollama may fail on low-RAM plans; never block the bot.
(
  echo "[start] ollama serve..."
  ollama serve >>/tmp/ollama.log 2>&1 &
  OPID=$!
  echo "[start] ollama pid=$OPID"

  for i in $(seq 1 120); do
    if curl -sf "http://127.0.0.1:11434/api/tags" >/dev/null 2>&1; then
      echo "[start] Ollama API up (${i}s)"
      break
    fi
    sleep 1
  done

  if ollama show "$MODEL" >/dev/null 2>&1; then
    echo "[start] model present: $MODEL"
  else
    echo "[start] pulling $MODEL ..."
    ollama pull "$MODEL" >>/tmp/ollama.log 2>&1 \
      && echo "[start] model ready: $MODEL" \
      || echo "[start] model pull failed (see /tmp/ollama.log)" >&2
  fi
  wait "$OPID" || true
) &

echo "[start] python bot now (health :$PORT/health)"
exec python3 -m app.main
