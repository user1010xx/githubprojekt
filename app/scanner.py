from __future__ import annotations

import logging

from app.config import Settings
from app.db import Database
from app.github_client import GitHubClient, RepoCandidate
from app.summarizer import Summarizer
from app.telegram_client import TelegramClient

logger = logging.getLogger(__name__)


class RisingScanner:
    def __init__(
        self,
        settings: Settings,
        db: Database,
        github: GitHubClient,
        summarizer: Summarizer,
        telegram: TelegramClient,
    ) -> None:
        self.settings = settings
        self.db = db
        self.github = github
        self.summarizer = summarizer
        self.telegram = telegram

    async def run_once(self) -> int:
        """Scan once and notify. Returns number of messages sent."""
        settings = self.settings
        candidates = await self.github.fetch_candidates(settings.max_candidates)
        logger.info("Fetched %s candidate repos", len(candidates))

        if not candidates:
            logger.warning("No candidates from GitHub search")
            return 0

        rising: list[RepoCandidate] = []

        for repo in candidates:
            try:
                await self.db.record_snapshot(repo.full_name, repo.stars)
                stars_24h = await self._estimate_stars_24h(repo)
                repo.stars_24h = max(0, stars_24h)
            except Exception:
                logger.exception("Failed measuring %s", repo.full_name)
                continue

            logger.info(
                "%s → +%s stars/24h (total %s)",
                repo.full_name,
                repo.stars_24h,
                repo.stars,
            )

            if repo.stars_24h < settings.min_stars_24h:
                continue

            if await self.db.was_notified_recently(
                repo.full_name, settings.dedup_hours
            ):
                logger.info("Skip (recently notified): %s", repo.full_name)
                continue

            rising.append(repo)

        rising.sort(key=lambda r: r.stars_24h, reverse=True)
        # Cap per cycle to avoid long Ollama backlog / Telegram flood
        to_notify = rising[: settings.max_notifications_per_scan]
        if len(rising) > len(to_notify):
            logger.info(
                "Capping notifications %s → %s",
                len(rising),
                len(to_notify),
            )

        sent = 0
        for repo in to_notify:
            try:
                repo.readme_excerpt = await self.github.fetch_readme_excerpt(
                    repo.full_name
                )
                summary = await self.summarizer.summarize(repo)
                header = (
                    f"🚀 RISING  ·  +{repo.stars_24h} star / ~24s  ·  ⭐ {repo.stars}\n"
                    f"{'─' * 28}\n"
                )
                message = header + summary
                await self.telegram.send_message(message)
                await self.db.mark_notified(
                    repo.full_name, repo.stars_24h, repo.stars
                )
                sent += 1
            except Exception:
                logger.exception("Failed to notify for %s", repo.full_name)

        logger.info(
            "Scan done. Rising: %s, notified attempt: %s, sent: %s",
            len(rising),
            len(to_notify),
            sent,
        )
        return sent

    async def _estimate_stars_24h(self, repo: RepoCandidate) -> int:
        api_count = await self.github.count_stars_last_24h(
            repo.full_name, repo.stars
        )
        snap_delta = await self._snapshot_delta(repo)

        if api_count < 0:
            # API could not measure — trust snapshot only
            return snap_delta

        # Prefer the stronger signal (API may undercount if >800 stars/day)
        return max(api_count, snap_delta)

    async def _snapshot_delta(self, repo: RepoCandidate) -> int:
        past = await self.db.stars_about_24h_ago(repo.full_name)
        if past is None:
            return 0
        return max(0, repo.stars - past)
