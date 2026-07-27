# Railway-friendly: Python bot first, Ollama in same container.
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

# Ollama binary (install.sh needs zstd)
RUN curl -fsSL https://ollama.com/install.sh | sh

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# IMPORTANT: start script outside /app so volume mount /app/data never hides it
COPY scripts/start.sh /start.sh
RUN chmod +x /start.sh \
    && mkdir -p /app/data /root/.ollama \
    && sed -i 's/\r$//' /start.sh

ENV OLLAMA_HOST=0.0.0.0:11434 \
    OLLAMA_BASE_URL=http://127.0.0.1:11434 \
    OLLAMA_MODEL=llama3.2:1b \
    DATABASE_PATH=/app/data/bot.db \
    PORT=8080 \
    EMBEDDED_OLLAMA=1 \
    PYTHONPATH=/app

EXPOSE 8080

CMD ["/bin/bash", "/start.sh"]
