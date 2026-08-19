"""
Pytest configuration for integration tests.
Sets up test environment BEFORE any test modules are imported.
"""

import os

# Force test environment BEFORE any other imports
os.environ["ENVIRONMENT"] = "test"
os.environ["MOCK_DOLIBARR_ENABLED"] = "true"
os.environ["TEST_MODE"] = "true"

# Clear any cached settings
import sys
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
