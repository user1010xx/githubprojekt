"""xAI Grok API client (OpenAI-compatible chat completions)."""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


class GrokError(RuntimeError):
    pass


class GrokClient:
    """
    POST {base_url}/chat/completions
    Default: https://api.x.ai/v1
    """

    def __init__(
        self,
        api_key: str,
        model: str = "grok-4.3",
        base_url: str = "https://api.x.ai/v1",
        timeout: float = 120.0,
    ) -> None:
        self.model = model.strip()
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {api_key.strip()}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def chat(self, system: str, user: str) -> str:
        payload = {
            "model": self.model,
            "temperature": 0.35,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        try:
            response = await self._client.post("/chat/completions", json=payload)
        except httpx.HTTPError as exc:
            raise GrokError(f"Grok API bağlantı hatası: {exc}") from exc

        if response.status_code >= 400:
            raise GrokError(
                f"Grok API HTTP {response.status_code}: {response.text[:500]}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise GrokError(f"Grok API geçersiz JSON: {response.text[:300]}") from exc

        if isinstance(data, dict) and data.get("error"):
            err = data["error"]
            msg = err.get("message", err) if isinstance(err, dict) else err
            raise GrokError(f"Grok API error: {msg}")

        choices = data.get("choices") or []
        if not choices:
            raise GrokError("Grok API boş choices döndü")

        message = choices[0].get("message") or {}
        content = (message.get("content") or "").strip()
        if not content:
            raise GrokError("Grok API boş content döndü")

        usage = data.get("usage") or {}
        if usage:
            logger.info(
                "Grok usage prompt=%s completion=%s total=%s",
                usage.get("prompt_tokens"),
                usage.get("completion_tokens"),
                usage.get("total_tokens"),
            )
        return content
