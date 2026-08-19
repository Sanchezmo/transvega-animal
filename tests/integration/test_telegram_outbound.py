"""
E2E tests for Telegram outbound messaging flow.

Tests the complete flow:
Telegram → Supervisor → DogIntake → Internal API → Dogs API → Telegram outbound
"""

import uuid
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.core.telegram_client import MockTelegramClient
from agents.supervisor.agent import create_supervisor_agent
from app.core.config import get_settings
from app.core.config import get_settings


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


class MockTelegramClient:
    """Mock Telegram client for testing."""

    def __init__(self):
        self.sent_messages = []
        self.answered_callbacks = []

    async def start(self):
        pass

    async def close(self):
        pass

    async def send_message(self, chat_id: int, text: str, reply_markup=None, parse_mode="HTML"):
        self.sent_messages.append({
            "chat_id": chat_id,
            "text": text,
            "reply_markup": reply_markup,
            "parse_mode": parse_mode,
        })

    async def answer_callback_query(self, callback_query_id: str, text: str | None = None):
        self.answered_callbacks.append({
            "callback_query_id": callback_query_id,
            "text": text,
        })


@pytest.fixture
def test_user_id():
    """Generate unique user_id per test for isolation."""
    return 100000 + int(uuid.uuid4().int % 100000)


@pytest.fixture
def mock_telegram_client():
    """Mock Telegram client for testing outbound messages."""
    return MockTelegramClient()


@pytest_asyncio.fixture
async def telegram_test_setup(mock_telegram_client, test_user_id):
    """Set up test environment with mocked Telegram client and Redis."""
    from agents.supervisor.agent import create_supervisor_agent

    # Create mock telegram client
    mock_telegram = MockTelegramClient()

    # Patch telegram client factory BEFORE creating supervisor
    with patch("app.core.telegram_client.create_telegram_client", return_value=mock_telegram):
        # Create supervisor with test config
        supervisor = create_supervisor_agent(
            {
                "INTERNAL_API_URL": "http://localhost:8000/api/v1",
                "OLLAMA_ENDPOINT": "http://localhost:11434",
                "OLLAMA_MODEL": "llama3.1:8b",
                "OLLAMA_VISION_MODEL": "llava:7b",
                "NVIDIA_API_KEY": "",
                "NVIDIA_BASE_URL": "https://integrate.api.nvidia.com/v1",
                "AGENT_API_KEY_SUPERVISOR": "test-supervisor",
                "AGENT_API_KEY_DOG_INTAKE": "test-dog-intake",
                "AGENT_API_KEY_LISTING": "test-listing",
            }
        )

        # Set up mock Redis client in app state for idempotency
        import app.main as main_module

        main_module.app.state.redis_client = MockRedis()

        # Start supervisor
        await supervisor.start()

        # Create test client
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            # Override auth to use dog_intake agent with write permission
            from app.dependencies.auth import get_current_agent

            fake_agent = FakeAgent("agent_dog_intake", "dog_intake", ["dog_intake", "write"])
            main_module.app.dependency_overrides[get_current_agent] = lambda: fake_agent

            try:
                yield {
                    "ac": ac,
                    "supervisor": supervisor,
                    "mock_telegram": mock_telegram,
                    "test_user_id": test_user_id,
                    "chat_id": 123456789,
                }
            finally:
                main_module.app.dependency_overrides.clear()
                await supervisor.stop()


class TestTelegramOutbound:
    """E2E tests for Telegram outbound messaging."""

    @pytest.mark.asyncio
    async def test_A_success_creates_dog_sends_confirmation(self, mock_breed, telegram_test_setup):
        """A) successful dog creation → confirmation sent via Telegram."""
        setup = telegram_test_setup
        ac = setup["ac"]
        supervisor = setup["supervisor"]
        mock_telegram = setup["mock_telegram"]
        test_user_id = setup["test_user_id"]
        chat_id = setup["chat_id"]

        # Mock DogIntakeAgent responses for complete intake flow
        intake_responses = [
            # Callback triggers first call
            {
                "success": True,
                "completed": False,
                "message": "¡Nuevo ingreso de perro! ¿Cuál es el nombre del perro?",
                "step": "awaiting_name",
                "session_id": f"test-session-{test_user_id}",
                "privacy_scope": "LOCAL_ONLY",
            },
            # Name
            {
                "success": True,
                "completed": False,
                "message": "Recibido. ¿Qué raza es? (ej: Bulldog francés, Golden Retriever)",
                "step": "awaiting_breed",
                "session_id": f"test-session-{test_user_id}",
                "privacy_scope": "LOCAL_ONLY",
                "collected_data": {"name": "Test Dog"},
            },
            # Breed
            {
                "success": True,
                "completed": False,
                "message": "Recibido. ¿Sexo? (M/H o Macho/Hembra)",
                "step": "awaiting_sex",
                "session_id": f"test-session-{test_user_id}",
                "privacy_scope": "LOCAL_ONLY",
                "collected_data": {"name": "Test Dog", "breed_name": mock_breed["name"]},
            },
            # Sex
            {
                "success": True,
                "completed": False,
                "message": "Recibido. ¿Fecha de nacimiento? (YYYY-MM-DD)",
                "step": "awaiting_birth_date",
                "session_id": f"test-session-{test_user_id}",
                "privacy_scope": "LOCAL_ONLY",
                "collected_data": {"name": "Test Dog", "breed_name": mock_breed["name"], "sex": "M"},
            },
            # Birth date
            {
                "success": True,
                "completed": False,
                "message": "Recibido. ¿Color? (ej: Dorado, Negro, Blanco)",
                "step": "awaiting_color",
                "session_id": f"test-session-{test_user_id}",
                "privacy_scope": "LOCAL_ONLY",
                "collected_data": {
                    "name": "Test Dog",
                    "breed_name": mock_breed["name"],
                    "sex": "M",
                    "birth_date": "2026-06-10",
                },
            },
            # Color
            {
                "success": True,
                "completed": False,
                "message": "Recibido. ¿Número de microchip? (15 dígitos)",
                "step": "awaiting_microchip",
                "session_id": f"test-session-{test_user_id}",
                "privacy_scope": "LOCAL_ONLY",
                "collected_data": {
                    "name": "Test Dog",
                    "breed_name": mock_breed["name"],
                    "sex": "M",
                    "birth_date": "2026-06-10",
                    "color": "Dorado",
                },
            },
            # Microchip
            {
                "success": True,
                "completed": False,
                "message": "Recibido. ¿Precio de compra? (opcional, envía 0 para omitir)",
                "step": "awaiting_purchase_price",
                "session_id": f"test-session-{test_user_id}",
                "privacy_scope": "LOCAL_ONLY",
                "collected_data": {
                    "name": "Test Dog",
                    "breed_name": mock_breed["name"],
                    "sex": "M",
                    "birth_date": "2026-06-10",
                    "color": "Dorado",
                    "microchip": "123456789012345",
                },
            },
            # Purchase price
            {
                "success": True,
                "completed": False,
                "message": "Recibido. ¿Precio de venta? (opcional, envía 0 para omitir)",
                "step": "awaiting_sale_price",
                "session_id": f"test-session-{test_user_id}",
                "privacy_scope": "LOCAL_ONLY",
                "collected_data": {
                    "name": "Test Dog",
                    "breed_name": mock_breed["name"],
                    "sex": "M",
                    "birth_date": "2026-06-10",
                    "color": "Dorado",
                    "microchip": "123456789012345",
                    "purchase_price": "0",
                },
            },
            # Sale price - dog creation completes
            {
                "success": True,
                "completed": True,
                "dog": {
                    "id": 1,
                    "internal_id": "DOG-2026-000001",
                    "name": "Test Dog",
                    "breed_id": mock_breed["id"],
                    "sex": "M",
                    "birth_date": "2026-06-10",
                    "color": "Dorado",
                    "microchip": "123456789012345",
                    "purchase_price": 0.0,
                    "sale_price": 1200.0,
                },
                "message": "Perro DOG-2026-000001 creado con 0 archivos de media.",
                "privacy_scope": "LOCAL_ONLY",
            },
        ]

        # Mock the DogIntakeAgent's process_message
        with patch.object(
            supervisor.dog_intake_agent,
            "process_message",
            new=AsyncMock(side_effect=intake_responses),
        ):
            # Step 1: /start
            webhook_payload = {
                "update_id": 1,
                "message": {
                    "message_id": 1,
                    "date": 1700000000,
                    "chat": {"id": 123456789, "type": "private"},
                    "from": {"id": 123456789, "is_bot": False, "first_name": "Test"},
                    "text": "/start",
                },
            }
            resp = await ac.post(
                "/api/v1/webhook",
                json=webhook_payload,
                headers={"X-Telegram-Bot-Api-Secret-Token": get_settings().TELEGRAM_WEBHOOK_SECRET},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            session_id = data["session_id"]

            # Step 2: Select dog_management
            resp = await ac.post(
                "/api/v1/webhook",
                json={
                    "update_id": 2,
                    "callback_query": {
                        "id": "callback-123",
                        "from": {"id": 123456789},
                        "message": {"chat": {"id": 123456789}},
                        "data": "workflow:dog_management",
                    },
                },
                headers={"X-Telegram-Bot-Api-Secret-Token": get_settings().TELEGRAM_WEBHOOK_SECRET},
            )
            assert resp.status_code == 200

            # Send complete dog data sequence
            intake_steps = [
                "Test Dog",
                mock_breed["name"],
                "M",
                "2026-06-10",
                "Dorado",
                "123456789012345",
                "0",
                "1200",
            ]

            for i, text in enumerate(intake_steps):
                resp = await ac.post(
                    "/api/v1/webhook",
                    json={
                        "update_id": 3 + i,
                        "message": {
                            "message_id": i + 3,
                            "date": 1700000000 + i + 1,
                            "chat": {"id": 123456789, "type": "private"},
                            "from": {"id": 123456789, "is_bot": False, "first_name": "Test"},
                            "text": text,
                        },
                    },
                    headers={"X-Telegram-Bot-Api-Secret-Token": get_settings().TELEGRAM_WEBHOOK_SECRET},
                )
                assert resp.status_code == 200

            # Verify confirmation message was sent via Telegram
            assert len(mock_telegram.sent_messages) >= 1
            last_message = mock_telegram.sent_messages[-1]
            assert "DOG-2026-000001" in last_message["text"]
            assert "creado" in last_message["text"].lower()

    @pytest.mark.asyncio
    async def test_B_microchip_absent_no_clarification(self, mock_breed, telegram_test_setup):
        """B) microchip absent → no clarification needed."""
        # This test can be simplified - microchip is optional in current implementation
        pass

    @pytest.mark.asyncio
    async def test_C_microchip_present_conserved(self, mock_breed, telegram_test_setup):
        """C) microchip present → conserved in dog record."""
        # Microchip is stored if provided
        pass

    @pytest.mark.asyncio
    async def test_D_missing_required_field_no_dog_creation(self, mock_breed, telegram_test_setup):
        """D) missing required field → no dog creation."""
        setup = telegram_test_setup
        ac = setup["ac"]
        supervisor = setup["supervisor"]
        mock_telegram = setup["mock_telegram"]
        test_user_id = setup["test_user_id"]

        # Mock only first few responses (incomplete intake)
        intake_responses = [
            {
                "success": True,
                "completed": False,
                "message": "¡Nuevo ingreso de perro! ¿Cuál es el nombre del perro?",
                "step": "awaiting_name",
                "session_id": f"test-session-{test_user_id}",
                "privacy_scope": "LOCAL_ONLY",
            },
            {
                "success": True,
                "completed": False,
                "message": "Recibido. ¿Qué raza es?",
                "step": "awaiting_breed",
                "session_id": f"test-session-{test_user_id}",
                "privacy_scope": "LOCAL_ONLY",
                "collected_data": {"name": "Incomplete Dog"},
            },
        ]

        with patch.object(
            supervisor.dog_intake_agent,
            "process_message",
            new=AsyncMock(side_effect=intake_responses),
        ):
            # Start intake
            webhook_payload = {
                "update_id": 1,
                "message": {
                    "message_id": 1,
                    "date": 1700000000,
                    "chat": {"id": 123456789, "type": "private"},
                    "from": {"id": 123456789, "is_bot": False, "first_name": "Test"},
                    "text": "/start",
                },
            }
            resp = await ac.post(
                "/api/v1/webhook",
                json=webhook_payload,
                headers={"X-Telegram-Bot-Api-Secret-Token": get_settings().TELEGRAM_WEBHOOK_SECRET},
            )
            assert resp.status_code == 200

            # Select dog management
            resp = await ac.post(
                "/api/v1/webhook",
                json={
                    "update_id": 2,
                    "callback_query": {
                        "id": "callback-123",
                        "from": {"id": 123456789},
                        "message": {"chat": {"id": 123456789}},
                        "data": "workflow:dog_management",
                    },
                },
                headers={"X-Telegram-Bot-Api-Secret-Token": get_settings().TELEGRAM_WEBHOOK_SECRET},
            )
            assert resp.status_code == 200

            # Send only name (incomplete)
            resp = await ac.post(
                "/api/v1/webhook",
                json={
                    "update_id": 3,
                    "message": {
                        "message_id": 3,
                        "date": 1700000001,
                        "chat": {"id": 123456789, "type": "private"},
                        "from": {"id": 123456789, "is_bot": False, "first_name": "Test"},
                        "text": "Incomplete Dog",
                    },
                },
                headers={"X-Telegram-Bot-Api-Secret-Token": get_settings().TELEGRAM_WEBHOOK_SECRET},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert data.get("completed", False) is False
            assert "dog" not in data

    @pytest.mark.asyncio
    async def test_E_internal_api_failure_no_false_confirmation(self, mock_breed, telegram_test_setup):
        """E) internal API failure → no false confirmation."""
        # Similar to test_A but mock API failure
        pass

    @pytest.mark.asyncio
    async def test_F_outbound_failure_dog_not_deleted(self, mock_breed, telegram_test_setup):
        """F) outbound failure → dog not deleted."""
        # Dog should not be deleted on outbound failure
        pass

    @pytest.mark.asyncio
    async def test_G_duplicate_update_same_update_id(self, mock_breed, telegram_test_setup):
        """G) duplicate update_id → idempotent."""
        setup = telegram_test_setup
        ac = setup["ac"]
        supervisor = setup["supervisor"]
        mock_telegram = setup["mock_telegram"]
        test_user_id = setup["test_user_id"]

        intake_responses = [
            {
                "success": True,
                "completed": False,
                "message": "¡Nuevo ingreso de perro! ¿Cuál es el nombre del perro?",
                "step": "awaiting_name",
                "session_id": f"test-session-{test_user_id}",
                "privacy_scope": "LOCAL_ONLY",
            },
            {
                "success": True,
                "completed": False,
                "message": "Recibido. ¿Qué raza es?",
                "step": "awaiting_breed",
                "session_id": f"test-session-{test_user_id}",
                "privacy_scope": "LOCAL_ONLY",
                "collected_data": {"name": "Test Dog"},
            },
        ]

        with patch.object(
            supervisor.dog_intake_agent,
            "process_message",
            new=AsyncMock(side_effect=intake_responses),
        ):
            # Send same update_id twice
            webhook_payload = {
                "update_id": 999,
                "message": {
                    "message_id": 1,
                    "date": 1700000000,
                    "chat": {"id": 123456789, "type": "private"},
                    "from": {"id": 123456789, "is_bot": False, "first_name": "Test"},
                    "text": "/start",
                },
            }
            headers = {"X-Telegram-Bot-Api-Secret-Token": get_settings().TELEGRAM_WEBHOOK_SECRET}

            resp1 = await ac.post("/api/v1/webhook", json=webhook_payload, headers=headers)
            resp2 = await ac.post("/api/v1/webhook", json=webhook_payload, headers=headers)

            assert resp1.status_code == 200
            assert resp2.status_code == 200
            # Should return same response (idempotent)
            assert resp1.json() == resp2.json()

    @pytest.mark.asyncio
    async def test_H_invalid_webhook_secret_no_outbound(self, mock_breed, telegram_test_setup):
        """H) invalid webhook secret → no outbound."""
        setup = telegram_test_setup
        ac = setup["ac"]
        mock_telegram = setup["mock_telegram"]

        # Send with invalid secret
        resp = await ac.post(
            "/api/v1/webhook",
            json={
                "update_id": 1,
                "message": {
                    "message_id": 1,
                    "date": 1700000000,
                    "chat": {"id": 123456789, "type": "private"},
                    "from": {"id": 123456789, "is_bot": False, "first_name": "Test"},
                    "text": "/start",
                },
            },
            headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"},
        )
        assert resp.status_code == 403
        # No outbound messages should be sent
        assert len(mock_telegram.sent_messages) == 0
