# GitHub Rising → Telegram Bot (gömülü Ollama)

Son ~24 saatte **yüksek star artışı** (rising) gösteren public GitHub repolarını bulur, **container içindeki Ollama** ile Türkçe özetler ve bir **Telegram grubuna** iletir.

- Tarama: **10 dakika**
- AI: **projeye gömülü Ollama** (ayrı AI API key yok)
- Zorunlu sırlar: **Telegram token + GitHub token**
- Deploy: **Railway** veya `docker compose`

## Zorunlu ayarlar (2 token)

| # | Değişken | Ne |
|---|----------|-----|
| 1 | `TELEGRAM_BOT_TOKEN` | BotFather token |
| 1b | `TELEGRAM_CHAT_ID` | Grup id |
| 2 | `GITHUB_TOKEN` | GitHub PAT |

**Ollama ayrı kurulmaz.** Docker image içinde gelir; `scripts/start.sh` hem Ollama’yı hem botu başlatır.

## Mimari (gömülü AI)

```
┌─────────────────────────────────────┐
│  Tek container (Dockerfile)         │
│  ┌─────────────┐  ┌──────────────┐  │
│  │ ollama serve│←→│ Python bot   │  │
│  │ llama3.2:1b │  │ scan+Telegram│  │
│  └─────────────┘  └──────────────┘  │
└─────────────────────────────────────┘
```

| Dosya | Görev |
|-------|--------|
| `Dockerfile` | Ollama base + Python bot |
| `scripts/start.sh` | Ollama başlat → model pull → bot |
| `app/prompts.py` | AI görev tanımı + prompt |
| `app/ollama_client.py` | `127.0.0.1:11434` chat |
| `app/summarizer.py` | Özet katmanı |

Varsayılan model: **`llama3.2:1b`** (Railway RAM’ine uygun, açık ağırlık).  
Daha kaliteli istersen: `OLLAMA_MODEL=llama3.2` veya `llama3.2:3b` (daha fazla bellek).

## Railway

1. Repo bağla (Dockerfile build).
2. **Variables:**
   ```
   TELEGRAM_BOT_TOKEN=
   TELEGRAM_CHAT_ID=
   GITHUB_TOKEN=
   OLLAMA_MODEL=llama3.2:1b
   ```
3. **Volume önerisi (önemli):**
   - `/root/.ollama` → model her deploy’da yeniden inmesin  
   - `/app/data` → SQLite dedup kalsın  
4. Redeploy. İlk boot’ta model indirme **birkaç dakika** sürebilir.
5. Log’da ara: `Embedded Ollama starting`, `Ollama API ready`, `Model ready`, `Starting scan cycle`.

> Not: CPU’da 1B model yavaş olabilir; özet başına 30–120 sn normal.  
> Planında **en az ~2 GB RAM** olsun; yoksa OOM / restart riski var.

## Docker Compose (lokal)

```bash
copy .env.example .env   # tokenları doldur
docker compose up -d --build
```

Health: http://localhost:8080/health

## Telegram grup

1. BotFather → token  
2. Botu gruba ekle  
3. Chat id → `TELEGRAM_CHAT_ID`  
4. GitHub PAT → `GITHUB_TOKEN`

## AI ne yapar?

`app/prompts.py` içinde sabit:

1. Repo meta + README oku  
2. Mantık / kullanım alanı çıkar  
3. Şu formatta Türkçe yaz:

```
🔗 Github link :
📦 Proje adı :
🧠 Proje mantığı :
🎯 Kullanım alanları :
📝 Açıklama :
```

Rising filtre + Telegram gönderimi **bot kodunda**; model sadece anlatır.

## Opsiyonel env

```
OLLAMA_MODEL=llama3.2:1b
OLLAMA_BASE_URL=http://127.0.0.1:11434
MIN_STARS_24H=30
MAX_CANDIDATES=25
MAX_NOTIFICATIONS_PER_SCAN=5
SCAN_INTERVAL_SECONDS=600
```

## Yerel geliştirme (Docker’sız)

Sadece kodu koşturuyorsan makinede Ollama gerekir:

```bash
ollama serve
ollama pull llama3.2:1b
pip install -r requirements.txt
python -m app.main
```

Production yolu: **gömülü image** (Railway / Compose).
