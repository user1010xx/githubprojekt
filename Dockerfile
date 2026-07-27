# Railway-friendly: Python bot first, Ollama optional in same container.
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        procps \
        bash \
        zstd \
    && rm -rf /var/lib/apt/lists/*

# Ollama binary (install.sh needs zstd to extract the archive)
RUN curl -fsSL https://ollama.com/install.sh | sh

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts/start.sh /app/scripts/start.sh
RUN chmod +x /app/scripts/start.sh \
    && mkdir -p /app/data /root/.ollama

ENV OLLAMA_HOST=127.0.0.1:11434 \
    OLLAMA_BASE_URL=http://127.0.0.1:11434 \
    OLLAMA_MODEL=llama3.2:1b \
    DATABASE_PATH=/app/data/bot.db \
    PORT=8080 \
    EMBEDDED_OLLAMA=1

EXPOSE 8080

# Bot is PID1-ish via start.sh; binds PORT immediately for health
CMD ["/bin/bash", "/app/scripts/start.sh"]
