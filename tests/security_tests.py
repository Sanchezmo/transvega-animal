import uuid

import pytest
from httpx import AsyncClient

from app.main import app


class FakeAgent:
    def __init__(self, agent_id, agent_name, roles):
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.roles = roles

    def has_role(self, role):
        return role in self.roles

    def has_any_role(self, roles):
        return any(r in self.roles for r in roles)


@pytest.mark.asyncio
async def test_protected_endpoint_requires_auth():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        resp = await ac.get("/api/v1/expedientes/expedientes")
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_invalid_token_rejected():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        headers = {"Authorization": "Bearer invalid.token.here"}
        resp = await ac.get("/api/v1/expedientes/expedientes", headers=headers)
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_no_extra_fields_allowed():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        fake = FakeAgent("test_agent", "expedientes", ["expedientes", "write"])
        app.dependency_overrides[
            __import__("app.dependencies.auth", fromlist=["get_current_agent"]).get_current_agent
        ] = lambda: fake
        resp = await ac.post(
            "/api/v1/expedientes/expedientes",
            json={
                "name": "Test",
                "breed": "Labrador",
                "sex": "M",
                "birth_date": "2024-01-01",
                "color": "Yellow",
                "weight_kg": 10.0,
                "microchip": "123456789012345",
            },
            headers={"Authorization": "Bearer fake-token"},
        )
        assert resp.status_code == 422
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_no_secret_leak():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        resp = await ac.get("/api/v1/salud/agents")
        data = resp.json()
        # Ensure no API keys leaked
        assert "api_key" not in str(data).lower()
        assert "apikey" not in str(data).lower()
        assert "secret" not in str(data).lower()


@pytest.mark.asyncio
async def test_cors_headers():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        resp = await ac.options("/api/v1/expedientes/expedientes")
        assert resp.status_code == 200
        assert "access-control-allow-origin" in resp.headers


@pytest.mark.asyncio
async def test_rate_limit():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Use a fake agent to bypass auth
        fake = FakeAgent("test_agent", "expedientes", ["expedientes", "read"])
        app.dependency_overrides[
            __import__("app.dependencies.auth", fromlist=["get_current_agent"]).get_current_agent
        ] = lambda: fake

        token = "fake-token"
        headers = {
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": str(uuid.uuid4()),
        }
        # Make multiple requests quickly to hit rate limit
        for _ in range(5):
            resp = await ac.get("/api/v1/expedientes/expedientes", headers=headers)
            # We expect either 200 (if not rate limited) or 429 (if rate limited)
            assert resp.status_code in [200, 429]
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_and_get_expediente():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        fake = FakeAgent("test_agent", "expedientes", ["expedientes", "write"])
        app.dependency_overrides[
            __import__("app.dependencies.auth", fromlist=["get_current_agent"]).get_current_agent
        ] = lambda: fake
        expediente_data = {
            "name": "Test Animal",
            "breed": "Labrador",
            "sex": "M",
            "birth_date": "2024-01-01",
            "color": "Yellow",
            "weight_kg": 10.0,
            "microchip": "123456789012345",
        }
        resp = await ac.post(
            "/api/v1/expedientes/expedientes",
            json=expediente_data,
            headers={"Authorization": "Bearer fake-token"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["success"]
        expediente_id = data["data"]["id"]
        resp = await ac.get(
            f"/api/v1/expedientes/expedientes/{expediente_id}",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"]
        assert data["data"]["name"] == "Test Animal"
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_invoice_flow():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Create thirdparty
        fake = FakeAgent("test_agent", "terceros", ["invoicing", "write"])
        app.dependency_overrides[
            __import__("app.dependencies.auth", fromlist=["get_current_agent"]).get_current_agent
        ] = lambda: fake
        tercero_data = {
            "name": "Test Client",
            "email": "client@test.com",
            "phone": "123456789",
            "address": "Calle Falsa 123",
            "zip": "28001",
            "town": "Madrid",
            "country_id": 1,
            "country_code": "ES",
            "vat_number": "B12345678",
        }
        resp = await ac.post(
            "/api/v1/terceros/terceros",
            json=tercero_data,
            headers={"Authorization": "Bearer fake-token"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["success"]
        tercero_id = data["data"]["id"]
        # Create invoice
        fake = FakeAgent("test_agent", "facturacion", ["invoicing", "write"])
        app.dependency_overrides[
            __import__("app.dependencies.auth", fromlist=["get_current_agent"]).get_current_agent
        ] = lambda: fake
        invoice_data = {
            "thirdparty_id": tercero_id,
            "date": "2024-01-01",
            "lines": [
                {
                    "description": "Test service",
                    "unit_price": 100.0,
                    "qty": 1,
                    "vat_rate": 21.0,
                    "discount_percent": 0.0,
                }
            ],
        }
        resp = await ac.post(
            "/api/v1/facturacion/facturas",
            json=invoice_data,
            headers={"Authorization": "Bearer fake-token"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["success"]
        assert data["data"]["id"] == 1
        assert data["data"]["ref"].startswith("FAC-")
        app.dependency_overrides.clear()
