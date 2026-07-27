from __future__ import annotations

import logging
from datetime import datetime, timezone

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
                "CATCH-UP MODE: since %s min=+%s max_msg=%s",
                cutoff.isoformat(),
                settings.min_stars_24h,
                max_notify,
            )
        else:
            cutoff = rolling_24h_cutoff()
            max_notify = settings.max_notifications_per_scan
            logger.info(
                "Normal mode: ~24h min=+%s max_msg=%s",
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
            return 0

        rising: list[RepoCandidate] = []

        for repo in candidates:
            try:
                # Snapshot BEFORE measuring growth so previous scan is available next time
                await self.db.record_snapshot(repo.full_name, repo.stars)
                stars_delta = await self._estimate_stars_since(repo, cutoff)
                repo.stars_24h = max(0, stars_delta)
            except Exception:
                logger.exception("Failed measuring %s", repo.full_name)
                continue

            logger.info(
                "%s → +%s stars (%s) total=%s",
                repo.full_name,
                repo.stars_24h,
                label,
                repo.stars,
            )

            if repo.stars_24h < settings.min_stars_24h:
                continue

            dedup_h = 6 if catchup else settings.dedup_hours
            if await self.db.was_notified_recently(repo.full_name, dedup_h):
                logger.info("Skip (recently notified): %s", repo.full_name)
                continue

            rising.append(repo)

        rising.sort(key=lambda r: r.stars_24h, reverse=True)
        to_notify = rising[:max_notify]
        if len(rising) > len(to_notify):
            logger.info("Capping notifications %s → %s", len(rising), len(to_notify))

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
                await self.telegram.send_message(header + summary)
                await self.db.mark_notified(
                    repo.full_name, repo.stars_24h, repo.stars
                )
                sent += 1
            except Exception:
                logger.exception("Failed to notify for %s", repo.full_name)

        if catchup:
            await self.db.mark_morning_catchup_done()
            logger.info("Catch-up done (sent=%s). Next: rolling 24h.", sent)

        logger.info(
            "Scan done. Rising=%s attempt=%s sent=%s",
            len(rising),
            len(to_notify),
            sent,
        )
        return sent

    async def _estimate_stars_since(
        self, repo: RepoCandidate, cutoff: datetime
    ) -> int:
        """
        Rising score from multiple signals (token may block stargazer lists):

        1) GraphQL/REST stargazer timestamps (if token allows)
        2) Snapshot growth (our DB) — works without stargazer permission
        3) New repo created inside window → total stars count as growth
        """
        scores: list[int] = []

        # 1) API timestamps (often FORBIDDEN on fine-grained PAT)
        api_count = await self.github.count_stars_since(
            repo.full_name, repo.stars, cutoff
        )
        if api_count >= 0:
            scores.append(api_count)
        else:
            logger.debug(
                "Stargazer history unavailable for %s (token/permission) — using snapshots",
                repo.full_name,
            )

        # 2) Snapshot deltas (no special GitHub permission)
        past_24 = await self.db.stars_about_24h_ago(repo.full_name)
        if past_24 is not None:
            scores.append(max(0, repo.stars - past_24))

        # Growth since we first saw this repo (after 2+ scans)
        # previous snapshot must be at least 5 minutes old (not the one we just wrote)
        prev = await self.db.previous_snapshot_stars(
            repo.full_name, min_age_seconds=300
        )
        if prev is not None:
            scores.append(max(0, repo.stars - prev))

        oldest = await self.db.oldest_snapshot_stars(repo.full_name)
        if oldest is not None:
            # If oldest is from "just now" only one snapshot exists — skip
            # oldest_snapshot after record_snapshot includes current; use prev instead
            pass

        # 3) Brand-new repo in window: all current stars are "since creation"
        if repo.created_at is not None:
            created = repo.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if created >= cutoff and repo.stars > 0:
                scores.append(repo.stars)

        if not scores:
            return 0
        return max(scores)
