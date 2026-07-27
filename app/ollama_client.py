"""Ollama (açık kaynak) istemcisi — harici AI API key yok."""

from __future__ import annotations

import logging
from urllib.parse import urlparse, urlunparse

import httpx

logger = logging.getLogger(__name__)


class OllamaError(RuntimeError):
    pass


def normalize_ollama_base_url(base_url: str) -> str:
    """
    Accept common forms and return origin used with /api/chat.

    Examples:
      http://127.0.0.1:11434
      http://127.0.0.1:11434/
      http://127.0.0.1:11434/v1   (OpenAI-compat style — strip /v1)
    """
    raw = (base_url or "").strip().rstrip("/")
    if not raw:
        return "http://127.0.0.1:11434"
    if not raw.startswith("http://") and not raw.startswith("https://"):
        raw = "http://" + raw

    parsed = urlparse(raw)
    path = (parsed.path or "").rstrip("/")
    if path in ("/v1", "/api"):
        path = ""
    elif path.endswith("/v1"):
        path = path[: -len("/v1")]

    normalized = urlunparse(
        (parsed.scheme, parsed.netloc, path, "", "", "")
    ).rstrip("/")
    return normalized or "http://127.0.0.1:11434"


class OllamaClient:
    """
    Ollama native Chat API.

    POST {base_url}/api/chat
    https://github.com/ollama/ollama/blob/main/docs/api.md
    """

    def __init__(self, base_url: str, model: str, timeout: float = 120.0) -> None:
        self.base_url = normalize_ollama_base_url(base_url)
        self.model = model.strip()
        self._client = httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        await self._client.aclose()

    async def healthcheck(self) -> bool:
        try:
            response = await self._client.get(f"{self.base_url}/api/tags")
            return response.status_code == 200
        except httpx.HTTPError as exc:
            logger.warning("Ollama healthcheck failed: %s", exc)
            return False

    async def chat(self, system: str, user: str) -> str:
        payload = {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "options": {
                "temperature": 0.3,
            },
        }
        url = f"{self.base_url}/api/chat"
        try:
            response = await self._client.post(url, json=payload)
        except httpx.HTTPError as exc:
            raise OllamaError(
                f"Ollama'ya bağlanılamadı ({url}): {exc}. "
                "Ollama çalışıyor mu? `ollama serve` ve model: "
                f"`ollama pull {self.model}`"
            ) from exc

        if response.status_code >= 400:
            raise OllamaError(
                f"Ollama hata {response.status_code}: {response.text[:500]}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise OllamaError(f"Ollama invalid JSON: {response.text[:300]}") from exc

        # Some errors still return 200 with an error field
        if isinstance(data, dict) and data.get("error"):
            raise OllamaError(f"Ollama error: {data['error']}")

        message = data.get("message") or {}
        content = (message.get("content") or "").strip()
        if not content:
            raise OllamaError("Ollama boş yanıt döndü")
        return content
