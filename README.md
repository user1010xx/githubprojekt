# GitHub Rising → Telegram Bot (Grok 4.3)

Son ~24 saatte yükselen public GitHub repolarını bulur, **xAI Grok 4.3** ile Türkçe özetler, Telegram grubuna atar.

- Tarama: **10 dakika**
- AI: **Grok API** (`grok-4.3`) — Ollama yok
- Zorunlu: Telegram + GitHub + **XAI_API_KEY**

## Zorunlu env

| Değişken | Ne |
|----------|-----|
| `TELEGRAM_BOT_TOKEN` | BotFather |
| `TELEGRAM_CHAT_ID` | Grup id |
| `GITHUB_TOKEN` | GitHub PAT |
| `XAI_API_KEY` | https://console.x.ai/ |

Opsiyonel:
```
GROK_MODEL=grok-4.3
GROK_BASE_URL=https://api.x.ai/v1
MIN_STARS_24H=5
```

## Railway

1. Repo bağla  
2. Variables: 4 zorunlu key  
3. Volume (önerilir): `/app/data`  
4. **Ollama / `/root/.ollama` volume gerekmez** — silebilirsin  
5. Deploy sonrası grupta: `✅ GitHub Rising bot aktif` + `AI: Grok (grok-4.3)`

## Yerel

```bash
cp .env.example .env   # doldur
pip install -r requirements.txt
python -m app.main
```

## Akış

```
GitHub → rising (≥5 star) → Grok 4.3 özet → Telegram grup
```

Grok hata verirse şablon özet kullanılır (mesaj yine gider).
