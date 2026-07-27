from __future__ import annotations

import asyncio
import base64
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import httpx

logger = logging.getLogger(__name__)


@dataclass
class RepoCandidate:
    full_name: str
    name: str
    html_url: str
    description: str | None
    language: str | None
    stars: int
    forks: int
    topics: list[str] = field(default_factory=list)
    default_branch: str = "main"
    is_fork: bool = False
    stars_24h: int = 0
    readme_excerpt: str = ""


class GitHubClient:
    def __init__(self, token: str) -> None:
        self._client = httpx.AsyncClient(
            base_url="https://api.github.com",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token.strip()}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "github-rising-telegram-bot",
            },
            timeout=30.0,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, **kwargs) -> httpx.Response:
        response = await self._client.get(path, **kwargs)
        if response.status_code == 403:
            remaining = response.headers.get("X-RateLimit-Remaining")
            logger.error(
                "GitHub 403 on %s (rate remaining=%s): %s",
                path,
                remaining,
                response.text[:300],
            )
        response.raise_for_status()
        return response

    async def fetch_candidates(self, limit: int) -> list[RepoCandidate]:
        """Collect active public repos likely to be rising."""
        limit = max(1, limit)
        seen: set[str] = set()
        candidates: list[RepoCandidate] = []

        day = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
        queries = [
            "stars:>100 fork:false",
            "stars:50..500 fork:false",
            f"stars:>200 pushed:>{day} fork:false",
        ]

        per_query = max(10, limit // len(queries) + 5)
        for query in queries:
            try:
                response = await self._get(
                    "/search/repositories",
                    params={
                        "q": query,
                        "sort": "updated",
                        "order": "desc",
                        "per_page": min(per_query, 30),
                    },
                )
                items = response.json().get("items", [])
            except httpx.HTTPError as exc:
                logger.warning("Search failed for %r: %s", query, exc)
                continue

            for item in items:
                full_name = item.get("full_name") or ""
                if not full_name or full_name in seen or item.get("fork"):
                    continue
                if item.get("archived") or item.get("disabled"):
                    continue
                seen.add(full_name)
                candidates.append(
                    RepoCandidate(
                        full_name=full_name,
                        name=item.get("name") or full_name.split("/")[-1],
                        html_url=item.get("html_url")
                        or f"https://github.com/{full_name}",
                        description=item.get("description"),
                        language=item.get("language"),
                        stars=int(item.get("stargazers_count") or 0),
                        forks=int(item.get("forks_count") or 0),
                        topics=list(item.get("topics") or []),
                        default_branch=item.get("default_branch") or "main",
                        is_fork=bool(item.get("fork")),
                    )
                )
                if len(candidates) >= limit:
                    return candidates

            # Be gentle with search secondary rate limit (30 req/min)
            await asyncio.sleep(0.5)

        return candidates

    async def count_stars_since(
        self,
        full_name: str,
        total_stars: int,
        cutoff: datetime,
    ) -> int:
        """
        Count stars with starred_at >= cutoff (walk newest stargazer pages).

        Returns:
          >= 0 : counted stars
          -1   : could not measure (API blocked / error) — use snapshot fallback
        """
        if total_stars <= 0:
            return 0

        if "/" not in full_name:
            logger.warning("Invalid full_name: %s", full_name)
            return -1

        if cutoff.tzinfo is None:
            cutoff = cutoff.replace(tzinfo=timezone.utc)

        owner, repo = full_name.split("/", 1)
        per_page = 100
        last_page = max(1, (total_stars + per_page - 1) // per_page)
        # GitHub list endpoints effectively cap around 400 pages for some resources
        last_page = min(last_page, 400)

        count = 0
        pages_checked = 0
        max_pages = 8  # up to 800 most recent stars
        saw_error = False

        for page in range(last_page, 0, -1):
            if pages_checked >= max_pages:
                break
            try:
                response = await self._client.get(
                    f"/repos/{owner}/{repo}/stargazers",
                    params={"per_page": per_page, "page": page},
                    headers={"Accept": "application/vnd.github.star+json"},
                )
                if response.status_code in (403, 404, 422):
                    logger.debug(
                        "Stargazers unavailable for %s (%s)",
                        full_name,
                        response.status_code,
                    )
                    return -1 if pages_checked == 0 else count
                response.raise_for_status()
                rows = response.json()
            except httpx.HTTPError as exc:
                logger.warning(
                    "Stargazers failed for %s p%s: %s", full_name, page, exc
                )
                saw_error = True
                break

            if not isinstance(rows, list) or not rows:
                break

            pages_checked += 1
            # Full list is oldest-first; high page numbers are newer.
            # Within a page, walk newest → oldest.
            for entry in reversed(rows):
                if not isinstance(entry, dict):
                    continue
                starred_raw = entry.get("starred_at")
                if not starred_raw:
                    continue
                try:
                    starred_at = datetime.fromisoformat(
                        str(starred_raw).replace("Z", "+00:00")
                    )
                except ValueError:
                    continue
                if starred_at.tzinfo is None:
                    starred_at = starred_at.replace(tzinfo=timezone.utc)
                if starred_at >= cutoff:
                    count += 1
                else:
                    return count

            oldest = rows[0].get("starred_at") if isinstance(rows[0], dict) else None
            if oldest:
                try:
                    oldest_dt = datetime.fromisoformat(
                        str(oldest).replace("Z", "+00:00")
                    )
                    if oldest_dt.tzinfo is None:
                        oldest_dt = oldest_dt.replace(tzinfo=timezone.utc)
                    if oldest_dt < cutoff:
                        return count
                except ValueError:
                    pass

            await asyncio.sleep(0.05)

        if pages_checked == 0 and saw_error:
            return -1
        return count

    async def count_stars_last_24h(self, full_name: str, total_stars: int) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        return await self.count_stars_since(full_name, total_stars, cutoff)

    async def fetch_readme_excerpt(self, full_name: str, max_chars: int = 4000) -> str:
        if "/" not in full_name:
            return ""
        owner, repo = full_name.split("/", 1)
        try:
            response = await self._client.get(f"/repos/{owner}/{repo}/readme")
            if response.status_code == 404:
                return ""
            response.raise_for_status()
            data = response.json()
            content = data.get("content") or ""
            encoding = data.get("encoding")
            if encoding == "base64":
                raw = base64.b64decode(content)
                text = raw.decode("utf-8", errors="replace")
            else:
                text = str(content)
            return text.strip()[:max_chars]
        except httpx.HTTPError as exc:
            logger.warning("README fetch failed for %s: %s", full_name, exc)
            return ""
        except (ValueError, TypeError) as exc:
            logger.warning("README parse failed for %s: %s", full_name, exc)
            return ""
