"""
Pytest configuration for integration tests.
Sets up test environment BEFORE any test modules are imported.
"""

import os

# Force test environment BEFORE any other imports
os.environ["ENVIRONMENT"] = "test"
os.environ["DEBUG"] = "true"
os.environ["MOCK_DOLIBARR_ENABLED"] = "true"
os.environ["TEST_MODE"] = "true"

# Required settings for config validation
os.environ["AUDIT_DB_HOST"] = "127.0.0.1"
os.environ["AUDIT_DB_PORT"] = "55432"
os.environ["AUDIT_DB_NAME"] = "transvega_test"
os.environ["AUDIT_DB_USER"] = "transvega_test"
os.environ["AUDIT_DB_PASSWORD"] = "transvega_test"

os.environ["REDIS_HOST"] = "127.0.0.1"
os.environ["REDIS_PORT"] = "56379"
os.environ["REDIS_PASSWORD"] = ""

os.environ["DOLIBARR_API_URL"] = "http://localhost:8001"
os.environ["DOLIBARR_API_KEY"] = "test_dolibarr_key"
os.environ["DOLIBARR_TIMEOUT"] = "30"

os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-testing-only-32chars"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["JWT_EXPIRATION_MINUTES"] = "30"
os.environ["JWT_REFRESH_EXPIRATION_DAYS"] = "7"
os.environ["FERNET_KEY"] = "ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Rg="

# API Keys por agente
os.environ["AGENT_API_KEY_SUPERVISOR"] = "tvsk_test_supervisor_key_123"
os.environ["AGENT_API_KEY_PRODUCTS"] = "tvsk_test_products_key_123"
os.environ["AGENT_API_KEY_COMPLIANCE"] = "tvsk_test_compliance_key_123"
os.environ["AGENT_API_KEY_PUBLISHING"] = "tvsk_test_publishing_key_123"
os.environ["AGENT_API_KEY_SALES"] = "tvsk_test_sales_key_123"
os.environ["AGENT_API_KEY_INVOICING"] = "tvsk_test_invoicing_key_123"
os.environ["AGENT_API_KEY_PURCHASES"] = "tvsk_test_purchases_key_123"
os.environ["AGENT_API_KEY_BANKING"] = "tvsk_test_banking_key_123"
os.environ["AGENT_API_KEY_ACCOUNTING"] = "tvsk_test_accounting_key_123"
os.environ["AGENT_API_KEY_TAX"] = "tvsk_test_tax_key_123"
os.environ["AGENT_API_KEY_MARKETING"] = "tvsk_test_marketing_key_123"
os.environ["AGENT_API_KEY_TECHNICAL"] = "tvsk_test_technical_key_123"
os.environ["AGENT_API_KEY_DOG_INTAKE"] = "tvsk_test_dog_intake_key_123"
os.environ["AGENT_API_KEY_EXPEDIENTES"] = "tvsk_test_expedientes_key_123"
os.environ["AGENT_API_KEY_FACTURACION"] = "tvsk_test_facturacion_key_123"
os.environ["AGENT_API_KEY_LISTING"] = "tvsk_test_listing_key_123"

os.environ["APPROVALS_SERVICE_URL"] = "http://localhost:8002"

os.environ["NOTIFICATION_WEBHOOK_URL"] = ""
os.environ["NOTIFICATION_WEBHOOK_SECRET"] = ""

os.environ["TELEGRAM_WEBHOOK_SECRET"] = "test_telegram_webhook_secret"
os.environ["TELEGRAM_WEBHOOK_SECRET_REQUIRED"] = "false"
os.environ["TELEGRAM_BOT_TOKEN"] = "test_bot_token"
os.environ["TELEGRAM_UPDATE_IDEMPOTENCY_TTL_HOURS"] = "24"

os.environ["GOOGLE_CLIENT_ID"] = ""
os.environ["GOOGLE_CLIENT_SECRET"] = ""
os.environ["GOOGLE_WORKSPACE_DOMAIN"] = "transvega-animal.es"

os.environ["CLOUDFLARE_API_TOKEN"] = ""
os.environ["CLOUDFLARE_ACCOUNT_ID"] = ""
os.environ["CLOUDFLARE_ZONE_ID"] = ""

os.environ["LOG_LEVEL"] = "DEBUG"
os.environ["LOG_FORMAT"] = "json"

os.environ["METRICS_ENABLED"] = "false"
os.environ["METRICS_PORT"] = "9090"

os.environ["VERIFACTU_PROVIDER"] = ""
os.environ["VERIFACTU_CERT_PATH"] = ""
os.environ["VERIFACTU_KEY_PATH"] = ""
os.environ["VERIFACTU_TEST_MODE"] = "true"

os.environ["CELERY_BROKER_URL"] = "redis://127.0.0.1:56379/0"
os.environ["CELERY_RESULT_BACKEND"] = "redis://127.0.0.1:56379/2"
os.environ["CELERY_TASK_SERIALIZER"] = "json"
os.environ["CELERY_RESULT_SERIALIZER"] = "json"
os.environ["CELERY_ACCEPT_CONTENT"] = '["json"]'
os.environ["CELERY_TIMEZONE"] = "Europe/Madrid"
os.environ["CELERY_TASK_TRACK_STARTED"] = "true"
os.environ["CELERY_TASK_TIME_LIMIT"] = "3600"
os.environ["CELERY_WORKER_PREFETCH_MULTIPLIER"] = "4"
os.environ["CELERY_WORKER_CONCURRENCY"] = "4"
os.environ["CELERY_TASK_DEFAULT_QUEUE"] = "default"

os.environ["RATE_LIMIT_REQUESTS"] = "100"
os.environ["RATE_LIMIT_WINDOW_SECONDS"] = "60"
os.environ["IDEMPOTENCY_TTL_HOURS"] = "24"

os.environ["OLLAMA_ENDPOINT"] = "http://localhost:11434"
os.environ["OLLAMA_MODEL"] = "transvega-local"

os.environ["NVIDIA_API_KEY"] = ""
os.environ["NVIDIA_BASE_URL"] = ""

os.environ["INTERNAL_API_URL"] = "http://localhost:8000/api/v1"


import pytest
import pytest_asyncio


class MockRedis:
    """Mock Redis for testing."""

    def __init__(self, *args, **kwargs):
        # Accept and ignore connection parameters like real Redis
        self._data = {}
        self._ttl = {}

    async def incr(self, key: str) -> int:
        current = self._data.get(key, 0) + 1
        self._data[key] = current
        return current

    async def expire(self, key: str, seconds: int) -> bool:
        self._ttl[key] = seconds
        return True

    async def ttl(self, key: str) -> int:
        return self._ttl.get(key, -1)

    async def get(self, key: str) -> str | None:
        return self._data.get(key)

    async def setex(self, key: str, seconds: int, value: str) -> bool:
        self._data[key] = value
        self._ttl[key] = seconds
        return True

    async def close(self):
        pass

    async def ping(self):
        return True


class FakeAgent:
    """Fake agent for testing authentication."""

    def __init__(self, agent_id, agent_name, roles):
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.roles = roles

    def has_role(self, role):
        return role in self.roles

    def has_any_role(self, roles):
        return any(r in self.roles for r in roles)


# Mock Redis at module level for rate limiting
@pytest.fixture(autouse=True)
def mock_redis():
    """Mock Redis for testing."""

    async def mock_get_redis():
        mock = MockRedis()
        yield mock

    async def mock_get_redis_client():
        return MockRedis()

    # Patch get_redis where it's used (rate_limit imports it at module level)
    # Also patch Redis class in database module where it's instantiated
    # get_redis_client() returns a Redis instance directly (async function)
    with pytest.MonkeyPatch().context() as m:
        m.setattr("app.dependencies.rate_limit.get_redis", mock_get_redis)
        m.setattr("app.core.database.get_redis", mock_get_redis)
        m.setattr("app.core.database.get_redis_client", mock_get_redis_client)
        m.setattr("app.core.database.Redis", MockRedis)
        yield


@pytest.fixture(scope="session")
def settings():
    """Configuración de test."""
    from app.core.config import get_settings

    get_settings.cache_clear()
    value = get_settings()
    yield value
    get_settings.cache_clear()


@pytest_asyncio.fixture(autouse=True)
async def init_database():
    """Inicializar base de datos para tests de integración."""
    from app.core.database import close_db, init_db

    await init_db()
    yield
    await close_db()


@pytest_asyncio.fixture(scope="session")
async def test_app():
    """App FastAPI para testing."""
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# Fixtures de datos de prueba
@pytest.fixture
def sample_tercero():
    """Datos de tercero de prueba."""
    return {
        "name": "Test Cliente",
        "email": "test@cliente.es",
        "phone": "+34 600 123 456",
        "client": 1,
        "supplier": 0,
        "status": 1,
        "vat_number": "ESB12345678",
    }


@pytest.fixture
def sample_expediente():
    """Datos de expediente animal de prueba."""
    return {
        "name": "Luna",
        "species": "perro",
        "breed": "Golden Retriever",
        "sex": "H",
        "birth_date": "2024-01-15",
        "color": "Dorado",
        "weight_kg": 12.5,
        "microchip": "941000012345678",
        "purchase_price": 800.00,
        "sale_price": 1500.00,
        "commercial_status": "draft",
    }


@pytest.fixture
def sample_product():
    """Datos de producto de prueba."""
    return {
        "ref": "DOG-GOLDEN-001",
        "label": "Cachorro Golden Retriever LOE",
        "price": 1500.00,
        "tva_tx": 21.0,
        "type": 0,
    }


# Mock de agente autenticado
@pytest.fixture
def mock_agent():
    """Agente mock para tests."""
    return {
        "agent_id": "agent_products",
        "agent_name": "products",
        "roles": ["products", "read"],
    }


@pytest.fixture
def api_keys():
    """API keys for testing from settings."""
    from app.core.config import get_settings

    s = get_settings()
    return {
        "supervisor": s.AGENT_API_KEY_SUPERVISOR,
        "products": s.AGENT_API_KEY_PRODUCTS,
        "compliance": s.AGENT_API_KEY_COMPLIANCE,
        "publishing": s.AGENT_API_KEY_PUBLISHING,
        "sales": s.AGENT_API_KEY_SALES,
        "invoicing": s.AGENT_API_KEY_INVOICING,
        "purchases": s.AGENT_API_KEY_PURCHASES,
        "banking": s.AGENT_API_KEY_BANKING,
        "accounting": s.AGENT_API_KEY_ACCOUNTING,
        "tax": s.AGENT_API_KEY_TAX,
        "marketing": s.AGENT_API_KEY_MARKETING,
        "technical": s.AGENT_API_KEY_TECHNICAL,
        "dog_intake": s.AGENT_API_KEY_DOG_INTAKE,
        "expedientes": s.AGENT_API_KEY_EXPEDIENTES,
        "facturacion": s.AGENT_API_KEY_FACTURACION,
        "listing": s.AGENT_API_KEY_LISTING,
    }


# Configuración de pytest
def pytest_configure(config):
    """Configuración global de pytest."""
    config.addinivalue_line("markers", "unit: Tests unitarios")
    config.addinivalue_line("markers", "integration: Tests de integración")
    config.addinivalue_line("markers", "security: Tests de seguridad")
    config.addinivalue_line("markers", "e2e: Tests end-to-end")
