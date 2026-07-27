from __future__ import annotations

import asyncio
import logging
import sys

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


async def health(_: Request) -> JSONResponse:
    return JSONResponse(
        {
            "status": "ok",
            "version": __version__,
            "ai": "ollama",
        }
    )


def create_app() -> Starlette:
    return Starlette(routes=[Route("/health", health), Route("/", health)])


async def scan_loop(scanner: RisingScanner, interval: int) -> None:
    await asyncio.sleep(3)
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


async def run() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        stream=sys.stdout,
    )

    ollama_url = normalize_ollama_base_url(settings.ollama_base_url)
    logger.info(
        "AI=embedded Ollama model=%s base_url=%s | min_stars_24h=%s interval=%ss",
        settings.ollama_model,
        ollama_url,
        settings.min_stars_24h,
        settings.scan_interval_seconds,
    )

    db = Database(settings.database_path)
    await db.connect()

    ollama = OllamaClient(
        base_url=ollama_url,
        model=settings.ollama_model,
        timeout=settings.ollama_timeout_seconds,
    )
    if await ollama.healthcheck():
        logger.info("Ollama erişilebilir")
    else:
        logger.warning(
            "Ollama şu an erişilemiyor (%s). "
            "Özetler fallback'e düşebilir. `ollama serve` ve `ollama pull %s`",
            ollama_url,
            settings.ollama_model,
        )

    github = GitHubClient(settings.github_token)
    summarizer = Summarizer(ollama)
    telegram = TelegramClient(settings.telegram_bot_token, settings.telegram_chat_id)
    scanner = RisingScanner(settings, db, github, summarizer, telegram)

    app = create_app()
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=settings.port,
        log_level=settings.log_level.lower(),
    )
    server = uvicorn.Server(config)

    loop_task = asyncio.create_task(
        scan_loop(scanner, settings.scan_interval_seconds),
        name="scan_loop",
    )

    try:
        await server.serve()
    finally:
        loop_task.cancel()
        try:
            await loop_task
        except asyncio.CancelledError:
            pass
        await github.close()
        await telegram.close()
        await ollama.close()
        await db.close()
        logger.info("Shutdown complete")


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("Interrupted")


if __name__ == "__main__":
    main()
