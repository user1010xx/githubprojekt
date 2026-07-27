from __future__ import annotations

import logging

from app.github_client import RepoCandidate
from app.ollama_client import OllamaClient, OllamaError
from app.prompts import SYSTEM_PROMPT, build_user_prompt
from app.template_summarizer import summarize_template

logger = logging.getLogger(__name__)


class Summarizer:
    """
    1) Ollama hazırsa AI özet
    2) Değilse kaliteli şablon özet (asla boş/çirkin fallback değil)
    """

    def __init__(self, ollama: OllamaClient, prefer_template: bool = False) -> None:
        self.ollama = ollama
        self.prefer_template = prefer_template

    async def summarize(self, repo: RepoCandidate) -> str:
        # Fast path: don't block the whole scan on cold Ollama for minutes
        if not self.prefer_template:
            try:
                ready = await self.ollama.ensure_ready(wait_seconds=45)
                if ready:
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
                    text = await self.ollama.chat(
                        system=SYSTEM_PROMPT, user=user_prompt, retries=1
                    )
                    if text and "Ollama" not in text[:40]:
                        logger.info(
                            "Ollama summary ok: %s (%s chars)",
                            repo.full_name,
                            len(text),
                        )
                        return text
            except OllamaError as exc:
                logger.warning(
                    "Ollama unavailable for %s (%s) — template summary",
                    repo.full_name,
                    exc,
                )
            except Exception:
                logger.exception(
                    "Ollama error for %s — template summary", repo.full_name
                )

        text = summarize_template(repo)
        logger.info("Template summary used: %s", repo.full_name)
        return text
