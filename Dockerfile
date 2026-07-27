# Lightweight bot image — AI via xAI Grok API (no Ollama)
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts/start.sh /start.sh
RUN chmod +x /start.sh \
    && mkdir -p /app/data \
    && sed -i 's/\r$//' /start.sh

ENV DATABASE_PATH=/app/data/bot.db \
    PORT=8080 \
    GROK_MODEL=grok-4.3 \
    GROK_BASE_URL=https://api.x.ai/v1 \
    PYTHONPATH=/app

EXPOSE 8080

CMD ["/bin/bash", "/start.sh"]
