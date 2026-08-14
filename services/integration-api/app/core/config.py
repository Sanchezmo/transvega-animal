"""
Configuración de la aplicación usando Pydantic Settings.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración centralizada de la aplicación."""

    model_config = SettingsConfigDict(
        env_file=".env.local",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Aplicación
    APP_NAME: str = "Transvega Animal API"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # API
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_WORKERS: int = 1
    API_CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:8002",
        "https://hermes.transvega-animal.es",
    ]

    # Internal API URL for service-to-service communication
    INTERNAL_API_URL: str = "http://localhost:8000"

    # Rate limiting
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    # Idempotencia
    IDEMPOTENCY_TTL_HOURS: int = 24

    # Base de datos auditoría
    AUDIT_DB_HOST: str = "audit-db"
    AUDIT_DB_PORT: int = 5432
    AUDIT_DB_NAME: str = "audit"
    AUDIT_DB_USER: str = "audit"
    AUDIT_DB_PASSWORD: str

    # Redis
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str

    # Dolibarr
    DOLIBARR_API_URL: str
    DOLIBARR_API_KEY: str
    DOLIBARR_TIMEOUT: int = 30

    # JWT
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_MINUTES: int = 30
    JWT_REFRESH_EXPIRATION_DAYS: int = 7

    # Cifrado
    FERNET_KEY: str

    # API Keys por agente
    AGENT_API_KEY_SUPERVISOR: str = "tvsk_dev_supervisor_abcdef123456"
    AGENT_API_KEY_PRODUCTS: str = "tvsk_dev_products_abcdef123456"
    AGENT_API_KEY_COMPLIANCE: str = "tvsk_dev_compliance_abcdef123456"
    AGENT_API_KEY_PUBLISHING: str = "tvsk_dev_publishing_abcdef123456"
    AGENT_API_KEY_SALES: str = "tvsk_dev_sales_abcdef123456"
    AGENT_API_KEY_INVOICING: str = "tvsk_dev_invoicing_abcdef123456"
    AGENT_API_KEY_PURCHASES: str = "tvsk_dev_purchases_abcdef123456"
    AGENT_API_KEY_BANKING: str = "tvsk_dev_banking_abcdef123456"
    AGENT_API_KEY_ACCOUNTING: str = "tvsk_dev_accounting_abcdef123456"
    AGENT_API_KEY_TAX: str = "tvsk_dev_tax_abcdef123456"
    AGENT_API_KEY_MARKETING: str = "tvsk_dev_marketing_abcdef123456"
    AGENT_API_KEY_TECHNICAL: str = "tvsk_dev_technical_abcdef123456"
    AGENT_API_KEY_DOG_INTAKE: str = "tvsk_dev_dog_intake_abcdef123456"
    AGENT_API_KEY_EXPEDIENTES: str = "tvsk_dev_expedientes_abcdef123456"
    AGENT_API_KEY_FACTURACION: str = "tvsk_dev_facturacion_abcdef123456"

    # Aprobaciones
    APPROVALS_SERVICE_URL: str = "http://approvals:8000"

    # Notificaciones
    NOTIFICATION_WEBHOOK_URL: str | None = None
    NOTIFICATION_WEBHOOK_SECRET: str | None = None

    # Telegram
    TELEGRAM_WEBHOOK_SECRET: str | None = None
    TELEGRAM_WEBHOOK_SECRET_REQUIRED: bool = True

    # Google Workspace
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    GOOGLE_WORKSPACE_DOMAIN: str = "transvega-animal.es"

    # Cloudflare
    CLOUDFLARE_API_TOKEN: str | None = None
    CLOUDFLARE_ACCOUNT_ID: str | None = None
    CLOUDFLARE_ZONE_ID: str | None = None

    # Logs
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"

    # Métricas
    METRICS_ENABLED: bool = True
    METRICS_PORT: int = 9090

    # VeriFactu
    VERIFACTU_PROVIDER: str | None = None
    VERIFACTU_CERT_PATH: str | None = None
    VERIFACTU_KEY_PATH: str | None = None
    VERIFACTU_TEST_MODE: bool = True

    # Celery
    CELERY_BROKER_URL: str = "redis://redis:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/2"
    CELERY_TASK_SERIALIZER: str = "json"
    CELERY_RESULT_SERIALIZER: str = "json"
    CELERY_ACCEPT_CONTENT: list[str] = ["json"]
    CELERY_TIMEZONE: str = "Europe/Madrid"
    CELERY_TASK_TRACK_STARTED: bool = True
    CELERY_TASK_TIME_LIMIT: int = 3600
    CELERY_WORKER_PREFETCH_MULTIPLIER: int = 4
    CELERY_WORKER_CONCURRENCY: int = 4
    CELERY_TASK_DEFAULT_QUEUE: str = "default"

    def get_agent_api_keys(self) -> dict[str, str]:
        """Obtener diccionario de API keys por agente."""
        return {
            "supervisor": self.AGENT_API_KEY_SUPERVISOR,
            "products": self.AGENT_API_KEY_PRODUCTS,
            "compliance": self.AGENT_API_KEY_COMPLIANCE,
            "publishing": self.AGENT_API_KEY_PUBLISHING,
            "sales": self.AGENT_API_KEY_SALES,
            "invoicing": self.AGENT_API_KEY_INVOICING,
            "purchases": self.AGENT_API_KEY_PURCHASES,
            "banking": self.AGENT_API_KEY_BANKING,
            "accounting": self.AGENT_API_KEY_ACCOUNTING,
            "tax": self.AGENT_API_KEY_TAX,
            "marketing": self.AGENT_API_KEY_MARKETING,
            "technical": self.AGENT_API_KEY_TECHNICAL,
            "dog_intake": self.AGENT_API_KEY_DOG_INTAKE,
            "expedientes": self.AGENT_API_KEY_EXPEDIENTES,
            "facturacion": self.AGENT_API_KEY_FACTURACION,
        }

    @property
    def AGENT_API_KEYS(self) -> dict[str, str]:
        """Property para compatibilidad con código que accede a settings.AGENT_API_KEYS."""
        return self.get_agent_api_keys()


# URLs computadas como funciones externas (evitan recursión en __repr__ de Pydantic)
# Sin type hints para evitar recursión
def get_audit_db_url(settings):
    return f"postgresql://{settings.AUDIT_DB_USER}:{settings.AUDIT_DB_PASSWORD}@{settings.AUDIT_DB_HOST}:{settings.AUDIT_DB_PORT}/{settings.AUDIT_DB_NAME}"


def get_redis_url(settings):
    return f"redis://:{settings.REDIS_PASSWORD}@{settings.REDIS_HOST}:{settings.REDIS_PORT}/0"


@lru_cache
def get_settings() -> Settings:
    """Obtener configuración cacheada."""
    return Settings()


# Exportar instancia para compatibilidad
settings = get_settings()
