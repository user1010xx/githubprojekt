from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Zorunlu:
      1) TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID
      2) GITHUB_TOKEN
      3) XAI_API_KEY  (Grok API)

    AI = xAI Grok 4.3 (Ollama devre dışı).
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

    # --- 3) xAI Grok ---
    xai_api_key: str = Field(..., alias="XAI_API_KEY", min_length=10)
    grok_model: str = Field("grok-4.3", alias="GROK_MODEL")
    grok_base_url: str = Field("https://api.x.ai/v1", alias="GROK_BASE_URL")
    grok_timeout_seconds: float = Field(120.0, alias="GROK_TIMEOUT_SECONDS")

    # --- Bot davranışı ---
    min_stars_24h: int = Field(5, alias="MIN_STARS_24H", ge=1)
    max_candidates: int = Field(40, alias="MAX_CANDIDATES", ge=1, le=100)
    max_notifications_per_scan: int = Field(
        8, alias="MAX_NOTIFICATIONS_PER_SCAN", ge=1, le=50
    )
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
        "xai_api_key",
        "grok_model",
        "grok_base_url",
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
