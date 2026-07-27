"""
Ollama yokken / hata olunca kullanılan kural tabanlı Türkçe özet.
Ham description dump'ı yerine okunabilir 5 başlıklı format üretir.
"""

from __future__ import annotations

import re

from app.github_client import RepoCandidate


def _clean(text: str, max_len: int = 500) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) > max_len:
        text = text[: max_len - 1].rstrip() + "…"
    return text


def _readme_blurb(readme: str) -> str:
    if not readme:
        return ""
    # Drop markdown noise
    lines: list[str] = []
    for line in readme.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            s = s.lstrip("#").strip()
        if s.startswith("!") or s.startswith("[!"):
            continue
        if s.startswith("```"):
            continue
        if s.startswith("|"):
            continue
        lines.append(s)
        if len(" ".join(lines)) > 400:
            break
    return _clean(" ".join(lines), 450)


def _guess_use_cases(repo: RepoCandidate, blurb: str) -> list[str]:
    text = " ".join(
        [
            repo.description or "",
            " ".join(repo.topics or []),
            blurb,
            repo.language or "",
            repo.full_name,
        ]
    ).lower()

    rules: list[tuple[list[str], str]] = [
        (["llm", "gpt", "openai", "agent", "ai ", "machine learning", "deep learning"], "AI / makine öğrenmesi projelerinde"),
        (["telegram", "bot"], "Telegram botları ve otomasyon"),
        (["cli", "command-line", "terminal"], "Komut satırı araçları ve geliştirici iş akışları"),
        (["api", "sdk", "http", "rest", "graphql"], "API entegrasyonu ve backend geliştirme"),
        (["web", "frontend", "react", "vue", "next"], "Web / frontend uygulamaları"),
        (["docker", "kubernetes", "k8s", "devops", "ci"], "DevOps ve altyapı otomasyonu"),
        (["security", "auth", "crypto", "vpn"], "Güvenlik ve kimlik doğrulama"),
        (["game", "unity", "godot"], "Oyun geliştirme"),
        (["data", "etl", "analytics", "spark"], "Veri işleme ve analitik"),
        (["mobile", "android", "ios", "flutter", "react-native"], "Mobil uygulama geliştirme"),
        (["self-host", "self hosted", "homelab"], "Kendi sunucunda barındırma (self-hosted)"),
        (["skill", "course", "learn", "tutorial", "eğitim", "课程"], "Öğrenme / eğitim içerikleri"),
    ]
    hits: list[str] = []
    for keys, label in rules:
        if any(k in text for k in keys):
            hits.append(f"• {label}")
        if len(hits) >= 4:
            break

    if repo.language:
        hits.append(f"• {repo.language} ekosisteminde çalışanlar")
    if not hits:
        hits = [
            "• Açık kaynak keşfi ve deneme",
            "• Benzer problemlere referans / başlangıç noktası",
            "• Topluluk katkıları ve inceleme",
        ]
    return hits[:5]


def summarize_template(repo: RepoCandidate) -> str:
    blurb = _readme_blurb(repo.readme_excerpt)
    desc = _clean(repo.description or "")
    logic_parts = []
    if desc:
        logic_parts.append(desc)
    if blurb and blurb.lower() not in (desc or "").lower():
        logic_parts.append(blurb)
    if not logic_parts:
        logic_parts.append(
            f"{repo.full_name} adlı açık kaynak depo. README sınırlı; "
            "detay için GitHub sayfasına bakın."
        )
    logic = _clean(" ".join(logic_parts), 600)

    uses = _guess_use_cases(repo, blurb or desc)
    topics = ", ".join(repo.topics) if repo.topics else "belirtilmemiş"
    lang = repo.language or "belirtilmemiş"

    explanation = (
        f"Son ~24 saatte +{repo.stars_24h} star almış yükselen bir proje "
        f"(toplam ⭐ {repo.stars}). Dil: {lang}; konular: {topics}. "
        "Özet, depo metadata + README kesitinden üretildi."
    )

    return (
        f"🔗 Github link : {repo.html_url}\n"
        f"📦 Proje adı : {repo.full_name}\n"
        f"🧠 Proje mantığı : {logic}\n"
        f"🎯 Kullanım alanları :\n" + "\n".join(uses) + "\n"
        f"📝 Açıklama : {_clean(explanation, 400)}"
    )
