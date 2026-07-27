from __future__ import annotations

import logging

from app.github_client import RepoCandidate
from app.ollama_client import OllamaClient, OllamaError
from app.prompts import SYSTEM_PROMPT, build_user_prompt

logger = logging.getLogger(__name__)


class Summarizer:
    """
    AI katmanı = yalnızca Ollama.

    Görev tanımı ve prompt'lar: app/prompts.py
    Ağ çağrısı: app/ollama_client.py
    """

    def __init__(self, ollama: OllamaClient) -> None:
        self.ollama = ollama

    async def summarize(self, repo: RepoCandidate) -> str:
        user_prompt = build_user_prompt(
            full_name=repo.full_name,
            html_url=repo.html_url,
            description=repo.description,
            language=repo.language,
            topics=repo.topics,
            stars=repo.stars,
            stars_24h=repo.stars_24h,
            forks=repo.forks,
            readme_excerpt=repo.readme_excerpt,
        )
        try:
            text = await self.ollama.chat(system=SYSTEM_PROMPT, user=user_prompt)
            logger.info("Ollama summary ok: %s (%s chars)", repo.full_name, len(text))
            return text
        except OllamaError as exc:
            logger.error("Ollama summary failed for %s: %s", repo.full_name, exc)
            return self._fallback(repo)
        except Exception:
            logger.exception("Unexpected AI error for %s", repo.full_name)
            return self._fallback(repo)

    @staticmethod
    def _fallback(repo: RepoCandidate) -> str:
        """Ollama yoksa / hata olursa ham özet — bot yine mesaj atabilsin."""
        desc = repo.description or "Açıklama bulunamadı."
        lang = repo.language or "bilinmiyor"
        topics = ", ".join(repo.topics) if repo.topics else "—"
        return (
            f"🔗 Github link : {repo.html_url}\n"
            f"📦 Proje adı : {repo.full_name}\n"
            f"🧠 Proje mantığı : {desc}\n"
            f"🎯 Kullanım alanları : Dil: {lang}. Konular: {topics}.\n"
            f"📝 Açıklama : Son ~24 saatte +{repo.stars_24h} star "
            f"(toplam {repo.stars}). Ollama özeti şu an üretilemedi."
        )
