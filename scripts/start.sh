#!/usr/bin/env bash
# Embedded Ollama + bot — tek container giriş noktası
set -euo pipefail

MODEL="${OLLAMA_MODEL:-llama3.2:1b}"
OLLAMA_HOST_BIND="${OLLAMA_HOST:-0.0.0.0:11434}"
export OLLAMA_HOST="$OLLAMA_HOST_BIND"

# Bot her zaman aynı container içindeki Ollama'ya konuşur
export OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://127.0.0.1:11434}"
export OLLAMA_MODEL="$MODEL"
export DATABASE_PATH="${DATABASE_PATH:-/app/data/bot.db}"

mkdir -p /app/data /root/.ollama

echo "[start] Embedded Ollama starting (host=$OLLAMA_HOST_BIND model=$MODEL)"

# Ollama sunucusu (arka plan)
ollama serve &
OLLAMA_PID=$!

cleanup() {
  echo "[start] Shutting down ollama pid=$OLLAMA_PID"
  kill "$OLLAMA_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# API ayağa kalksın (model indirmeden önce)
ready=0
for i in $(seq 1 120); do
  if curl -sf "http://127.0.0.1:11434/api/tags" >/dev/null 2>&1; then
    echo "[start] Ollama API ready (${i}s)"
    ready=1
    break
  fi
  sleep 1
done

if [ "$ready" -ne 1 ]; then
  echo "[start] ERROR: Ollama API did not become ready" >&2
  exit 1
fi

# Model yoksa çek — arka planda (Railway healthcheck bloke olmasın)
(
  if ollama show "$MODEL" >/dev/null 2>&1; then
    echo "[start] Model already present: $MODEL"
  else
    echo "[start] Pulling model $MODEL (first boot may take several minutes)..."
    if ollama pull "$MODEL"; then
      echo "[start] Model ready: $MODEL"
    else
      echo "[start] WARNING: model pull failed — summaries use fallback until fixed" >&2
    fi
  fi
) &

echo "[start] Starting Telegram bot..."
# exec: bot PID 1 sinyallerini alsın; trap yine ollama'yı kapatır
exec python3 -m app.main
