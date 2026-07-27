from __future__ import annotations

import logging
import time
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self.path)
        self._db.row_factory = aiosqlite.Row
        # WAL: better concurrent read during long scans
        await self._db.execute("PRAGMA journal_mode=WAL;")
        await self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS star_snapshots (
                full_name TEXT NOT NULL,
                stars INTEGER NOT NULL,
                captured_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_snapshots_name_time
                ON star_snapshots(full_name, captured_at);

            CREATE TABLE IF NOT EXISTS notifications (
                full_name TEXT PRIMARY KEY,
                stars_24h INTEGER NOT NULL,
                total_stars INTEGER NOT NULL,
                sent_at REAL NOT NULL
            );
            """
        )
        await self._db.commit()
        # Migrate old ISO-text schemas if present (best-effort, ignore errors)
        await self._maybe_migrate_legacy()
        logger.info("Database ready: %s", self.path)

    async def _maybe_migrate_legacy(self) -> None:
        """If captured_at/sent_at are text ISO, wipe snapshots (safe) once."""
        assert self._db is not None
        try:
            cursor = await self._db.execute(
                "SELECT captured_at FROM star_snapshots LIMIT 1"
            )
            row = await cursor.fetchone()
            if row is None:
                return
            sample = row[0]
            if isinstance(sample, str):
                logger.warning(
                    "Legacy text timestamps detected; clearing star_snapshots"
                )
                await self._db.execute("DELETE FROM star_snapshots")
                await self._db.commit()
        except Exception:
            logger.debug("No legacy migration needed", exc_info=True)

    def _require_db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("Database not connected")
        return self._db

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    async def record_snapshot(self, full_name: str, stars: int) -> None:
        db = self._require_db()
        now = time.time()
        await db.execute(
            "INSERT INTO star_snapshots(full_name, stars, captured_at) VALUES (?, ?, ?)",
            (full_name, stars, now),
        )
        # Keep ~3 days of history per repo
        cutoff = now - 3 * 24 * 3600
        await db.execute(
            "DELETE FROM star_snapshots WHERE full_name = ? AND captured_at < ?",
            (full_name, cutoff),
        )
        await db.commit()

    async def stars_about_24h_ago(self, full_name: str) -> int | None:
        """Return the snapshot closest to 24h ago (within ±6h), else older fallback."""
        db = self._require_db()
        now = time.time()
        target = now - 24 * 3600
        window_start = target - 6 * 3600
        window_end = target + 6 * 3600

        cursor = await db.execute(
            """
            SELECT stars, captured_at FROM star_snapshots
            WHERE full_name = ? AND captured_at BETWEEN ? AND ?
            ORDER BY ABS(captured_at - ?)
            LIMIT 1
            """,
            (full_name, window_start, window_end, target),
        )
        row = await cursor.fetchone()
        if row:
            return int(row["stars"])

        # Fallback: oldest snapshot that is at least 12h old
        older = now - 12 * 3600
        cursor = await db.execute(
            """
            SELECT stars FROM star_snapshots
            WHERE full_name = ? AND captured_at <= ?
            ORDER BY captured_at ASC
            LIMIT 1
            """,
            (full_name, older),
        )
        row = await cursor.fetchone()
        return int(row["stars"]) if row else None

    async def was_notified_recently(self, full_name: str, hours: int) -> bool:
        db = self._require_db()
        cutoff = time.time() - hours * 3600
        cursor = await db.execute(
            "SELECT 1 FROM notifications WHERE full_name = ? AND sent_at >= ?",
            (full_name, cutoff),
        )
        return await cursor.fetchone() is not None

    async def mark_notified(
        self, full_name: str, stars_24h: int, total_stars: int
    ) -> None:
        db = self._require_db()
        now = time.time()
        await db.execute(
            """
            INSERT INTO notifications(full_name, stars_24h, total_stars, sent_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(full_name) DO UPDATE SET
                stars_24h = excluded.stars_24h,
                total_stars = excluded.total_stars,
                sent_at = excluded.sent_at
            """,
            (full_name, stars_24h, total_stars, now),
        )
        await db.commit()
