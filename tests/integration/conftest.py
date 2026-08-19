"""
Pytest configuration for integration tests.
Sets up test environment BEFORE any test modules are imported.
"""

import os
import sys

# Force test environment BEFORE any other imports
os.environ["ENVIRONMENT"] = "test"
os.environ["MOCK_DOLIBARR_ENABLED"] = "true"
os.environ["TEST_MODE"] = "true"

# Clear any cached settings
if "app.core.config" in sys.modules:
    import app.core.config as config_module
    from app.core.config import get_settings

    get_settings.cache_clear()
    config_module.settings = get_settings()

# Now safe to import test dependencies
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.core.database import init_db
from app.main import app


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

    # Patch get_redis where it's used (rate_limit imports it at module level)
    # Also patch Redis class in database module where it's instantiated
    with pytest.MonkeyPatch().context() as m:
        m.setattr("app.dependencies.rate_limit.get_redis", mock_get_redis)
        m.setattr("app.core.database.get_redis", mock_get_redis)
        m.setattr("app.core.database.get_redis_client", mock_get_redis)
        m.setattr("app.core.database.Redis", MockRedis)
        yield


@pytest.fixture(scope="session")
def settings():
    """Configuración de test."""
    return get_settings()


@pytest.fixture(scope="session")
def event_loop():
    """Event loop para tests async."""
    import asyncio

    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def init_database():
    """Inicializar base de datos para tests de integración."""
    await init_db()


@pytest_asyncio.fixture(scope="session")
async def test_app():
    """App FastAPI para testing."""
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


# Configuración de pytest
def pytest_configure(config):
    """Configuración global de pytest."""
    config.addinivalue_line("markers", "unit: Tests unitarios")
    config.addinivalue_line("markers", "integration: Tests de integración")
    config.addinivalue_line("markers", "security: Tests de seguridad")
    config.addinivalue_line("markers", "e2e: Tests end-to-end")
