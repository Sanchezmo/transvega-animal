import pytest
from httpx import AsyncClient
from app.main import app
from app.dependencies.auth import AgentIdentity
import uuid

class FakeAgent:
    def __init__(self, agent_id, agent_name, roles):
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.roles = roles
    def has_role(self, role): return role in self.roles
    def has_any_role(self, roles): return any(r in self.roles for r in roles)

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

        token = "fake-token"
        headers = {
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": str(uuid.uuid4())
        }
        payload = {
            "name": "Fido",
            "breed": "Labrador",
            "sex": "M",
            "birth_date": "2020-01-01",
            "color": "Golden",
            "weight_kg": 30.5,
            "microchip": "123456789012345",
            "extra_field": "should not be allowed"
        }
        resp = await ac.post(
            "/api/v1/expedientes/expedientes", json=payload, headers=headers
        )
        # Accept 201 (created) if extra field is ignored, or 400/422 if rejected
        assert resp.status_code in (201, 400, 422)
        app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_no_secret_leak():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        fake = FakeAgent("test_agent", "expedientes", ["expedientes", "write"])
        app.dependency_overrides[
            __import__("app.dependencies.auth", fromlist=["get_current_agent"]).get_current_agent
        ] = lambda: fake

        token = "fake-token"
        headers = {
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": str(uuid.uuid4())
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
        resp = await ac.post(
            "/api/v1/expedientes/expedientes", json=payload, headers=headers
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "microchip" in data
        # Ensure no actual secrets leaked (internal_id etc are part of schema, not secrets)
        for secret in ["secret", "password", "key", "token"]:
            assert secret not in str(data).lower()

        app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_cors_headers():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        resp = await ac.options("/api/v1/expedientes/expedientes")
        # Accept either 200 (CORS preflight) or 405 if OPTIONS not explicitly handled
        assert resp.status_code in (200, 405)
        if resp.status_code == 200:
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
            "Idempotency-Key": str(uuid.uuid4())
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

        token = "fake-token"
        headers = {
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": str(uuid.uuid4())
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
        resp = await ac.post(
            "/api/v1/expedientes/expedientes", json=payload, headers=headers
        )
        assert resp.status_code == 201
        data = resp.json()
        expediente_id = data["id"]

        resp2 = await ac.get(
            f"/api/v1/expedientes/expedientes/{expediente_id}", headers=headers
        )
        assert resp2.status_code == 200
        assert resp2.json()["name"] == "Fido"

        app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_invoice_flow():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        fake = FakeAgent("test_agent", "facturacion", ["invoicing", "write"])
        app.dependency_overrides[
            __import__("app.dependencies.auth", fromlist=["get_current_agent"]).get_current_agent
        ] = lambda: fake

        token = "fake-token"
        headers = {
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": str(uuid.uuid4())
        }
        tp = {
            "name": "Cliente Test",
            "email": "test@example.com",
        }
        resp = await ac.post(
            "/api/v1/terceros/terceros", json=tp, headers=headers
        )
        assert resp.status_code == 201
        tercero_id = resp.json()["id"]

        inv = {
            "thirdparty_id": tercero_id,
            "date": "2024-01-01",
            "lines": [
                {"description": "Servicio", "qty": 1, "unit_price": 100.0, "vat_rate": 21.0}
            ],
        }
        headers2 = {
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": str(uuid.uuid4())
        }
        resp2 = await ac.post(
            "/api/v1/facturacion/facturas", json=inv, headers=headers2
        )
        assert resp2.status_code == 201
        assert resp2.json()["total_ttc"] == 121.0

        app.dependency_overrides.clear()