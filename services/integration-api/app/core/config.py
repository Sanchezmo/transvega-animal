"""
Configuración de la aplicación usando Pydantic Settings.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional


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
    API_WORKERS: int = 4
    API_CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:8002",
        "https://hermes.transvega-animal.es",
    ]
    
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
    
    @property
    def AUDIT_DB_URL(self) -> str:
        return f"postgresql://{self.AUDIT_DB_USER}:{self.AUDIT_DB_PASSWORD}@{self.AUDIT_DB_HOST}:{self.AUDIT_DB_PORT}/{self.AUDIT_DB_NAME}"
    
    # Redis
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str
    
    @property
    def REDIS_URL(self) -> str:
        return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/0"
    
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
    AGENT_API_KEY_SUPERVISOR: str
    AGENT_API_KEY_PRODUCTS: str
    AGENT_API_KEY_COMPLIANCE: str
    AGENT_API_KEY_PUBLISHING: str
    AGENT_API_KEY_SALES: str
    AGENT_API_KEY_INVOICING: str
    AGENT_API_KEY_PURCHASES: str
    AGENT_API_KEY_BANKING: str
    AGENT_API_KEY_ACCOUNTING: str
    AGENT_API_KEY_TAX: str
    AGENT_API_KEY_MARKETING: str
    AGENT_API_KEY_TECHNICAL: str
    
    @property
    def AGENT_API_KEYS(self) -> dict:
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
        }
    
    # Dolibarr
    DOLIBARR_API_URL: str
    DOLIBARR_API_KEY: str
    DOLIBARR_TIMEOUT: int = 30
    
    # Aprobaciones
    APPROVALS_SERVICE_URL: str = "http://approvals:8000"
    
    # Notificaciones
    NOTIFICATION_WEBHOOK_URL: Optional[str] = None
    NOTIFICATION_WEBHOOK_SECRET: Optional[str] = None
    
    # Google Workspace
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GOOGLE_WORKSPACE_DOMAIN: str = "transvega-animal.es"
    
    # Cloudflare
    CLOUDFLARE_API_TOKEN: Optional[str] = None
    CLOUDFLARE_ACCOUNT_ID: Optional[str] = None
    CLOUDFLARE_ZONE_ID: Optional[str] = None
    
    # Logs
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"
    
    # Métricas
    METRICS_ENABLED: bool = True
    METRICS_PORT: int = 9090
    
    # VeriFactu (fase posterior)
    VERIFACTU_PROVIDER: Optional[str] = None
    VERIFACTU_CERT_PATH: Optional[str] = None
    VERIFACTU_KEY_PATH: Optional[str] = None
    VERIFACTU_TEST_MODE: bool = True


@lru_cache
def get_settings() -> Settings:
    """Obtener configuración cacheada."""
    return Settings()