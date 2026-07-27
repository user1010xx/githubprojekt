from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Zorunlu sırlar yalnızca iki token (+ Telegram grup id):

      1) TELEGRAM_BOT_TOKEN  (+ TELEGRAM_CHAT_ID)
      2) GITHUB_TOKEN

    AI = container içine gömülü Ollama (API key yok).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- 1) Telegram ---
    telegram_bot_token: str = Field(..., alias="TELEGRAM_BOT_TOKEN", min_length=10)
    telegram_chat_id: str = Field(..., alias="TELEGRAM_CHAT_ID", min_length=1)

    # --- 2) GitHub ---
    github_token: str = Field(..., alias="GITHUB_TOKEN", min_length=10)

    # --- Ollama ---
    ollama_base_url: str = Field("http://127.0.0.1:11434", alias="OLLAMA_BASE_URL")
    ollama_model: str = Field("llama3.2:1b", alias="OLLAMA_MODEL")
    ollama_timeout_seconds: float = Field(180.0, alias="OLLAMA_TIMEOUT_SECONDS")

    # --- Bot davranışı ---
    # Rising eşiği: pencere içindeki star artışı (varsayılan 5)
    min_stars_24h: int = Field(5, alias="MIN_STARS_24H", ge=1)
    max_candidates: int = Field(40, alias="MAX_CANDIDATES", ge=1, le=100)
    max_notifications_per_scan: int = Field(
        8, alias="MAX_NOTIFICATIONS_PER_SCAN", ge=1, le=50
    )
    # Bu seferlik: bugün sabahtan (TR 00:00) itibaren — bir kez çalışır, DB'ye işlenir
    morning_catchup_once: bool = Field(True, alias="MORNING_CATCHUP_ONCE")
    catchup_max_notifications: int = Field(
        25, alias="CATCHUP_MAX_NOTIFICATIONS", ge=1, le=50
    )
    catchup_timezone: str = Field("Europe/Istanbul", alias="CATCHUP_TIMEZONE")

    dedup_hours: int = Field(48, alias="DEDUP_HOURS", ge=1)
    scan_interval_seconds: int = Field(600, alias="SCAN_INTERVAL_SECONDS", ge=60)
    database_path: str = Field("./data/bot.db", alias="DATABASE_PATH")

    port: int = Field(8080, alias="PORT", ge=1, le=65535)
    log_level: str = Field("INFO", alias="LOG_LEVEL")

    @field_validator(
        "telegram_bot_token",
        "telegram_chat_id",
        "github_token",
        "ollama_base_url",
        "ollama_model",
        "catchup_timezone",
        mode="before",
    )
    @classmethod
    def _strip_str(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
