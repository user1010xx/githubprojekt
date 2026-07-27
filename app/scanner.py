from __future__ import annotations

import logging
from datetime import datetime

from app.config import Settings
from app.db import Database
from app.github_client import GitHubClient, RepoCandidate
from app.summarizer import Summarizer
from app.telegram_client import TelegramClient
from app.time_window import rolling_24h_cutoff, start_of_today, window_label

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

        catchup = False
        if settings.morning_catchup_once:
            catchup = not await self.db.is_morning_catchup_done()

        if catchup:
            cutoff = start_of_today(settings.catchup_timezone)
            max_notify = settings.catchup_max_notifications
            logger.info(
                "CATCH-UP MODE (one-time): stars since %s (%s), min=+%s, max_msg=%s",
                cutoff.isoformat(),
                settings.catchup_timezone,
                settings.min_stars_24h,
                max_notify,
            )
        else:
            cutoff = rolling_24h_cutoff()
            max_notify = settings.max_notifications_per_scan
            logger.info(
                "Normal mode: rolling ~24h, min=+%s star, max_msg=%s",
                settings.min_stars_24h,
                max_notify,
            )

        label = window_label(cutoff, catchup=catchup)

        candidates = await self.github.fetch_candidates(settings.max_candidates)
        logger.info("Fetched %s candidate repos", len(candidates))

        if not candidates:
            logger.warning("No candidates from GitHub search")
            if catchup:
                await self.db.mark_morning_catchup_done()
                logger.info("Catch-up marked done (no candidates)")
            return 0

        rising: list[RepoCandidate] = []

        for repo in candidates:
            try:
                await self.db.record_snapshot(repo.full_name, repo.stars)
                stars_delta = await self._estimate_stars_since(repo, cutoff)
                repo.stars_24h = max(0, stars_delta)
            except Exception:
                logger.exception("Failed measuring %s", repo.full_name)
                continue

            logger.info(
                "%s → +%s stars (%s) (total %s)",
                repo.full_name,
                repo.stars_24h,
                label,
                repo.stars,
            )

            if repo.stars_24h < settings.min_stars_24h:
                continue

            # Catch-up: more lenient dedup (still skip if notified in last 6h)
            dedup_h = 6 if catchup else settings.dedup_hours
            if await self.db.was_notified_recently(repo.full_name, dedup_h):
                logger.info("Skip (recently notified): %s", repo.full_name)
                continue

            rising.append(repo)

        rising.sort(key=lambda r: r.stars_24h, reverse=True)
        to_notify = rising[:max_notify]
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
                mode_tag = "CATCH-UP" if catchup else "RISING"
                header = (
                    f"🚀 {mode_tag}  ·  +{repo.stars_24h} star / {label}  "
                    f"·  ⭐ {repo.stars}\n"
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

        if catchup:
            await self.db.mark_morning_catchup_done()
            logger.info(
                "Morning catch-up finished and marked done (sent=%s). "
                "Next scans use rolling 24h only.",
                sent,
            )

        logger.info(
            "Scan done. Rising: %s, notified attempt: %s, sent: %s",
            len(rising),
            len(to_notify),
            sent,
        )
        return sent

    async def _estimate_stars_since(
        self, repo: RepoCandidate, cutoff: datetime
    ) -> int:
        api_count = await self.github.count_stars_since(
            repo.full_name, repo.stars, cutoff
        )
        snap_delta = await self._snapshot_delta(repo)

        if api_count < 0:
            return snap_delta

        return max(api_count, snap_delta)

    async def _snapshot_delta(self, repo: RepoCandidate) -> int:
        past = await self.db.stars_about_24h_ago(repo.full_name)
        if past is None:
            return 0
        return max(0, repo.stars - past)
