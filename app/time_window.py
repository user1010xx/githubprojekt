"""Star-count time windows (rolling 24h vs one-time morning catch-up)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

# Kullanıcı Türkiye saati — "bugün sabah" = bugünün başı (Europe/Istanbul)
DEFAULT_TZ = "Europe/Istanbul"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def start_of_today(tz_name: str = DEFAULT_TZ) -> datetime:
    """Bugünün 00:00'ı (yerel), UTC aware datetime olarak."""
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")
    local_now = datetime.now(tz)
    local_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return local_start.astimezone(timezone.utc)


def rolling_24h_cutoff() -> datetime:
    return now_utc() - timedelta(hours=24)


def window_label(cutoff: datetime, catchup: bool) -> str:
    if catchup:
        local = cutoff.astimezone(ZoneInfo(DEFAULT_TZ))
        return f"bugün sabahından ({local.strftime('%d.%m %H:%M')} TR)"
    return "~24s"
