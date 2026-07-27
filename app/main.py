from __future__ import annotations

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route
import uvicorn

from app import __version__

logger = logging.getLogger("rising_bot")

_state: dict[str, Any] = {
    "ready": False,
    "error": None,
    "ai": "grok-4.3",
}


async def health(_: Request) -> JSONResponse:
    return JSONResponse(
        {
            "status": "ok",
            "version": __version__,
            "ready": bool(_state.get("ready")),
            "ai": _state.get("ai"),
            "error": _state.get("error"),
            "port": os.environ.get("PORT"),
        }
    )


async def health_plain(_: Request) -> PlainTextResponse:
    return PlainTextResponse("ok")


async def scan_loop(scanner: Any, interval: int) -> None:
    await asyncio.sleep(2)
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
    from app.db import Database
    from app.github_client import GitHubClient
    from app.grok_client import GrokClient
    from app.scanner import RisingScanner
    from app.summarizer import Summarizer
    from app.telegram_client import TelegramClient

    db: Database | None = None
    github: GitHubClient | None = None
    telegram: TelegramClient | None = None
    grok: GrokClient | None = None
    loop_task: asyncio.Task[None] | None = None

    try:
        logger.info(
            "Bootstrap: AI=Grok model=%s base=%s min_stars=%s",
            settings.grok_model,
            settings.grok_base_url,
            settings.min_stars_24h,
        )
        _state["ai"] = settings.grok_model

        db = Database(settings.database_path)
        await db.connect()

        grok = GrokClient(
            api_key=settings.xai_api_key,
            model=settings.grok_model,
            base_url=settings.grok_base_url,
            timeout=settings.grok_timeout_seconds,
        )
        github = GitHubClient(settings.github_token)
        summarizer = Summarizer(grok)
        telegram = TelegramClient(
            settings.telegram_bot_token, settings.telegram_chat_id
        )

        try:
            await telegram.send_message(
                "✅ GitHub Rising bot aktif.\n"
                f"• Eşik: +{settings.min_stars_24h} star\n"
                f"• Tarama: her {settings.scan_interval_seconds // 60} dk\n"
                f"• AI: Grok ({settings.grok_model})\n"
                "Rising repo bulunca buraya yazar."
            )
            logger.info("Startup Telegram ping sent")
        except Exception:
            logger.exception(
                "Startup Telegram ping FAILED — check TELEGRAM_BOT_TOKEN / CHAT_ID"
            )

        scanner = RisingScanner(settings, db, github, summarizer, telegram)
        loop_task = asyncio.create_task(
            scan_loop(scanner, settings.scan_interval_seconds),
            name="scan_loop",
        )
        _state["ready"] = True
        _state["error"] = None
        logger.info("Bootstrap complete — scanner running (Ollama disabled)")
        await loop_task
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.exception("Bootstrap failed (HTTP stays up)")
        _state["ready"] = False
        _state["error"] = str(exc)
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
        if grok is not None:
            await grok.close()
        if db is not None:
            await db.close()


def build_app(settings: Any | None) -> Starlette:
    @asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncIterator[None]:
        task: asyncio.Task[None] | None = None
        if settings is not None:
            task = asyncio.create_task(bootstrap(settings), name="bootstrap")
        try:
            yield
        finally:
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    return Starlette(
        routes=[
            Route("/health", health),
            Route("/", health_plain),
        ],
        lifespan=lifespan,
    )


def _port() -> int:
    raw = os.environ.get("PORT", "8080").strip() or "8080"
    try:
        return int(raw)
    except ValueError:
        return 8080


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        stream=sys.stdout,
        force=True,
    )
    print(f"[main] starting version={__version__} PORT={_port()}", flush=True)

    settings = None
    try:
        from app.config import get_settings

        settings = get_settings()
        logging.getLogger().setLevel(
            getattr(logging, settings.log_level.upper(), logging.INFO)
        )
        port = settings.port
        print("[main] config ok (AI=Grok)", flush=True)
    except Exception as exc:
        print(f"[main] CONFIG ERROR (health-only mode): {exc}", flush=True)
        logger.exception("Config error — health-only mode")
        _state["error"] = f"config: {exc}"
        port = _port()

    app = build_app(settings)
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info",
        access_log=True,
    )
    server = uvicorn.Server(config)
    print(f"[main] binding 0.0.0.0:{port} /health", flush=True)
    server.run()
    print("[main] server stopped", flush=True)


if __name__ == "__main__":
    main()
