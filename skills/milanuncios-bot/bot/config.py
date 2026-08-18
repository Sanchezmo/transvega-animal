# Milanuncios Bot - Config
"""
Configuration management using Pydantic Settings.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Browser settings
    HEADLESS: bool = Field(default=True, description="Run browser in headless mode")
    STORAGE_STATE_PATH: str = Field(
        default="/app/storage/state.json", description="Path to persist browser storage state"
    )

    # Milanuncios credentials
    MILANUNCIOS_EMAIL: str = Field(..., description="Milanuncios account email")
    MILANUNCIOS_PASSWORD: str = Field(..., description="Milanuncios account password")

    # Renewal settings
    RENEWAL_DELAY_MIN: int = Field(default=1800, description="Min delay between renewals (seconds)")
    RENEWAL_DELAY_MAX: int = Field(default=3600, description="Max delay between renewals (seconds)")
    MAX_ADS_PER_RUN: int = Field(default=50, description="Maximum ads to renew per run")

    # Selectors (may need updates if site changes)
    LOGIN_URL: str = Field(default="https://www.milanuncios.com/mis-anuncios/")
    ADS_LIST_SELECTOR: str = Field(default="article.ad-item")
    RENEW_BUTTON_SELECTOR: str = Field(default="button[data-action='renew']")
    CONFIRM_RENEW_SELECTOR: str = Field(default="button:has-text('Renovar')")

    # Logging
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")

    # Metrics
    METRICS_PORT: int = Field(default=9090, description="Prometheus metrics port")

    # Notifications (optional)
    TELEGRAM_BOT_TOKEN: str = Field(default="", description="Telegram bot token for alerts")
    TELEGRAM_CHAT_ID: str = Field(default="", description="Telegram chat ID for alerts")


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Global settings instance
settings = get_settings()
