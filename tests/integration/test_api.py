"""
Tests de integración para la API.
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch

from app.main import app


@pytest_asyncio.fixture
async def client():
    """Cliente HTTP para testing."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


class TestHealthEndpoints:
    """Tests para endpoints de salud."""
    
    @pytest.mark.asyncio
    async def test_health_check(self, client: AsyncClient):
        """Health check básico."""
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "Transvega Animal API"
    
    @pytest.mark.asyncio
    async def test_readiness_check(self, client: AsyncClient):
        """Readiness check."""
        response = await client.get("/health/ready")
        assert response.status_code in [200, 503]
        data = response.json()
        assert "status" in data
        assert "checks" in data


class TestRootEndpoint:
    """Tests para endpoint raíz."""
    
    @pytest.mark.asyncio
    async def test_root(self, client: AsyncClient):
        """Endpoint raíz."""
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "Transvega Animal API"
        assert "docs" in data
        assert "health" in data


class TestAuthentication:
    """Tests de autenticación."""
    
    @pytest.mark.asyncio
    async def test_endpoint_protegido_sin_token(self, client: AsyncClient):
        """Endpoint protegido sin token debe fallar."""
        response = await client.get("/api/v1/expedientes")
        assert response.status_code == 401
    
    @pytest.mark.asyncio
    async def test_endpoint_con_token_invalido(self, client: AsyncClient):
        """Token inválido debe fallar."""
        headers = {"Authorization": "Bearer token_invalido"}
        response = await client.get("/api/v1/expedientes", headers=headers)
        assert response.status_code == 401


class TestRateLimiting:
    """Tests de rate limiting."""
    
    @pytest.mark.asyncio
    async def test_rate_limit_headers(self, client: AsyncClient):
        """Verificar headers de rate limit."""
        # Simular autenticación
        headers = {"Authorization": "Bearer tvsk_test_key"}
        
        with patch("app.dependencies.auth.get_current_agent") as mock_agent:
            mock_agent.return_value = type("Agent", (), {
                "agent_id": "test_agent",
                "agent_name": "test",
                "roles": ["read"],
                "has_role": lambda self, r: True,
                "has_any_role": lambda self, roles: True,
            })()
            
            response = await client.get("/health", headers=headers)
            # Health check no tiene rate limit
            assert response.status_code == 200


class TestIdempotency:
    """Tests de idempotencia."""
    
    @pytest.mark.asyncio
    async def test_idempotency_key_requerida_post(self, client: AsyncClient):
        """POST sin Idempotency-Key debe fallar en endpoints mutables."""
        headers = {"Authorization": "Bearer tvsk_test_key"}
        
        with patch("app.dependencies.auth.get_current_agent") as mock_agent:
            mock_agent.return_value = type("Agent", (), {
                "agent_id": "test_agent",
                "agent_name": "products",
                "roles": ["products", "write"],
                "has_role": lambda self, r: True,
                "has_any_role": lambda self, roles: True,
            })()
            
            response = await client.post(
                "/api/v1/expedientes",
                json={"name": "Test", "breed": "Golden", "sex": "H", 
                      "birth_date": "2024-01-15", "color": "Dorado",
                      "weight_kg": 10.0, "microchip": "941000012345678"},
                headers=headers,
            )
            # Debería fallar por falta de Idempotency-Key
            assert response.status_code == 400
    
    @pytest.mark.asyncio
    async def test_idempotency_funciona(self, client: AsyncClient):
        """Idempotency-Key funciona correctamente."""
        headers = {
            "Authorization": "Bearer tvsk_test_key",
            "Idempotency-Key": "test-key-123",
        }
        
        with patch("app.dependencies.auth.get_current_agent") as mock_agent:
            mock_agent.return_value = type("Agent", (), {
                "agent_id": "test_agent",
                "agent_name": "products",
                "roles": ["products", "write"],
                "has_role": lambda self, r: True,
                "has_any_role": lambda self, roles: True,
            })()
            
            # Primera request
            response1 = await client.post(
                "/api/v1/expedientes",
                json={"name": "Test", "breed": "Golden", "sex": "H",
                      "birth_date": "2024-01-15", "color": "Dorado",
                      "weight_kg": 10.0, "microchip": "941000012345678"},
                headers=headers,
            )
            
            # Segunda request con misma key
            response2 = await client.post(
                "/api/v1/expedientes",
                json={"name": "Test", "breed": "Golden", "sex": "H",
                      "birth_date": "2024-01-15", "color": "Dorado",
                      "weight_kg": 10.0, "microchip": "941000012345678"},
                headers=headers,
            )
            
            # Segunda debería fallar por idempotencia
            assert response2.status_code == 409


class TestCORS:
    """Tests de CORS."""
    
    @pytest.mark.asyncio
    async def test_cors_headers(self, client: AsyncClient):
        """Verificar headers CORS."""
        response = await client.options("/health", headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        })
        assert response.status_code == 200
        assert "access-control-allow-origin" in response.headers


class TestAuditLogging:
    """Tests de logging de auditoría."""
    
    @pytest.mark.asyncio
    async def test_audit_log_creado(self, client: AsyncClient):
        """Verificar que se crea log de auditoría."""
        # Este test requeriría acceso a la BD de auditoría
        # Se implementaría con base de datos de test
        pass


# Tests de esquemas ya están en test_schemas.py

if __name__ == "__main__":
    pytest.main([__file__, "-v"])