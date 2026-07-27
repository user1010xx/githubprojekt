"""Ollama (açık kaynak) istemcisi — harici AI API key yok."""

from __future__ import annotations

import asyncio
import logging
from urllib.parse import urlparse, urlunparse

import httpx

logger = logging.getLogger(__name__)


class OllamaError(RuntimeError):
    pass


def normalize_ollama_base_url(base_url: str) -> str:
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
    """Ollama native API: /api/tags, /api/pull, /api/chat."""

    def __init__(self, base_url: str, model: str, timeout: float = 180.0) -> None:
        self.base_url = normalize_ollama_base_url(base_url)
        self.model = model.strip()
        self.timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)
        self._ready = False
        self._pull_started = False

    async def close(self) -> None:
        await self._client.aclose()

    async def healthcheck(self) -> bool:
        try:
            response = await self._client.get(
                f"{self.base_url}/api/tags",
                timeout=5.0,
            )
            return response.status_code == 200
        except httpx.HTTPError as exc:
            logger.debug("Ollama healthcheck failed: %s", exc)
            return False

    async def list_models(self) -> list[str]:
        try:
            response = await self._client.get(
                f"{self.base_url}/api/tags",
                timeout=10.0,
            )
            response.raise_for_status()
            models = response.json().get("models") or []
            names: list[str] = []
            for m in models:
                name = m.get("name") or m.get("model") or ""
                if name:
                    names.append(name)
            return names
        except Exception as exc:
            logger.debug("list_models failed: %s", exc)
            return []

    def _model_present(self, names: list[str]) -> bool:
        want = self.model
        want_base = want.split(":")[0]
        for n in names:
            if n == want or n.startswith(want + ":") or n.split(":")[0] == want_base:
                # prefer exact or matching tag
                if n == want or want in n or n.startswith(want_base):
                    return True
        return False

    async def pull_model(self) -> bool:
        """Pull model via API (blocking until done or fail)."""
        logger.info("Ollama pulling model %s ...", self.model)
        try:
            # stream=false waits until pull completes
            response = await self._client.post(
                f"{self.base_url}/api/pull",
                json={"name": self.model, "stream": False},
                timeout=600.0,
            )
            if response.status_code >= 400:
                logger.error("Ollama pull HTTP %s: %s", response.status_code, response.text[:400])
                return False
            data = response.json() if response.content else {}
            if isinstance(data, dict) and data.get("error"):
                logger.error("Ollama pull error: %s", data["error"])
                return False
            logger.info("Ollama model pull finished: %s", self.model)
            return True
        except httpx.HTTPError as exc:
            logger.error("Ollama pull failed: %s", exc)
            return False

    async def ensure_ready(self, wait_seconds: float = 300.0) -> bool:
        """
        Wait until Ollama API is up and model is available.
        Triggers pull once if model missing.
        """
        if self._ready:
            return True

        deadline = asyncio.get_running_loop().time() + wait_seconds
        pull_attempted = False

        while asyncio.get_running_loop().time() < deadline:
            if not await self.healthcheck():
                logger.info("Waiting for Ollama API at %s ...", self.base_url)
                await asyncio.sleep(3)
                continue

            names = await self.list_models()
            if self._model_present(names):
                self._ready = True
                logger.info("Ollama ready with model %s (have: %s)", self.model, names[:8])
                return True

            if not pull_attempted:
                pull_attempted = True
                await self.pull_model()
                continue

            logger.info("Model %s not listed yet; waiting... (%s)", self.model, names[:5])
            await asyncio.sleep(5)

        logger.error(
            "Ollama not ready after %.0fs (url=%s model=%s)",
            wait_seconds,
            self.base_url,
            self.model,
        )
        return False

    async def chat(self, system: str, user: str, *, retries: int = 2) -> str:
        # Ensure server+model before first real use
        if not self._ready:
            ok = await self.ensure_ready(wait_seconds=240)
            if not ok:
                raise OllamaError(
                    f"Ollama hazır değil ({self.base_url}, model={self.model}). "
                    "Railway RAM yetersiz olabilir veya model inmiyor. "
                    "OLLAMA_MODEL=llama3.2:1b ve /root/.ollama volume kontrol et."
                )

        payload = {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "options": {
                "temperature": 0.3,
                "num_predict": 800,
            },
        }
        url = f"{self.base_url}/api/chat"
        last_err: Exception | None = None

        for attempt in range(1, retries + 2):
            try:
                response = await self._client.post(url, json=payload, timeout=self.timeout)
            except httpx.HTTPError as exc:
                last_err = exc
                logger.warning("Ollama chat attempt %s failed: %s", attempt, exc)
                self._ready = False
                await asyncio.sleep(2 * attempt)
                await self.ensure_ready(wait_seconds=60)
                continue

            if response.status_code >= 400:
                text = response.text[:500]
                # model missing → pull and retry
                if response.status_code == 404 or "not found" in text.lower():
                    logger.warning("Model missing on chat; pulling %s", self.model)
                    self._ready = False
                    await self.pull_model()
                    continue
                raise OllamaError(f"Ollama hata {response.status_code}: {text}")

            try:
                data = response.json()
            except ValueError as exc:
                raise OllamaError(f"Ollama invalid JSON: {response.text[:300]}") from exc

            if isinstance(data, dict) and data.get("error"):
                err = str(data["error"])
                if "not found" in err.lower():
                    self._ready = False
                    await self.pull_model()
                    continue
                raise OllamaError(f"Ollama error: {err}")

            message = data.get("message") or {}
            content = (message.get("content") or "").strip()
            if content:
                return content
            last_err = OllamaError("Ollama boş yanıt döndü")
            await asyncio.sleep(1)

        raise OllamaError(f"Ollama chat başarısız: {last_err}")
