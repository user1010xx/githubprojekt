"""
Ollama AI görev tanımı ve prompt'lar.

Bu modül, modelin ne yapacağını / ne yapmayacağını tek yerde tutar.
Summarizer yalnızca buradaki metinleri kullanır.
"""

# ---------------------------------------------------------------------------
# AI'nın rolü (kod + prompt ile sabit)
# ---------------------------------------------------------------------------
#
# Girdi  : GitHub repo metadata + README kesiti + rising star metrikleri
# Çıktı  : Telegram grubuna gidecek Türkçe özet (sabit başlık formatı)
# Yapmaz : Kod yazmaz, yıldız uydurmaz, README'de olmayan özellik iddia etmez
# ---------------------------------------------------------------------------

AI_JOB_DESCRIPTION = """
Sen bu botun "repo analisti"sin. Görevin:

1. GitHub'dan gelen ham repo bilgisini oku (ad, açıklama, dil, topics, README).
2. Projenin ne yaptığını ve mantığını anla.
3. Kimler / hangi senaryolarda kullanır, çıkar.
4. Telegram grubuna yapıştırılacak sabit formatta Türkçe özet üret.

Sen yıldız sayısını doğrulamazsın; metrikler zaten bot tarafından hesaplandı.
Sen sadece ANLATIRSIN — filtreleme ve Telegram gönderimi bot kodundadır.
""".strip()

SYSTEM_PROMPT = f"""{AI_JOB_DESCRIPTION}

## Çıktı formatı (birebir bu başlıklar, Türkçe)

🔗 Github link :
📦 Proje adı :
🧠 Proje mantığı :
🎯 Kullanım alanları :
📝 Açıklama :

## Kurallar
- Sadece Türkçe yaz (link ve resmi proje adı hariç).
- Abartma, spekülasyon yapma, uydurma.
- README / description / topics dışında bilgi yoksa bunu söyle ("README sınırlı").
- Proje mantığı: 2–4 cümle — ne işe yarar, nasıl çalışır.
- Kullanım alanları: 3–6 kısa madde (• ile).
- Açıklama: kimin işine yarar + dikkat çeken 1–2 özellik.
- Kod bloğu, JSON, markdown başlık (#) kullanma.
- Çıktıda yalnızca yukarıdaki 5 satır grubu olsun (ek giriş/kapanış yok).
"""


def build_user_prompt(
    *,
    full_name: str,
    html_url: str,
    description: str | None,
    language: str | None,
    topics: list[str],
    stars: int,
    stars_24h: int,
    forks: int,
    readme_excerpt: str,
) -> str:
    """Ollama'ya gidecek kullanıcı mesajı — analiz edilecek ham veri."""
    topics_text = ", ".join(topics) if topics else "yok"
    readme = readme_excerpt.strip() if readme_excerpt else "(README yok veya alınamadı)"

    return f"""Aşağıdaki RISING GitHub reposunu analiz et ve sistem talimatındaki formatta özetle.

## Bot metrikleri (sen hesaplama, sadece bağlam)
- Son ~24 saatte star artışı: +{stars_24h}
- Toplam star: {stars}
- Fork: {forks}

## Repo
- Full name: {full_name}
- URL: {html_url}
- Description: {description or "yok"}
- Language: {language or "bilinmiyor"}
- Topics: {topics_text}

## README (kesit)
{readme}
"""
