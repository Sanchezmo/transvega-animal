from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.main import app

"""
Fixtures compartidas para tests de integración.
"""


@pytest.fixture(scope="session", autouse=True)
def configure_test_settings():
    """Configurar settings de test usando .env.test (cargado antes por load_env.py)."""
    get_settings.cache_clear()
    settings = get_settings()
    return settings


@pytest.fixture(scope="session")
def test_settings(configure_test_settings):
    """Proporcionar settings de test."""
    return configure_test_settings


@pytest.fixture(scope="session")
def api_keys(test_settings):
    """Proporcionar API keys para testing."""
    return test_settings.get_agent_api_keys()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def init_database():
    """Inicializar base de datos para tests de integración."""
    # Importar aquí para que el engine se cree en el event loop correcto
    from app.core.database import close_db, init_db

    await init_db()
    yield
    await close_db()


@pytest_asyncio.fixture(scope="session")
async def async_client():
    """Cliente HTTP asíncrono para testing con la app real."""

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


class MockRedis:
    """Mock Redis para testing."""

    def __init__(self, *args, **kwargs):
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

    async def set(self, key: str, value: str, nx: bool = False, ex: int | None = None) -> bool:
        if nx and key in self._data:
            return False
        self._data[key] = value
        if ex is not None:
            self._ttl[key] = ex
        return True

    async def close(self):
        pass

    async def ping(self):
        return True


class FakeAgent:
    """Fake agent para testing de autenticación."""

    def __init__(self, agent_id: str, agent_name: str, roles: list[str]):
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.roles = roles

    def has_role(self, role: str) -> bool:
        return role in self.roles

    def has_any_role(self, roles: list[str]) -> bool:
        return any(r in self.roles for r in roles)

    def get(self, key, default=None):
        return getattr(self, key, default)


@pytest.fixture(autouse=True)
def mock_redis():
    """Mock Redis a nivel de módulo para todos los tests."""

    async def mock_get_redis():
        mock = MockRedis()
        yield mock

    # Patch get_redis where it's used (rate_limit imports it at module level)
    # Also patch Redis class in database module where it's instantiated
    with patch("app.dependencies.rate_limit.get_redis", mock_get_redis):
        with patch("app.core.database.get_redis", mock_get_redis):
            with patch("app.core.database.get_redis_client", mock_get_redis):
                with patch("app.core.database.Redis", MockRedis):
                    yield


# Configuración de pytest
@pytest.fixture
def mock_breed():
    """Proporcionar una raza mock para tests."""
    return {
        "id": 1,
        "name": "Golden Retriever",
        "species": "dog",
        "average_height_cm": None,
        "average_weight_kg": None,
        "description": None,
        "created_at": "2026-08-18T00:00:00",
        "updated_at": "2026-08-18T00:00:00",
    }


def pytest_configure(config):
    """Configuración global de pytest."""
    config.addinivalue_line("markers", "unit: Tests unitarios")
    config.addinivalue_line("markers", "integration: Tests de integración")
    config.addinivalue_line("markers", "security: Tests de seguridad")
    config.addinivalue_line("markers", "e2e: Tests end-to-end")
