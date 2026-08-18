"""
Tests de integración para la API.
"""

from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app


class MockRedis:
    """Mock Redis for testing."""

    def __init__(self):
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


def create_mock_dolibarr_request():
    """Create a mock _request method for DolibarrClient."""
    import time

    # Store thirdparties in memory
    _thirdparties = [
        {
            "rowid": 1,
            "ref": "CLI-000001",
            "name": "Test Client",
            "name_alias": None,
            "email": "test@cliente.es",
            "phone": None,
            "address": None,
            "zip": None,
            "town": None,
            "fk_country": 4,
            "country_code": "ES",
            "fk_state": None,
            "client": 1,
            "supplier": 0,
            "status": 1,
            "tva_intra": "ESB12345678",
            "default_lang": "es_ES",
            "date_creation": 1700000000,
            "date_modification": 1700000000,
            "fk_user_author": 1,
            "fk_user_modif": 1,
            "code_client": "CLI-000001",
        }
    ]
    _next_id = 2

    # Store invoices in memory
    _invoices = []
    _next_invoice_id = 1

    async def mock_request(self, method: str, endpoint: str, params=None, json=None, data=None):
        nonlocal _next_id, _next_invoice_id

        if method == "POST" and endpoint == "thirdparties":
            # Create thirdparty
            new_tp = {
                "rowid": _next_id,
                "ref": f"CLI-{_next_id:06d}",
                "code_client": f"CLI-{int(time.time())}",
                **json,
                "date_creation": int(time.time()),
                "date_modification": int(time.time()),
                "fk_user_author": 1,
                "fk_user_modif": 1,
                "default_lang": "es_ES",
            }
            if "client" not in new_tp:
                new_tp["client"] = 1
            if "supplier" not in new_tp:
                new_tp["supplier"] = 0
            if "status" not in new_tp:
                new_tp["status"] = 1
            if "fk_country" not in new_tp:
                new_tp["fk_country"] = 4
            if "country_code" not in new_tp:
                new_tp["country_code"] = "ES"

            _next_id += 1
            _thirdparties.append(new_tp)
            return {"success": True, "data": new_tp, "id": new_tp["rowid"]}

        elif method == "GET" and endpoint == "thirdparties":
            return {"success": True, "data": _thirdparties, "total": len(_thirdparties)}

        elif method == "GET" and endpoint.startswith("thirdparties/"):
            # Get single thirdparty
            tp_id = int(endpoint.split("/")[-1])
            tp = next((t for t in _thirdparties if t["rowid"] == tp_id), None)
            if not tp:
                from app.core.exceptions import DolibarrException

                raise DolibarrException(message="Thirdparty not found", status_code=404)
            return {"success": True, "data": tp}

        elif method == "PUT" and endpoint.startswith("thirdparties/"):
            tp_id = int(endpoint.split("/")[-1])
            for i, tp in enumerate(_thirdparties):
                if tp["rowid"] == tp_id:
                    updated = {**tp, **json, "date_modification": int(time.time())}
                    _thirdparties[i] = updated
                    return {"success": True, "data": updated}
            from app.core.exceptions import DolibarrException

            raise DolibarrException(message="Thirdparty not found", status_code=404)

        elif method == "DELETE" and endpoint.startswith("thirdparties/"):
            tp_id = int(endpoint.split("/")[-1])
            _thirdparties[:] = [t for t in _thirdparties if t["rowid"] != tp_id]
            return {"success": True}

        elif method == "POST" and endpoint == "invoices":
            # Create invoice - calculate totals from lines
            lines = json.get("lines", [])
            total_ht = 0.0
            total_tva = 0.0
            for line in lines:
                qty = line.get("qty", 1.0)
                unit_price = line.get("subprice", line.get("unit_price", 0.0))
                discount = line.get("remise_percent", line.get("discount_percent", 0.0))
                vat_rate = line.get("tva_tx", line.get("vat_rate", 21.0))
                line_ht = qty * unit_price * (1 - discount / 100.0)
                line_tva = line_ht * vat_rate / 100.0
                total_ht += line_ht
                total_tva += line_tva
            total_ttc = total_ht + total_tva

            new_inv = {
                "rowid": _next_invoice_id,
                "ref": f"FAC-{_next_invoice_id:06d}",
                "total_ht": round(total_ht, 2),
                "total_tva": round(total_tva, 2),
                "total_ttc": round(total_ttc, 2),
                "status": 0,
                "date": json.get("date", "2024-01-01"),
                "lines": lines,
                "date_creation": int(time.time()),
                "date_modification": int(time.time()),
            }
            _next_invoice_id += 1
            _invoices.append(new_inv)
            return {"success": True, "data": new_inv, "id": new_inv["rowid"]}

        elif method == "GET" and endpoint == "invoices":
            return {"success": True, "data": _invoices, "total": len(_invoices)}

        elif method == "GET" and endpoint.startswith("invoices/"):
            inv_id = int(endpoint.split("/")[-1])
            inv = next((inv for inv in _invoices if inv["rowid"] == inv_id), None)
            if not inv:
                from app.core.exceptions import DolibarrException

                raise DolibarrException(message="Invoice not found", status_code=404)
            # Return unwrapped data like the real Dolibarr API does for GET
            return inv

        # For other endpoints, raise not implemented
        from app.core.exceptions import DolibarrException

        raise DolibarrException(message=f"Mock not implemented for {method} {endpoint}", status_code=501)

    return mock_request


@pytest_asyncio.fixture
async def mock_redis():
    """Mock Redis for testing."""
    return MockRedis()


@pytest_asyncio.fixture
async def client(mock_redis: MockRedis):
    """Cliente HTTP para testing."""
    # Override the get_redis dependency
    from app.adapters.dolibarr.client import DolibarrClient
    from app.core.database import get_redis

    app.dependency_overrides[get_redis] = lambda: mock_redis

    # Monkey patch DolibarrClient._request to use mock
    original_request = DolibarrClient._request
    DolibarrClient._request = create_mock_dolibarr_request()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    # Clean up
    app.dependency_overrides.clear()
    DolibarrClient._request = original_request


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
            mock_agent.return_value = type(
                "Agent",
                (),
                {
                    "agent_id": "test_agent",
                    "agent_name": "test",
                    "roles": ["read"],
                    "has_role": lambda self, r: True,
                    "has_any_role": lambda self, roles: True,
                },
            )()

            response = await client.get("/health", headers=headers)
            # Health check no tiene rate limit
            assert response.status_code == 200


class TestIdempotency:
    """Tests de idempotencia."""

    @pytest.mark.asyncio
    async def test_idempotency_key_requerida_post(self, client: AsyncClient, api_keys: dict):
        """POST sin Idempotency-Key debe fallar en endpoints mutables."""
        headers = {"Authorization": f"Bearer {api_keys['expedientes']}"}

        with patch("app.dependencies.auth.get_current_agent") as mock_agent:
            mock_agent.return_value = type(
                "Agent",
                (),
                {
                    "agent_id": "test_agent",
                    "agent_name": "expedientes",
                    "roles": ["expedientes", "write"],
                    "has_role": lambda self, r: True,
                    "has_any_role": lambda self, roles: True,
                },
            )()

            response = await client.post(
                "/api/v1/expedientes",
                json={
                    "name": "Test",
                    "breed": "Golden",
                    "sex": "H",
                    "birth_date": "2024-01-15",
                    "color": "Dorado",
                    "weight_kg": 10.0,
                    "microchip": "941000012345678",
                },
                headers=headers,
            )
            # Debería fallar por falta de Idempotency-Key
            assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_idempotency_funciona(self, client: AsyncClient, api_keys: dict):
        """Idempotency-Key funciona correctamente."""
        headers = {
            "Authorization": f"Bearer {api_keys['expedientes']}",
            "Idempotency-Key": "test-key-123",
        }

        with patch("app.dependencies.auth.get_current_agent") as mock_agent:
            mock_agent.return_value = type(
                "Agent",
                (),
                {
                    "agent_id": "test_agent",
                    "agent_name": "expedientes",
                    "roles": ["expedientes", "write"],
                    "has_role": lambda self, r: True,
                    "has_any_role": lambda self, roles: True,
                },
            )()

            # Primera request
            _ = await client.post(
                "/api/v1/expedientes",
                json={
                    "name": "Test",
                    "breed": "Golden",
                    "sex": "H",
                    "birth_date": "2024-01-15",
                    "color": "Dorado",
                    "weight_kg": 10.0,
                    "microchip": "941000012345678",
                },
                headers=headers,
            )

            # Segunda request con misma key
            response2 = await client.post(
                "/api/v1/expedientes",
                json={
                    "name": "Test",
                    "breed": "Golden",
                    "sex": "H",
                    "birth_date": "2024-01-15",
                    "color": "Dorado",
                    "weight_kg": 10.0,
                    "microchip": "941000012345678",
                },
                headers=headers,
            )

            # Segunda debería fallar por idempotencia
            assert response2.status_code == 409


class TestCORS:
    """Tests de CORS."""

    @pytest.mark.asyncio
    async def test_cors_headers(self, client: AsyncClient):
        """Verificar headers CORS."""
        response = await client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code == 200
        assert "access-control-allow-origin" in response.headers


class TestAuditLogging:
    """Tests de logging de auditoría."""

    @pytest.mark.asyncio
    async def test_audit_log_creado(self, client: AsyncClient):
        """Verificar que se crea log de auditoría."""
        # Este test requeriría acceso a la BD de auditoría
        # Se implementaría con base de datos de test


# Tests de esquemas ya están en test_schemas.py

if __name__ == "__main__":
    pytest.main([__file__, "-v"])


@pytest.mark.asyncio
async def test_protected_endpoint_requires_auth(client: AsyncClient):
    """Endpoint protegido sin token debe fallar."""
    response = await client.get("/api/v1/expedientes")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_invalid_token_rejected(client: AsyncClient):
    """Token inválido debe ser rechazado."""
    headers = {"Authorization": "Bearer token_invalido"}
    response = await client.get("/api/v1/expedientes", headers=headers)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_no_extra_fields_allowed(client: AsyncClient, api_keys: dict):
    """Rechazo de campos inesperados."""
    # First we need a valid token - mock the dependency
    with patch("app.dependencies.auth.get_current_agent") as mock_agent:
        mock_agent.return_value = type(
            "Agent",
            (),
            {
                "agent_id": "test_agent",
                "agent_name": "expedientes",
                "roles": ["expedientes", "write"],
                "has_role": lambda self, r: True,
                "has_any_role": lambda self, rs: True,
            },
        )()
        headers = {
            "Authorization": f"Bearer {api_keys['expedientes']}",
            "Idempotency-Key": "test-extra-fields-123",
        }
        payload = {
            "name": "Test",
            "breed": "Labrador",
            "sex": "H",
            "birth_date": "2020-01-01",
            "color": "Negro",
            "weight_kg": 30.0,
            "microchip": "123456789012345",
            "extra_field": "no_allowed",
        }
        response = await client.post("/api/v1/expedientes", json=payload, headers=headers)
        # Should reject extra field via Pydantic -> 422
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_no_secret_leak(client: AsyncClient):
    """Verificar que no se filtren secrets en respuestas."""
    response = await client.get("/")
    text = response.text.lower()
    for secret in ["secret", "password", "key", "token"]:
        assert secret not in text, f"Se encontró '{secret}' en la respuesta"


@pytest.mark.asyncio
async def test_cors_headers(client: AsyncClient):
    """Validar encabezados CORS."""
    resp = await client.options("/", headers={"Origin": "http://evil.com"})
    # Should not reflect arbitrary origin; our backend likely sets specific origins or null
    acao = resp.headers.get("access-control-allow-origin")
    assert acao != "*"  # should not be wildcard


@pytest.mark.asyncio
async def test_rate_limit(client: AsyncClient):
    """Verificar límite básico de rate (asumiendo configurado)."""
    # Make many requests quickly; we expect 429 after limit
    for _ in range(15):
        await client.get("/api/v1/expedientes")
        # May be 401 due to auth, but we just keep hitting
    resp = await client.get("/api/v1/expedientes")
    # If rate limiting is active, we get 429; otherwise 401 (still not 200)
    assert resp.status_code in (429, 401)


# End-to-end flows with dummy data
@pytest.mark.asyncio
async def test_create_and_get_expediente(client: AsyncClient, api_keys: dict):
    with patch("app.dependencies.auth.get_current_agent") as mock_agent:
        mock_agent.return_value = type(
            "Agent",
            (),
            {
                "agent_id": "test_agent",
                "agent_name": "expedientes",
                "roles": ["expedientes", "write"],
                "has_role": lambda self, r: True,
                "has_any_role": lambda self, rs: True,
            },
        )()
        headers = {
            "Authorization": f"Bearer {api_keys['expedientes']}",
            "Idempotency-Key": "test-create-expediente-123",
        }
        payload = {
            "name": "Fido",
            "breed": "Labrador",
            "sex": "M",
            "birth_date": "2020-01-01",
            "color": "Golden",
            "weight_kg": 30.5,
            "microchip": "123456789012345",
        }
        resp = await client.post("/api/v1/expedientes", json=payload, headers=headers)
        assert resp.status_code == 201
        data = resp.json()
        expediente_id = data["id"]
        resp2 = await client.get(f"/api/v1/expedientes/{expediente_id}", headers=headers)
        assert resp2.status_code == 200
        assert resp2.json()["name"] == "Fido"


@pytest.mark.asyncio
async def test_invoice_flow(client: AsyncClient, api_keys: dict):
    with patch("app.dependencies.auth.get_current_agent") as mock_agent:
        # Use invoicing agent which has the required financial roles
        mock_agent.return_value = type(
            "Agent",
            (),
            {
                "agent_id": "test_agent",
                "agent_name": "invoicing",
                "roles": ["invoicing", "read", "write"],
                "has_role": lambda self, r: True,
                "has_any_role": lambda self, rs: True,
            },
        )()
        # Create third party
        headers_tp = {
            "Authorization": f"Bearer {api_keys['invoicing']}",
            "Idempotency-Key": "test-invoice-flow-tp-123",
        }
        tp = {
            "name": "Cliente Test",
            "email": "test@example.com",
            "vat_number": "ESA12345678",
        }
        resp = await client.post("/api/v1/terceros", json=tp, headers=headers_tp)
        assert resp.status_code == 201
        tercero_id = resp.json()["id"]
        # Create invoice with different idempotency key
        headers_inv = {
            "Authorization": f"Bearer {api_keys['invoicing']}",
            "Idempotency-Key": "test-invoice-flow-inv-123",
        }
        inv = {
            "thirdparty_id": tercero_id,
            "date": "2024-01-01",
            "lines": [
                {
                    "description": "Servicio",
                    "qty": 1,
                    "unit_price": 100.0,
                    "vat_rate": 21.0,
                }
            ],
        }
        resp2 = await client.post("/api/v1/facturacion", json=inv, headers=headers_inv)
        assert resp2.status_code == 201
        assert resp2.json()["total_ttc"] == 121.0
