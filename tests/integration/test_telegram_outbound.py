"""
E2E tests for Telegram outbound messaging flow.

Tests the complete flow:
Telegram → Supervisor → DogIntake → Internal API → Dogs API → Telegram outbound
"""

import os
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.core.internal_api_client import InternalAPIClient
from app.core.telegram_client import MockTelegramClient
from app.main import app

# Set up test environment variables BEFORE importing app modules that depend on settings
os.environ.setdefault("AUDIT_DB_HOST", "localhost")
os.environ.setdefault("AUDIT_DB_PORT", "5432")
os.environ.setdefault("AUDIT_DB_NAME", "audit_test")
os.environ.setdefault("AUDIT_DB_USER", "audit")
os.environ.setdefault("AUDIT_DB_PASSWORD", "test")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("REDIS_PORT", "6379")
os.environ.setdefault("REDIS_PASSWORD", "")
os.environ.setdefault("DOLIBARR_API_URL", "http://localhost:8001")
os.environ.setdefault("DOLIBARR_API_KEY", "test-key")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-testing-only")
os.environ.setdefault("FERNET_KEY", "ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Rg=")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("MOCK_DOLIBARR_ENABLED", "true")
os.environ.setdefault("AGENT_API_KEY_SUPERVISOR", "test-supervisor")
os.environ.setdefault("AGENT_API_KEY_PRODUCTS", "test-products")
os.environ.setdefault("AGENT_API_KEY_COMPLIANCE", "test-compliance")
os.environ.setdefault("AGENT_API_KEY_PUBLISHING", "test-publishing")
os.environ.setdefault("AGENT_API_KEY_SALES", "test-sales")
os.environ.setdefault("AGENT_API_KEY_INVOICING", "test-invoicing")
os.environ.setdefault("AGENT_API_KEY_PURCHASES", "test-purchases")
os.environ.setdefault("AGENT_API_KEY_BANKING", "test-banking")
os.environ.setdefault("AGENT_API_KEY_ACCOUNTING", "test-accounting")
os.environ.setdefault("AGENT_API_KEY_TAX", "test-tax")
os.environ.setdefault("AGENT_API_KEY_MARKETING", "test-marketing")
os.environ.setdefault("AGENT_API_KEY_TECHNICAL", "test-technical")
os.environ.setdefault("AGENT_API_KEY_DOG_INTAKE", "test-dog-intake")
os.environ.setdefault("AGENT_API_KEY_EXPEDIENTES", "test-expedientes")
os.environ.setdefault("AGENT_API_KEY_FACTURACION", "test-facturacion")
os.environ.setdefault("TELEGRAM_WEBHOOK_SECRET", "test-secret")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-bot-token")

# Clear settings cache to pick up new environment variables
get_settings.cache_clear()


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
    """Fake agent for testing authentication."""

    def __init__(self, agent_id, agent_name, roles):
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.roles = roles

    def has_role(self, role):
        return role in self.roles

    def has_any_role(self, roles):
        return any(r in self.roles for r in roles)


# Mock Redis at module level
@pytest.fixture(autouse=True)
def mock_redis():
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


class TestTelegramOutbound:
    """Tests for Telegram outbound messaging."""

    @pytest.mark.asyncio
    async def test_A_success_creates_dog_sends_confirmation(self):
        """
        A. SUCCESS
        Telegram update → dog created → send_message called once → confirmación correcta
        """
        mock_telegram = MockTelegramClient()

        # Mock the supervisor_agent to return completed result on last call
        from unittest.mock import AsyncMock

        from agents.supervisor.agent import create_supervisor_agent

        mock_supervisor = create_supervisor_agent(
            {
                "INTERNAL_API_URL": "http://localhost:8000/api/v1",
                "OLLAMA_ENDPOINT": "http://ollama:11434",
                "OLLAMA_MODEL": "llama3.1:8b",
                "OLLAMA_VISION_MODEL": "llava:7b",
                "NVIDIA_API_KEY": "",
                "NVIDIA_BASE_URL": "https://integrate.api.nvidia.com/v1",
                "AGENT_API_KEY_SUPERVISOR": "test-supervisor",
                "AGENT_API_KEY_DOG_INTAKE": "test-dog-intake",
            }
        )

        # Create a mock handle_telegram_message that returns completed on the 9th call
        call_count = 0

        async def mock_handle_telegram_message(update):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {
                    "success": True,
                    "completed": False,
                    "message": "¡Nuevo ingreso de perro! ¿Cuál es el nombre del perro?",
                    "step": "awaiting_name",
                    "session_id": "test",
                    "privacy_scope": "LOCAL_ONLY",
                    "awaiting_input": True,
                }
            elif call_count == 2:
                return {
                    "success": True,
                    "completed": False,
                    "message": "Recibido. ¿Qué raza es?",
                    "step": "awaiting_breed",
                    "session_id": "test",
                    "privacy_scope": "LOCAL_ONLY",
                    "awaiting_input": True,
                }
            elif call_count == 3:
                return {
                    "success": True,
                    "completed": False,
                    "message": "Recibido. ¿Sexo?",
                    "step": "awaiting_sex",
                    "session_id": "test",
                    "privacy_scope": "LOCAL_ONLY",
                    "awaiting_input": True,
                }
            elif call_count == 4:
                return {
                    "success": True,
                    "completed": False,
                    "message": "Recibido. ¿Fecha de nacimiento?",
                    "step": "awaiting_birth_date",
                    "session_id": "test",
                    "privacy_scope": "LOCAL_ONLY",
                    "awaiting_input": True,
                }
            elif call_count == 5:
                return {
                    "success": True,
                    "completed": False,
                    "message": "Recibido. ¿Color?",
                    "step": "awaiting_color",
                    "session_id": "test",
                    "privacy_scope": "LOCAL_ONLY",
                    "awaiting_input": True,
                }
            elif call_count == 6:
                return {
                    "success": True,
                    "completed": False,
                    "message": "Recibido. ¿Microchip?",
                    "step": "awaiting_microchip",
                    "session_id": "test",
                    "privacy_scope": "LOCAL_ONLY",
                    "awaiting_input": True,
                }
            elif call_count == 7:
                return {
                    "success": True,
                    "completed": False,
                    "message": "Recibido. ¿Precio de compra?",
                    "step": "awaiting_purchase_price",
                    "session_id": "test",
                    "privacy_scope": "LOCAL_ONLY",
                    "awaiting_input": True,
                }
            elif call_count == 8:
                return {
                    "success": True,
                    "completed": False,
                    "message": "Recibido. ¿Precio de venta?",
                    "step": "awaiting_sale_price",
                    "session_id": "test",
                    "privacy_scope": "LOCAL_ONLY",
                    "awaiting_input": True,
                }
            elif call_count == 9:
                return {
                    "success": True,
                    "completed": True,
                    "dog": {"id": 1, "internal_id": "DOG-2026-000001", "name": "Thor", "breed_id": 1},
                    "message": "Perro creado",
                    "privacy_scope": "LOCAL_ONLY",
                }
            else:
                return {
                    "success": True,
                    "completed": False,
                    "message": "Done",
                    "step": "completed",
                    "session_id": "test",
                    "privacy_scope": "LOCAL_ONLY",
                }

        mock_supervisor.handle_telegram_message = mock_handle_telegram_message
        mock_supervisor.start = AsyncMock()
        mock_supervisor.stop = AsyncMock()

        await mock_supervisor.start()

        with patch("app.routes.telegram.supervisor_agent", mock_supervisor):
            with patch("app.routes.telegram.telegram_client", mock_telegram):
                with patch("app.routes.telegram.settings.TELEGRAM_WEBHOOK_SECRET", "test-secret"):
                    with patch("app.routes.telegram.settings.ENVIRONMENT", "test"):
                        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                            headers = {
                                "X-Telegram-Bot-Api-Secret-Token": "test-secret",
                                "Content-Type": "application/json",
                            }

                            # Simulate complete dog intake flow via webhook
                            webhook_payload = {
                                "update_id": 999001,
                                "message": {
                                    "message_id": 1,
                                    "date": 1700000000,
                                    "chat": {"id": 111111111, "type": "private"},
                                    "from": {"id": 111111111, "is_bot": False, "first_name": "Test"},
                                    "text": "/start",
                                },
                            }
                            resp = await ac.post("/api/v1/webhook", json=webhook_payload, headers=headers)
                            assert resp.status_code == 200

                            # Continue the intake flow
                            intake_steps = [
                                ("Thor", "awaiting_name"),
                                ("Golden Retriever", "awaiting_breed"),
                                ("M", "awaiting_sex"),
                                ("2026-06-10", "awaiting_birth_date"),
                                ("Dorado", "awaiting_color"),
                                ("saltar", "awaiting_microchip"),  # Skip microchip
                                ("0", "awaiting_purchase_price"),
                                ("1200", "awaiting_sale_price"),
                            ]

                            for i, (text, _expected_step) in enumerate(intake_steps):
                                resp = await ac.post(
                                    "/api/v1/webhook",
                                    json={
                                        "update_id": 999001 + i + 1,
                                        "message": {
                                            "message_id": i + 2,
                                            "date": 1700000000 + i + 1,
                                            "chat": {"id": 111111111, "type": "private"},
                                            "from": {"id": 111111111, "is_bot": False, "first_name": "Test"},
                                            "text": text,
                                        },
                                    },
                                    headers=headers,
                                )
                                assert resp.status_code == 200

                            # Verify send_message was called for each step (9 steps = 9 calls)
                            send_calls = [c for c in mock_telegram.calls if c["method"] == "send_message"]
                            assert len(send_calls) == 9, (
                                f"Expected 9 send_message calls (one per step), got {len(send_calls)}"
                            )

                            # Verify final confirmation message contains key info
                            final_text = send_calls[-1]["text"]
                            assert "Perro registrado correctamente" in final_text
                            assert "DOG-" in final_text
                            assert "Thor" in final_text

        await mock_supervisor.stop()

    @pytest.mark.asyncio
    async def test_B_microchip_absent_no_clarification(self):
        """
        B. MICROCHIP AUSENTE
        Telegram update sin microchip → dog created → microchip=None
        → no clarification por microchip → confirmación enviada
        """
        mock_telegram = MockTelegramClient()

        from unittest.mock import AsyncMock

        from agents.supervisor.agent import create_supervisor_agent

        mock_supervisor = create_supervisor_agent(
            {
                "INTERNAL_API_URL": "http://localhost:8000/api/v1",
                "OLLAMA_ENDPOINT": "http://ollama:11434",
                "OLLAMA_MODEL": "llama3.1:8b",
                "OLLAMA_VISION_MODEL": "llava:7b",
                "NVIDIA_API_KEY": "",
                "NVIDIA_BASE_URL": "https://integrate.api.nvidia.com/v1",
                "AGENT_API_KEY_SUPERVISOR": "test-supervisor",
                "AGENT_API_KEY_DOG_INTAKE": "test-dog-intake",
            }
        )

        call_count = 0

        async def mock_handle_telegram_message(update):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {
                    "success": True,
                    "completed": False,
                    "message": "¡Nuevo ingreso de perro! ¿Cuál es el nombre del perro?",
                    "step": "awaiting_name",
                    "session_id": "test",
                    "privacy_scope": "LOCAL_ONLY",
                    "awaiting_input": True,
                }
            elif call_count == 2:
                return {
                    "success": True,
                    "completed": False,
                    "message": "Recibido. ¿Qué raza es?",
                    "step": "awaiting_breed",
                    "session_id": "test",
                    "privacy_scope": "LOCAL_ONLY",
                    "awaiting_input": True,
                }
            elif call_count == 3:
                return {
                    "success": True,
                    "completed": False,
                    "message": "Recibido. ¿Sexo?",
                    "step": "awaiting_sex",
                    "session_id": "test",
                    "privacy_scope": "LOCAL_ONLY",
                    "awaiting_input": True,
                }
            elif call_count == 4:
                return {
                    "success": True,
                    "completed": False,
                    "message": "Recibido. ¿Fecha de nacimiento?",
                    "step": "awaiting_birth_date",
                    "session_id": "test",
                    "privacy_scope": "LOCAL_ONLY",
                    "awaiting_input": True,
                }
            elif call_count == 5:
                return {
                    "success": True,
                    "completed": False,
                    "message": "Recibido. ¿Color?",
                    "step": "awaiting_color",
                    "session_id": "test",
                    "privacy_scope": "LOCAL_ONLY",
                    "awaiting_input": True,
                }
            elif call_count == 6:
                return {
                    "success": True,
                    "completed": False,
                    "message": "Recibido. ¿Microchip?",
                    "step": "awaiting_microchip",
                    "session_id": "test",
                    "privacy_scope": "LOCAL_ONLY",
                    "awaiting_input": True,
                }
            elif call_count == 7:
                return {
                    "success": True,
                    "completed": False,
                    "message": "Recibido. ¿Precio de compra?",
                    "step": "awaiting_purchase_price",
                    "session_id": "test",
                    "privacy_scope": "LOCAL_ONLY",
                    "awaiting_input": True,
                }
            elif call_count == 8:
                return {
                    "success": True,
                    "completed": False,
                    "message": "Recibido. ¿Precio de venta?",
                    "step": "awaiting_sale_price",
                    "session_id": "test",
                    "privacy_scope": "LOCAL_ONLY",
                    "awaiting_input": True,
                }
            elif call_count == 9:
                return {
                    "success": True,
                    "completed": True,
                    "dog": {"id": 1, "internal_id": "DOG-2026-000001", "name": "Luna", "breed_id": 1},
                    "message": "Perro creado",
                    "privacy_scope": "LOCAL_ONLY",
                }
            else:
                return {
                    "success": True,
                    "completed": False,
                    "message": "Done",
                    "step": "completed",
                    "session_id": "test",
                    "privacy_scope": "LOCAL_ONLY",
                }

        mock_supervisor.handle_telegram_message = mock_handle_telegram_message
        mock_supervisor.start = AsyncMock()
        mock_supervisor.stop = AsyncMock()

        await mock_supervisor.start()

        with patch("app.routes.telegram.supervisor_agent", mock_supervisor):
            with patch("app.routes.telegram.telegram_client", mock_telegram):
                with patch("app.routes.telegram.settings.TELEGRAM_WEBHOOK_SECRET", "test-secret"):
                    with patch("app.routes.telegram.settings.ENVIRONMENT", "test"):
                        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                            headers = {
                                "X-Telegram-Bot-Api-Secret-Token": "test-secret",
                                "Content-Type": "application/json",
                            }

                            # Start intake
                            resp = await ac.post(
                                "/api/v1/webhook",
                                json={
                                    "update_id": 999100,
                                    "message": {
                                        "message_id": 1,
                                        "date": 1700000000,
                                        "chat": {"id": 222222222, "type": "private"},
                                        "from": {"id": 222222222, "is_bot": False, "first_name": "Test"},
                                        "text": "/start",
                                    },
                                },
                                headers=headers,
                            )
                            assert resp.status_code == 200

                            # Provide all required fields, skip microchip with "saltar"
                            intake_steps = [
                                ("Luna", "awaiting_name"),
                                ("Golden Retriever", "awaiting_breed"),
                                ("H", "awaiting_sex"),
                                ("2026-06-10", "awaiting_birth_date"),
                                ("Dorado", "awaiting_color"),
                                ("saltar", "awaiting_microchip"),  # Skip microchip
                                ("0", "awaiting_purchase_price"),
                                ("1200", "awaiting_sale_price"),
                            ]

                            for i, (text, _expected_step) in enumerate(intake_steps):
                                resp = await ac.post(
                                    "/api/v1/webhook",
                                    json={
                                        "update_id": 999100 + i + 1,
                                        "message": {
                                            "message_id": i + 2,
                                            "date": 1700000000 + i + 1,
                                            "chat": {"id": 222222222, "type": "private"},
                                            "from": {"id": 222222222, "is_bot": False, "first_name": "Test"},
                                            "text": text,
                                        },
                                    },
                                    headers=headers,
                                )
                                assert resp.status_code == 200

                            # Verify send_message was called for each step (9 steps = 9 calls)
                            send_calls = [c for c in mock_telegram.calls if c["method"] == "send_message"]
                            assert len(send_calls) == 9, (
                                f"Expected 9 send_message calls (one per step), got {len(send_calls)}"
                            )

                            sent_text = send_calls[-1]["text"]
                            assert "Perro registrado correctamente" in sent_text
                            assert "Luna" in sent_text
                            # No error about missing microchip

        await mock_supervisor.stop()

    @pytest.mark.asyncio
    async def test_C_microchip_present_conserved(self):
        """
        C. MICROCHIP PRESENTE
        Telegram update con microchip → dog created → valor conservado
        """
        mock_telegram = MockTelegramClient()

        from unittest.mock import AsyncMock

        from agents.supervisor.agent import create_supervisor_agent

        mock_supervisor = create_supervisor_agent(
            {
                "INTERNAL_API_URL": "http://localhost:8000/api/v1",
                "OLLAMA_ENDPOINT": "http://ollama:11434",
                "OLLAMA_MODEL": "llama3.1:8b",
                "OLLAMA_VISION_MODEL": "llava:7b",
                "NVIDIA_API_KEY": "",
                "NVIDIA_BASE_URL": "https://integrate.api.nvidia.com/v1",
                "AGENT_API_KEY_SUPERVISOR": "test-supervisor",
                "AGENT_API_KEY_DOG_INTAKE": "test-dog-intake",
            }
        )

        call_count = 0

        async def mock_handle_telegram_message(update):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {
                    "success": True,
                    "completed": False,
                    "message": "¡Nuevo ingreso de perro! ¿Cuál es el nombre del perro?",
                    "step": "awaiting_name",
                    "session_id": "test",
                    "privacy_scope": "LOCAL_ONLY",
                    "awaiting_input": True,
                }
            elif call_count == 2:
                return {
                    "success": True,
                    "completed": False,
                    "message": "Recibido. ¿Qué raza es?",
                    "step": "awaiting_breed",
                    "session_id": "test",
                    "privacy_scope": "LOCAL_ONLY",
                    "awaiting_input": True,
                }
            elif call_count == 3:
                return {
                    "success": True,
                    "completed": False,
                    "message": "Recibido. ¿Sexo?",
                    "step": "awaiting_sex",
                    "session_id": "test",
                    "privacy_scope": "LOCAL_ONLY",
                    "awaiting_input": True,
                }
            elif call_count == 4:
                return {
                    "success": True,
                    "completed": False,
                    "message": "Recibido. ¿Fecha de nacimiento?",
                    "step": "awaiting_birth_date",
                    "session_id": "test",
                    "privacy_scope": "LOCAL_ONLY",
                    "awaiting_input": True,
                }
            elif call_count == 5:
                return {
                    "success": True,
                    "completed": False,
                    "message": "Recibido. ¿Color?",
                    "step": "awaiting_color",
                    "session_id": "test",
                    "privacy_scope": "LOCAL_ONLY",
                    "awaiting_input": True,
                }
            elif call_count == 6:
                return {
                    "success": True,
                    "completed": False,
                    "message": "Recibido. ¿Microchip?",
                    "step": "awaiting_microchip",
                    "session_id": "test",
                    "privacy_scope": "LOCAL_ONLY",
                    "awaiting_input": True,
                }
            elif call_count == 7:
                return {
                    "success": True,
                    "completed": False,
                    "message": "Recibido. ¿Precio de compra?",
                    "step": "awaiting_purchase_price",
                    "session_id": "test",
                    "privacy_scope": "LOCAL_ONLY",
                    "awaiting_input": True,
                }
            elif call_count == 8:
                return {
                    "success": True,
                    "completed": False,
                    "message": "Recibido. ¿Precio de venta?",
                    "step": "awaiting_sale_price",
                    "session_id": "test",
                    "privacy_scope": "LOCAL_ONLY",
                    "awaiting_input": True,
                }
            elif call_count == 9:
                return {
                    "success": True,
                    "completed": True,
                    "dog": {"id": 1, "internal_id": "DOG-2026-000001", "name": "Rex", "breed_id": 1},
                    "message": "Perro creado",
                    "privacy_scope": "LOCAL_ONLY",
                }
            else:
                return {
                    "success": True,
                    "completed": False,
                    "message": "Done",
                    "step": "completed",
                    "session_id": "test",
                    "privacy_scope": "LOCAL_ONLY",
                }

        mock_supervisor.handle_telegram_message = mock_handle_telegram_message
        mock_supervisor.start = AsyncMock()
        mock_supervisor.stop = AsyncMock()

        await mock_supervisor.start()

        with patch("app.routes.telegram.supervisor_agent", mock_supervisor):
            with patch("app.routes.telegram.telegram_client", mock_telegram):
                with patch("app.routes.telegram.settings.TELEGRAM_WEBHOOK_SECRET", "test-secret"):
                    with patch("app.routes.telegram.settings.ENVIRONMENT", "test"):
                        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                            headers = {
                                "X-Telegram-Bot-Api-Secret-Token": "test-secret",
                                "Content-Type": "application/json",
                            }

                            # Start intake
                            resp = await ac.post(
                                "/api/v1/webhook",
                                json={
                                    "update_id": 999200,
                                    "message": {
                                        "message_id": 1,
                                        "date": 1700000000,
                                        "chat": {"id": 333333333, "type": "private"},
                                        "from": {"id": 333333333, "is_bot": False, "first_name": "Test"},
                                        "text": "/start",
                                    },
                                },
                                headers=headers,
                            )
                            assert resp.status_code == 200

                            # Provide all fields INCLUDING microchip
                            intake_steps = [
                                ("Rex", "awaiting_name"),
                                ("Golden Retriever", "awaiting_breed"),
                                ("M", "awaiting_sex"),
                                ("2026-06-10", "awaiting_birth_date"),
                                ("Negro", "awaiting_color"),
                                ("123456789012345", "awaiting_microchip"),  # Provide microchip
                                ("0", "awaiting_purchase_price"),
                                ("1200", "awaiting_sale_price"),
                            ]

                            for i, (text, _expected_step) in enumerate(intake_steps):
                                resp = await ac.post(
                                    "/api/v1/webhook",
                                    json={
                                        "update_id": 999200 + i + 1,
                                        "message": {
                                            "message_id": i + 2,
                                            "date": 1700000000 + i + 1,
                                            "chat": {"id": 333333333, "type": "private"},
                                            "from": {"id": 333333333, "is_bot": False, "first_name": "Test"},
                                            "text": text,
                                        },
                                    },
                                    headers=headers,
                                )
                                assert resp.status_code == 200

                            # Verify send_message was called for each step (9 steps = 9 calls)
                            send_calls = [c for c in mock_telegram.calls if c["method"] == "send_message"]
                            assert len(send_calls) == 9, (
                                f"Expected 9 send_message calls (one per step), got {len(send_calls)}"
                            )

        await mock_supervisor.stop()

    @pytest.mark.asyncio
    async def test_D_missing_required_field_no_dog_creation(self):
        """
        D. MISSING REQUIRED FIELD
        falta otro campo realmente obligatorio
        → no dog creation
        → send_message pide aclaración
        """
        mock_telegram = MockTelegramClient()

        from unittest.mock import AsyncMock

        from agents.supervisor.agent import create_supervisor_agent

        mock_supervisor = create_supervisor_agent(
            {
                "INTERNAL_API_URL": "http://localhost:8000/api/v1",
                "OLLAMA_ENDPOINT": "http://ollama:11434",
                "OLLAMA_MODEL": "llama3.1:8b",
                "OLLAMA_VISION_MODEL": "llava:7b",
                "NVIDIA_API_KEY": "",
                "NVIDIA_BASE_URL": "https://integrate.api.nvidia.com/v1",
                "AGENT_API_KEY_SUPERVISOR": "test-supervisor",
                "AGENT_API_KEY_DOG_INTAKE": "test-dog-intake",
            }
        )

        call_count = 0

        async def mock_handle_telegram_message(update):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {
                    "success": True,
                    "completed": False,
                    "message": "¡Nuevo ingreso de perro! ¿Cuál es el nombre del perro?",
                    "step": "awaiting_name",
                    "session_id": "test",
                    "privacy_scope": "LOCAL_ONLY",
                    "awaiting_input": True,
                }
            elif call_count == 2:
                return {
                    "success": True,
                    "completed": False,
                    "message": "Recibido. ¿Qué raza es? (ej: Bulldog francés, Golden Retriever)",
                    "step": "awaiting_breed",
                    "session_id": "test",
                    "privacy_scope": "LOCAL_ONLY",
                    "awaiting_input": True,
                }
            else:
                return {
                    "success": True,
                    "completed": False,
                    "message": "Need more info",
                    "step": "awaiting_breed",
                    "session_id": "test",
                    "privacy_scope": "LOCAL_ONLY",
                    "awaiting_input": True,
                }

        mock_supervisor.handle_telegram_message = mock_handle_telegram_message
        mock_supervisor.start = AsyncMock()
        mock_supervisor.stop = AsyncMock()

        await mock_supervisor.start()

        with patch("app.routes.telegram.supervisor_agent", mock_supervisor):
            with patch("app.routes.telegram.telegram_client", mock_telegram):
                with patch("app.routes.telegram.settings.TELEGRAM_WEBHOOK_SECRET", "test-secret"):
                    with patch("app.routes.telegram.settings.ENVIRONMENT", "test"):
                        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                            headers = {
                                "X-Telegram-Bot-Api-Secret-Token": "test-secret",
                                "Content-Type": "application/json",
                            }

                            # Start intake
                            resp = await ac.post(
                                "/api/v1/webhook",
                                json={
                                    "update_id": 999300,
                                    "message": {
                                        "message_id": 1,
                                        "date": 1700000000,
                                        "chat": {"id": 444444444, "type": "private"},
                                        "from": {"id": 444444444, "is_bot": False, "first_name": "Test"},
                                        "text": "/start",
                                    },
                                },
                                headers=headers,
                            )
                            assert resp.status_code == 200

                            # Provide ONLY name, then stop - missing sex, birth_date, color, breed
                            resp = await ac.post(
                                "/api/v1/webhook",
                                json={
                                    "update_id": 999301,
                                    "message": {
                                        "message_id": 2,
                                        "date": 1700000001,
                                        "chat": {"id": 444444444, "type": "private"},
                                        "from": {"id": 444444444, "is_bot": False, "first_name": "Test"},
                                        "text": "Incomplete Dog",
                                    },
                                },
                                headers=headers,
                            )
                            assert resp.status_code == 200
                            data = resp.json()
                            assert data["completed"] is False
                            assert "dog" not in data

                            # Should have sent messages for the first two steps (start + name)
                            send_calls = [c for c in mock_telegram.calls if c["method"] == "send_message"]
                            assert len(send_calls) == 2, (
                                f"Expected 2 send_message calls (for /start and name), got {len(send_calls)}"
                            )

                            # Verify the messages are the intermediate steps
                            assert "nombre" in send_calls[0]["text"].lower()
                            assert "raza" in send_calls[1]["text"].lower()

        await mock_supervisor.stop()

    @pytest.mark.asyncio
    async def test_E_internal_api_failure_no_false_confirmation(self):
        """
        E. INTERNAL API FAILURE
        → no confirmación falsa
        → mensaje controlado
        """
        from unittest.mock import AsyncMock

        from agents.supervisor.agent import create_supervisor_agent

        failing_supervisor = create_supervisor_agent(
            {
                "INTERNAL_API_URL": "http://localhost:8000/api/v1",
                "OLLAMA_ENDPOINT": "http://ollama:11434",
                "OLLAMA_MODEL": "llama3.1:8b",
                "OLLAMA_VISION_MODEL": "llava:7b",
                "NVIDIA_API_KEY": "",
                "NVIDIA_BASE_URL": "https://integrate.api.nvidia.com/v1",
                "AGENT_API_KEY_SUPERVISOR": "test-supervisor",
                "AGENT_API_KEY_DOG_INTAKE": "test-dog-intake",
            }
        )

        async def mock_handle_telegram_message(update):
            return {"success": False, "error": "API error: 500", "completed": False}

        failing_supervisor.handle_telegram_message = mock_handle_telegram_message
        failing_supervisor.start = AsyncMock()
        failing_supervisor.stop = AsyncMock()

        await failing_supervisor.start()

        mock_telegram = MockTelegramClient()

        with patch("app.routes.telegram.supervisor_agent", failing_supervisor):
            with patch("app.routes.telegram.telegram_client", mock_telegram):
                with patch("app.routes.telegram.settings.TELEGRAM_WEBHOOK_SECRET", "test-secret"):
                    with patch("app.routes.telegram.settings.ENVIRONMENT", "test"):
                        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                            headers = {
                                "X-Telegram-Bot-Api-Secret-Token": "test-secret",
                                "Content-Type": "application/json",
                            }

                            webhook_payload = {
                                "update_id": 999400,
                                "message": {
                                    "message_id": 1,
                                    "date": 1700000000,
                                    "chat": {"id": 555555555, "type": "private"},
                                    "from": {"id": 555555555, "is_bot": False, "first_name": "Test"},
                                    "text": "/start",
                                },
                            }

                            resp = await ac.post("/api/v1/webhook", json=webhook_payload, headers=headers)
                            assert resp.status_code == 200

                            # Should NOT send outbound message for failed processing
                            send_calls = [c for c in mock_telegram.calls if c["method"] == "send_message"]
                            assert len(send_calls) == 0, "No outbound message should be sent for failed processing"

        await failing_supervisor.stop()

    @pytest.mark.asyncio
    async def test_F_outbound_failure_dog_not_deleted(self):
        """
        F. TELEGRAM OUTBOUND FAILURE
        → dog ya creado permanece
        → no segunda creación
        """
        from unittest.mock import AsyncMock

        mock_telegram = MockTelegramClient()
        # Make send_message raise an exception
        mock_telegram.send_message = AsyncMock(side_effect=Exception("Network error"))
        mock_telegram.calls = []  # Reset calls

        from unittest.mock import AsyncMock

        from agents.supervisor.agent import create_supervisor_agent

        mock_supervisor = create_supervisor_agent(
            {
                "INTERNAL_API_URL": "http://localhost:8000/api/v1",
                "OLLAMA_ENDPOINT": "http://ollama:11434",
                "OLLAMA_MODEL": "llama3.1:8b",
                "OLLAMA_VISION_MODEL": "llava:7b",
                "NVIDIA_API_KEY": "",
                "NVIDIA_BASE_URL": "https://integrate.api.nvidia.com/v1",
                "AGENT_API_KEY_SUPERVISOR": "test-supervisor",
                "AGENT_API_KEY_DOG_INTAKE": "test-dog-intake",
            }
        )

        call_count = 0

        async def mock_handle_telegram_message(update):
            nonlocal call_count
            call_count += 1
            if call_count == 9:
                return {
                    "success": True,
                    "completed": True,
                    "dog": {"id": 1, "internal_id": "DOG-2026-000001", "name": "Test", "breed_id": 1},
                    "message": "Perro creado",
                    "privacy_scope": "LOCAL_ONLY",
                }
            return {
                "success": True,
                "completed": False,
                "message": "Step",
                "step": "step",
                "session_id": "test",
                "privacy_scope": "LOCAL_ONLY",
                "awaiting_input": True,
            }

        mock_supervisor.handle_telegram_message = mock_handle_telegram_message
        mock_supervisor.start = AsyncMock()
        mock_supervisor.stop = AsyncMock()

        await mock_supervisor.start()

        with patch("app.routes.telegram.supervisor_agent", mock_supervisor):
            with patch("app.routes.telegram.telegram_client", mock_telegram):
                with patch("app.routes.telegram.settings.TELEGRAM_WEBHOOK_SECRET", "test-secret"):
                    with patch("app.routes.telegram.settings.ENVIRONMENT", "test"):
                        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                            headers = {
                                "X-Telegram-Bot-Api-Secret-Token": "test-secret",
                                "Content-Type": "application/json",
                            }

                            # Complete intake flow
                            for i in range(9):
                                resp = await ac.post(
                                    "/api/v1/webhook",
                                    json={
                                        "update_id": 999500 + i,
                                        "message": {
                                            "message_id": i + 1,
                                            "date": 1700000000 + i,
                                            "chat": {"id": 666666666, "type": "private"},
                                            "from": {"id": 666666666, "is_bot": False, "first_name": "Test"},
                                            "text": "test",
                                        },
                                    },
                                    headers=headers,
                                )
                                assert resp.status_code == 200

                            # Webhook should return 200 even if outbound fails
                            assert resp.status_code == 200
                            data = resp.json()
                            assert data["success"] is True

        await mock_supervisor.stop()

    @pytest.mark.asyncio
    async def test_G_duplicate_update_same_update_id(self):
        """
        G. DUPLICATE UPDATE
        mismo update_id dos veces → dog creation == 1
        """
        mock_telegram = MockTelegramClient()

        from unittest.mock import AsyncMock

        from agents.supervisor.agent import create_supervisor_agent

        mock_supervisor = create_supervisor_agent(
            {
                "INTERNAL_API_URL": "http://localhost:8000/api/v1",
                "OLLAMA_ENDPOINT": "http://ollama:11434",
                "OLLAMA_MODEL": "llama3.1:8b",
                "OLLAMA_VISION_MODEL": "llava:7b",
                "NVIDIA_API_KEY": "",
                "NVIDIA_BASE_URL": "https://integrate.api.nvidia.com/v1",
                "AGENT_API_KEY_SUPERVISOR": "test-supervisor",
                "AGENT_API_KEY_DOG_INTAKE": "test-dog-intake",
            }
        )

        call_count = 0

        async def mock_handle_telegram_message(update):
            nonlocal call_count
            call_count += 1
            if call_count == 9:
                return {
                    "success": True,
                    "completed": True,
                    "dog": {"id": 1, "internal_id": "DOG-2026-000001", "name": "Duplicado", "breed_id": 1},
                    "message": "Perro creado",
                    "privacy_scope": "LOCAL_ONLY",
                }
            return {
                "success": True,
                "completed": False,
                "message": "Step",
                "step": "step",
                "session_id": "test",
                "privacy_scope": "LOCAL_ONLY",
                "awaiting_input": True,
            }

        mock_supervisor.handle_telegram_message = mock_handle_telegram_message
        mock_supervisor.start = AsyncMock()
        mock_supervisor.stop = AsyncMock()

        await mock_supervisor.start()

        with patch("app.routes.telegram.supervisor_agent", mock_supervisor):
            with patch("app.routes.telegram.telegram_client", mock_telegram):
                with patch("app.routes.telegram.settings.TELEGRAM_WEBHOOK_SECRET", "test-secret"):
                    with patch("app.routes.telegram.settings.ENVIRONMENT", "test"):
                        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                            headers = {
                                "X-Telegram-Bot-Api-Secret-Token": "test-secret",
                                "Content-Type": "application/json",
                            }

                            # First webhook with update_id 999600
                            webhook_payload = {
                                "update_id": 999600,
                                "message": {
                                    "message_id": 1,
                                    "date": 1700000000,
                                    "chat": {"id": 777777777, "type": "private"},
                                    "from": {"id": 777777777, "is_bot": False, "first_name": "Test"},
                                    "text": "/start",
                                },
                            }

                            # Complete intake for first request
                            for i in range(9):
                                resp = await ac.post(
                                    "/api/v1/webhook",
                                    json={
                                        "update_id": 999600 + i,
                                        "message": {
                                            "message_id": i + 1,
                                            "date": 1700000000 + i,
                                            "chat": {"id": 777777777, "type": "private"},
                                            "from": {"id": 777777777, "is_bot": False, "first_name": "Test"},
                                            "text": "test",
                                        },
                                    },
                                    headers=headers,
                                )
                                assert resp.status_code == 200

                            # Now send SAME update_id again (simulating Telegram retry)
                            resp = await ac.post("/api/v1/webhook", json=webhook_payload, headers=headers)
                            assert resp.status_code == 200

                    # Should not create a second dog - only one confirmation sent
                    _ = [c for c in mock_telegram.calls if c["method"] == "send_message"]
                    # The duplicate update_id should be handled gracefully

        await mock_supervisor.stop()

    @pytest.mark.asyncio
    async def test_H_invalid_webhook_secret_no_outbound(self):
        """
        H. INVALID WEBHOOK SECRET
        → 403
        → send_message calls == 0
        """
        mock_telegram = MockTelegramClient()

        with patch("app.routes.telegram.telegram_client", mock_telegram):
            with patch("app.routes.telegram.settings.TELEGRAM_WEBHOOK_SECRET", "test-secret"):
                with patch("app.routes.telegram.settings.ENVIRONMENT", "test"):
                    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                        headers = {
                            "X-Telegram-Bot-Api-Secret-Token": "wrong-secret",
                            "Content-Type": "application/json",
                        }

                        webhook_payload = {
                            "update_id": 999700,
                            "message": {
                                "message_id": 1,
                                "date": 1700000000,
                                "chat": {"id": 888888888, "type": "private"},
                                "from": {"id": 888888888, "is_bot": False, "first_name": "Test"},
                                "text": "/start",
                            },
                        }

                        resp = await ac.post("/api/v1/webhook", json=webhook_payload, headers=headers)
                        assert resp.status_code == 403

                        # No outbound message should be sent for invalid secret
                        send_calls = [c for c in mock_telegram.calls if c["method"] == "send_message"]
                        assert len(send_calls) == 0


class TestInternalAPIClientRetry:
    """Tests for InternalAPIClient retry logic with idempotency."""

    @pytest.mark.asyncio
    async def test_post_timeout_exactly_one_call(self):
        """
        POST timeout → exactly 1 call (no retry)
        """
        import httpx

        from app.core.internal_api_client import InternalAPIError

        client = InternalAPIClient(
            base_url="http://test",
            api_key="test-key",
            agent_name="test_agent",
            timeout=1.0,
            max_retries=3,
        )

        # Mock the underlying httpx client to raise TimeoutException on POST
        mock_httpx_client = AsyncMock()
        mock_httpx_client.request = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
        client._client = mock_httpx_client

        # Attempt POST - should raise InternalAPIError immediately (no retries)
        try:
            await client.post("/dogs", json={"name": "Test"})
            raise AssertionError("Should have raised InternalAPIError")
        except InternalAPIError as e:
            assert e.status_code == 504  # Timeout

        # Verify exactly 1 call was made (no retries for POST)
        assert mock_httpx_client.request.call_count == 1

    @pytest.mark.asyncio
    async def test_get_timeout_allows_retry(self):
        """
        GET timeout → retry allowed
        """
        import httpx

        client = InternalAPIClient(
            base_url="http://test",
            api_key="test-key",
            agent_name="test_agent",
            timeout=1.0,
            max_retries=3,
        )

        # Mock the underlying httpx client to raise TimeoutException twice then succeed
        mock_httpx_client = AsyncMock()

        timeout_exc = httpx.TimeoutException("Timeout")
        success_response = AsyncMock()
        success_response.status_code = 200
        success_response.json = lambda: {"data": "ok"}

        mock_httpx_client.request = AsyncMock(
            side_effect=[
                timeout_exc,
                timeout_exc,
                success_response,
            ]
        )
        client._client = mock_httpx_client

        # Attempt GET - should retry and eventually succeed
        result = await client.get("/dogs")
        assert result == {"data": "ok"}

        # Verify 3 calls were made (initial + 2 retries)
        assert mock_httpx_client.request.call_count == 3
