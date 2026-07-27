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
        self._token = token.strip()
        self._client = httpx.AsyncClient(
            base_url="https://api.github.com",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self._token}",
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
        """Collect public repos that are more likely to be rising (not only mega-repos)."""
        limit = max(1, limit)
        seen: set[str] = set()
        candidates: list[RepoCandidate] = []

        day7 = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
        day1 = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

        # Prefer mid-size / recently active — huge lists often 403 on REST stargazers
        queries = [
            (f"stars:20..2000 created:>{day7} fork:false", "stars"),
            (f"stars:10..5000 pushed:>{day1} fork:false", "updated"),
            ("stars:50..3000 fork:false", "updated"),
            (f"stars:>100 pushed:>{day7} fork:false", "updated"),
        ]

        per_query = max(10, limit // len(queries) + 8)
        for query, sort in queries:
            try:
                response = await self._get(
                    "/search/repositories",
                    params={
                        "q": query,
                        "sort": sort,
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
                stars = int(item.get("stargazers_count") or 0)
                # Skip ultra-huge repos (stargazer history is painful / noisy)
                if stars > 50000:
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
                        stars=stars,
                        forks=int(item.get("forks_count") or 0),
                        topics=list(item.get("topics") or []),
                        default_branch=item.get("default_branch") or "main",
                        is_fork=bool(item.get("fork")),
                    )
                )
                if len(candidates) >= limit:
                    return candidates

            await asyncio.sleep(0.6)

        return candidates

    async def count_stars_since(
        self,
        full_name: str,
        total_stars: int,
        cutoff: datetime,
    ) -> int:
        """
        Count stars with starred_at >= cutoff.

        Prefer GraphQL (newest stars first). REST high page numbers often 403.
        """
        if total_stars <= 0:
            return 0
        if "/" not in full_name:
            return -1
        if cutoff.tzinfo is None:
            cutoff = cutoff.replace(tzinfo=timezone.utc)

        gql = await self._count_stars_graphql(full_name, cutoff)
        if gql >= 0:
            return gql

        # Fallback REST only for smaller repos (low page numbers)
        if total_stars <= 800:
            return await self._count_stars_rest(full_name, total_stars, cutoff)
        logger.debug("Skipping REST fallback for large repo %s", full_name)
        return -1

    async def _count_stars_graphql(self, full_name: str, cutoff: datetime) -> int:
        """Newest-first stargazer timestamps via GraphQL."""
        owner, name = full_name.split("/", 1)
        query = """
        query($owner: String!, $name: String!, $cursor: String) {
          repository(owner: $owner, name: $name) {
            stargazers(first: 100, orderBy: {field: STARRED_AT, direction: DESC}, after: $cursor) {
              edges {
                starredAt
              }
              pageInfo {
                hasNextPage
                endCursor
              }
            }
          }
        }
        """
        count = 0
        cursor = None
        max_pages = 5  # up to 500 most recent stars

        for _ in range(max_pages):
            try:
                response = await self._client.post(
                    "/graphql",
                    json={
                        "query": query,
                        "variables": {
                            "owner": owner,
                            "name": name,
                            "cursor": cursor,
                        },
                    },
                )
            except httpx.HTTPError as exc:
                logger.warning("GraphQL stargazers failed for %s: %s", full_name, exc)
                return -1

            if response.status_code == 401:
                logger.error("GraphQL 401 — check GITHUB_TOKEN")
                return -1
            if response.status_code >= 400:
                logger.warning(
                    "GraphQL HTTP %s for %s: %s",
                    response.status_code,
                    full_name,
                    response.text[:200],
                )
                return -1

            payload = response.json()
            if payload.get("errors"):
                logger.warning(
                    "GraphQL errors for %s: %s",
                    full_name,
                    str(payload["errors"])[:300],
                )
                return -1

            repo = (payload.get("data") or {}).get("repository")
            if not repo:
                return -1
            gazers = repo.get("stargazers") or {}
            edges = gazers.get("edges") or []
            if not edges:
                return count

            stop = False
            for edge in edges:
                raw = edge.get("starredAt")
                if not raw:
                    continue
                try:
                    starred_at = datetime.fromisoformat(
                        str(raw).replace("Z", "+00:00")
                    )
                except ValueError:
                    continue
                if starred_at.tzinfo is None:
                    starred_at = starred_at.replace(tzinfo=timezone.utc)
                if starred_at >= cutoff:
                    count += 1
                else:
                    stop = True
                    break

            if stop:
                return count

            page_info = gazers.get("pageInfo") or {}
            if not page_info.get("hasNextPage"):
                return count
            cursor = page_info.get("endCursor")
            await asyncio.sleep(0.05)

        # Hit page cap while still inside window → at least `count` (maybe more)
        return count

    async def _count_stars_rest(
        self, full_name: str, total_stars: int, cutoff: datetime
    ) -> int:
        owner, repo = full_name.split("/", 1)
        per_page = 100
        last_page = max(1, (total_stars + per_page - 1) // per_page)
        last_page = min(last_page, 10)  # never deep-paginate (403 risk)

        count = 0
        pages_checked = 0

        for page in range(last_page, 0, -1):
            if pages_checked >= 8:
                break
            try:
                response = await self._client.get(
                    f"/repos/{owner}/{repo}/stargazers",
                    params={"per_page": per_page, "page": page},
                    headers={"Accept": "application/vnd.github.star+json"},
                )
                if response.status_code in (403, 404, 422):
                    return -1 if pages_checked == 0 else count
                response.raise_for_status()
                rows = response.json()
            except httpx.HTTPError as exc:
                logger.warning("REST stargazers failed %s p%s: %s", full_name, page, exc)
                return -1 if pages_checked == 0 else count

            if not isinstance(rows, list) or not rows:
                break
            pages_checked += 1

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
