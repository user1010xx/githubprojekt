from __future__ import annotations

import logging

from app.github_client import RepoCandidate
from app.grok_client import GrokClient, GrokError
from app.prompts import SYSTEM_PROMPT, build_user_prompt
from app.template_summarizer import summarize_template

logger = logging.getLogger(__name__)


class Summarizer:
    """AI = xAI Grok. Hata olursa şablon özet."""

    def __init__(self, grok: GrokClient) -> None:
        self.grok = grok

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
            text = await self.grok.chat(system=SYSTEM_PROMPT, user=user_prompt)
            logger.info(
                "Grok summary ok: %s (%s chars)", repo.full_name, len(text)
            )
            return text
        except GrokError as exc:
            logger.error("Grok summary failed for %s: %s", repo.full_name, exc)
            return summarize_template(repo)
        except Exception:
            logger.exception("Unexpected AI error for %s", repo.full_name)
            return summarize_template(repo)
