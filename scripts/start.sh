#!/usr/bin/env bash
# /start.sh — volume-safe entrypoint
set -uo pipefail

export PORT="${PORT:-8080}"
export OLLAMA_HOST="${OLLAMA_HOST:-0.0.0.0:11434}"
export OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://127.0.0.1:11434}"
export OLLAMA_MODEL="${OLLAMA_MODEL:-llama3.2:1b}"
export DATABASE_PATH="${DATABASE_PATH:-/app/data/bot.db}"
export EMBEDDED_OLLAMA="${EMBEDDED_OLLAMA:-1}"
export PYTHONPATH="${PYTHONPATH:-/app}"

cd /app || { echo "[start] FATAL: /app missing"; sleep 60; exit 1; }
if [ ! -d /app/app ]; then
  echo "[start] FATAL: code missing — mount volume at /app/data only"
  ls -la /app || true
  sleep 120
  exit 1
fi

mkdir -p /app/data /root/.ollama
echo "[start] PORT=$PORT MODEL=$OLLAMA_MODEL EMBEDDED_OLLAMA=$EMBEDDED_OLLAMA"
echo "[start] ollama bin: $(command -v ollama || echo MISSING)"

if [ "$EMBEDDED_OLLAMA" = "1" ] && command -v ollama >/dev/null 2>&1; then
  (
    echo "[ollama] serve starting..."
    # Direct background — no pipe (pipe can break process group on Railway)
    ollama serve >>/proc/1/fd/1 2>>/proc/1/fd/2 &
    SPID=$!
    echo "[ollama] pid=$SPID"

    for i in $(seq 1 90); do
      if curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
        echo "[ollama] API up after ${i}s"
        break
      fi
      sleep 1
    done

    if curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
      if ollama show "$OLLAMA_MODEL" >/dev/null 2>&1; then
        echo "[ollama] model present: $OLLAMA_MODEL"
      else
        echo "[ollama] pulling $OLLAMA_MODEL ..."
        ollama pull "$OLLAMA_MODEL" \
          && echo "[ollama] model ready" \
          || echo "[ollama] pull FAILED"
      fi
    else
      echo "[ollama] API never came up — bot will use template summaries"
    fi
  ) &
else
  echo "[ollama] skipped (disabled or binary missing)"
fi

echo "[start] python bot"
exec python3 -m app.main
