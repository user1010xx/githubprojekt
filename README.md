# GitHub Rising → Telegram Bot (Ollama AI)

Son ~24 saatte **yüksek star artışı** (rising) gösteren public GitHub repolarını bulur, **Ollama (açık kaynak AI)** ile Türkçe özetler ve bir **Telegram grubuna** iletir.

- Tarama: **10 dakika**
- AI: **yalnızca Ollama** (API key yok)
- Zorunlu sırlar: **Telegram token + GitHub token**
- Dağıtım: Railway veya Docker Compose

## Zorunlu ayarlar (2 token)

| # | Değişken | Ne |
|---|----------|-----|
| 1 | `TELEGRAM_BOT_TOKEN` | BotFather token |
| 1b | `TELEGRAM_CHAT_ID` | Grup id (token değil, hedef adres) |
| 2 | `GITHUB_TOKEN` | GitHub PAT |

AI için **üçüncü bir API key yok**. Özetleme Ollama üzerinden yapılır.

## AI ne yapar? (kod + prompt)

| Dosya | Görev |
|-------|--------|
| `app/prompts.py` | AI rolü, kurallar, çıktı formatı, user prompt şablonu |
| `app/ollama_client.py` | Ollama `/api/chat` çağrısı |
| `app/summarizer.py` | Repo → prompt → Ollama → metin (hata olursa fallback) |

AI **sadece özet üretir**. Rising filtreleme, star hesabı ve Telegram gönderimi bot kodundadır.

Çıktı formatı:

```
🔗 Github link :
📦 Proje adı :
🧠 Proje mantığı :
🎯 Kullanım alanları :
📝 Açıklama :
```

## Ollama kurulumu

### A) Bilgisayarında (geliştirme)

1. [Ollama](https://ollama.com) kur  
2. Model çek:
   ```bash
   ollama pull llama3.2
   ```
3. `.env`:
   ```env
   TELEGRAM_BOT_TOKEN=...
   TELEGRAM_CHAT_ID=...
   GITHUB_TOKEN=...
   OLLAMA_BASE_URL=http://127.0.0.1:11434
   OLLAMA_MODEL=llama3.2
   ```
4. Bot:
   ```bash
   pip install -r requirements.txt
   python -m app.main
   ```

### B) Docker Compose (bot + Ollama birlikte)

```bash
copy .env.example .env   # tokenları doldur
docker compose up -d
docker compose exec ollama ollama pull llama3.2
```

Compose içinde bot `OLLAMA_BASE_URL=http://ollama:11434` kullanır.

### C) Railway

Railway container’ında GPU’lu büyük model genelde pratik değil. Seçenekler:

1. **Ollama’yı ayrı çalıştır** (VPS / ev sunucusu / GPU’lu makine), public veya private URL ver:
   ```env
   OLLAMA_BASE_URL=https://ollama.senin-domainin.com
   OLLAMA_MODEL=llama3.2
   ```
2. Bot servisini Railway’de tut; sadece 2 token + `OLLAMA_BASE_URL` set et.

Volume önerisi: `/app/data` → SQLite dedup kalıcı olsun.

## Telegram grup

1. BotFather → bot → token  
2. Grup aç → botu ekle  
3. Chat id al (`getUpdates` veya id botu) → `TELEGRAM_CHAT_ID`  
4. `GITHUB_TOKEN` ekle  
5. Ollama’nın ayakta olduğundan emin ol  

## Opsiyonel env

```
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.2
MIN_STARS_24H=30
MAX_CANDIDATES=25
MAX_NOTIFICATIONS_PER_SCAN=5
DEDUP_HOURS=48
SCAN_INTERVAL_SECONDS=600
DATABASE_PATH=./data/bot.db
```

## Proje yapısı

```
app/
  main.py             # health + 10 dk döngü
  config.py           # 2 token + ollama ayarları
  github_client.py    # adaylar, 24s star, README
  scanner.py          # rising filtre + bildirim
  prompts.py          # AI görev tanımı + prompt
  ollama_client.py    # açık kaynak AI istemcisi
  summarizer.py       # AI özet katmanı
  telegram_client.py
  db.py
docker-compose.yml    # ollama + bot
Dockerfile
railway.toml
```

## Akış

```
GitHub (token) → rising adaylar → eşik geçti mi?
       ↓ evet
README + meta → Ollama (prompt) → Türkçe özet
       ↓
Telegram grup (token)
```
