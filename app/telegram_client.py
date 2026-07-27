from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class TelegramError(RuntimeError):
    pass


class TelegramClient:
    def __init__(self, bot_token: str, chat_id: str) -> None:
        self.chat_id: str | int
        # Telegram accepts int for groups; coerce when numeric
        stripped = chat_id.strip()
        try:
            self.chat_id = int(stripped)
        except ValueError:
            self.chat_id = stripped

        self._client = httpx.AsyncClient(
            base_url=f"https://api.telegram.org/bot{bot_token.strip()}",
            timeout=30.0,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def send_message(self, text: str) -> dict[str, Any]:
        # Telegram hard limit 4096 chars
        if len(text) > 4000:
            text = text[:3990] + "\n…"

        response = await self._client.post(
            "/sendMessage",
            json={
                "chat_id": self.chat_id,
                "text": text,
                "disable_web_page_preview": False,
            },
        )

        # HTTP layer
        if response.status_code >= 400:
            logger.error("Telegram HTTP %s: %s", response.status_code, response.text)
            response.raise_for_status()

        # Telegram often returns HTTP 200 with ok=false
        try:
            data = response.json()
        except ValueError as exc:
            raise TelegramError(f"Telegram invalid JSON: {response.text[:300]}") from exc

        if not data.get("ok"):
            desc = data.get("description") or data
            raise TelegramError(f"Telegram API error: {desc}")

        logger.info("Message sent to chat %s", self.chat_id)
        return data
