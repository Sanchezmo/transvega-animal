"""
Configuración de pytest y fixtures compartidas.
"""

import pytest
import pytest_asyncio


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


@pytest_asyncio.fixture(scope="function")
async def db_session():
    """Sesión de base de datos para tests."""
    # TODO: Implementar con base de datos de test separada


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
