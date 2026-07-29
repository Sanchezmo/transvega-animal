"""Configuration for approval service."""
import os
from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    APPROVALS_DB_URL: str = os.getenv("APPROVALS_DB_URL", "postgresql+asyncpg://audit:audit@audit-db:5432/audit")
    APPROVALS_REDIS_URL: str = os.getenv("APPROVALS_REDIS_URL", "redis://:dev_redis_password_123456789012345678901234@redis:6379/1")
    NOTIFICATION_WEBHOOK_URL: str = os.getenv("NOTIFICATION_WEBHOOK_URL", "")
    NOTIFICATION_WEBHOOK_SECRET: str = os.getenv("NOTIFICATION_WEBHOOK_SECRET", "")
    ALLOWED_ORIGINS: List[str] = ["*"]
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()