from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
import uvicorn

from app import __version__
from app.config import get_settings
from app.db import Database
from app.github_client import GitHubClient
from app.ollama_client import OllamaClient, normalize_ollama_base_url
from app.scanner import RisingScanner
from app.summarizer import Summarizer
from app.telegram_client import TelegramClient

logger = logging.getLogger("rising_bot")

# Shared runtime state (filled after HTTP is already up)
_state: dict[str, Any] = {
    "ready": False,
    "error": None,
    "ai": "ollama",
}


async def health(_: Request) -> JSONResponse:
    """Railway healthcheck — always 200 once uvicorn is listening."""
    return JSONResponse(
        {
            "status": "ok",
            "version": __version__,
            "ready": bool(_state.get("ready")),
            "ai": _state.get("ai"),
            "error": _state.get("error"),
        }
    )


async def scan_loop(scanner: RisingScanner, interval: int) -> None:
    await asyncio.sleep(5)
    while True:
        started = asyncio.get_running_loop().time()
        try:
            logger.info("Starting scan cycle…")
            sent = await scanner.run_once()
            logger.info("Cycle finished, messages sent: %s", sent)
        except Exception:
            logger.exception("Scan cycle failed")

        elapsed = asyncio.get_running_loop().time() - started
        sleep_for = max(5.0, interval - elapsed)
        logger.info(
            "Cycle took %.1fs; sleeping %.1fs (interval=%ss)",
            elapsed,
            sleep_for,
            interval,
        )
        await asyncio.sleep(sleep_for)


async def bootstrap(settings: Any) -> None:
    """Heavy init after /health is already serving."""
    db: Database | None = None
    github: GitHubClient | None = None
    telegram: TelegramClient | None = None
    ollama: OllamaClient | None = None
    loop_task: asyncio.Task[None] | None = None

    try:
        ollama_url = normalize_ollama_base_url(settings.ollama_base_url)
        logger.info(
            "Bootstrap: embedded Ollama model=%s base_url=%s min_stars=%s",
            settings.ollama_model,
            ollama_url,
            settings.min_stars_24h,
        )

        db = Database(settings.database_path)
        await db.connect()

        ollama = OllamaClient(
            base_url=ollama_url,
            model=settings.ollama_model,
            timeout=min(settings.ollama_timeout_seconds, 30.0),
        )
        # Short check only — never block deploy on model download
        if await ollama.healthcheck():
            logger.info("Ollama API reachable")
        else:
            logger.warning(
                "Ollama not ready yet (%s) — summaries may use fallback",
                ollama_url,
            )

        # Full timeout for real chat calls
        await ollama.close()
        ollama = OllamaClient(
            base_url=ollama_url,
            model=settings.ollama_model,
            timeout=settings.ollama_timeout_seconds,
        )

        github = GitHubClient(settings.github_token)
        summarizer = Summarizer(ollama)
        telegram = TelegramClient(
            settings.telegram_bot_token, settings.telegram_chat_id
        )
        scanner = RisingScanner(settings, db, github, summarizer, telegram)

        loop_task = asyncio.create_task(
            scan_loop(scanner, settings.scan_interval_seconds),
            name="scan_loop",
        )
        _state["ready"] = True
        _state["error"] = None
        logger.info("Bootstrap complete — scanner running")

        # Keep bootstrap task alive until cancelled
        await loop_task
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.exception("Bootstrap failed")
        _state["ready"] = False
        _state["error"] = str(exc)
        # Keep process alive so /health still returns 200 for Railway
        while True:
            await asyncio.sleep(3600)
    finally:
        if loop_task is not None:
            loop_task.cancel()
            try:
                await loop_task
            except asyncio.CancelledError:
                pass
        if github is not None:
            await github.close()
        if telegram is not None:
            await telegram.close()
        if ollama is not None:
            await ollama.close()
        if db is not None:
            await db.close()
        logger.info("Bootstrap shutdown complete")


def build_app(settings: Any) -> Starlette:
    @asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncIterator[None]:
        task = asyncio.create_task(bootstrap(settings), name="bootstrap")
        try:
            yield
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    return Starlette(
        routes=[Route("/health", health), Route("/", health)],
        lifespan=lifespan,
    )


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        stream=sys.stdout,
    )

    try:
        settings = get_settings()
    except Exception:
        logger.exception(
            "Config error — set TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, GITHUB_TOKEN"
        )
        raise

    logging.getLogger().setLevel(
        getattr(logging, settings.log_level.upper(), logging.INFO)
    )

    app = build_app(settings)
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=settings.port,
        log_level=settings.log_level.lower(),
        # Fail fast if port busy; bind ASAP for healthchecks
        timeout_keep_alive=5,
    )
    server = uvicorn.Server(config)
    logger.info(
        "Binding HTTP on 0.0.0.0:%s (/health) before full bootstrap",
        settings.port,
    )
    try:
        server.run()
    except KeyboardInterrupt:
        logger.info("Interrupted")


if __name__ == "__main__":
    main()
