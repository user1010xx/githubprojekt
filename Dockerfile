# Tek image: Ollama (gömülü açık kaynak AI) + GitHub Rising bot
# Railway / Docker Compose: ayrı Ollama servisi gerekmez.

FROM ollama/ollama:latest

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_BREAK_SYSTEM_PACKAGES=1

# Python + curl (health / start script)
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        python3-venv \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3 /usr/local/bin/python \
    && ln -sf /usr/bin/python3 /usr/bin/python

WORKDIR /app

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts/start.sh /app/scripts/start.sh
RUN chmod +x /app/scripts/start.sh \
    && mkdir -p /app/data /root/.ollama

# Gömülü Ollama varsayılanları (API key yok)
ENV OLLAMA_HOST=0.0.0.0:11434 \
    OLLAMA_BASE_URL=http://127.0.0.1:11434 \
    OLLAMA_MODEL=llama3.2:1b \
    DATABASE_PATH=/app/data/bot.db \
    PORT=8080

# 8080 = bot health | 11434 = ollama (opsiyonel expose)
EXPOSE 8080 11434

# ollama image ENTRYPOINT'ini devre dışı bırak
ENTRYPOINT []
CMD ["/bin/bash", "/app/scripts/start.sh"]
