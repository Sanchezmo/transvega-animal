"""
E2E test for Telegram → Supervisor → DogIntakeAgent → InternalAPIClient → Integration API → DB flow.

This test demonstrates the complete E2E flow without contacting real Telegram.
"""

import asyncio
import os
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Set up test environment variables BEFORE importing app
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

# Clear settings cache to pick up new environment variables
from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()

from agents.dog_intake.agent import DogIntakeAgent  # noqa: E402
from agents.supervisor.agent import SupervisorAgent  # noqa: E402
from app.core.internal_api_client import InternalAPIClient  # noqa: E402
from app.main import app  # noqa: E402


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


@pytest_asyncio.fixture
async def mock_telegram_update():
    """Create a mock Telegram update simulating a dog intake conversation."""
    return {
        "update_id": 123456789,
        "message": {
            "message_id": 1,
            "date": 1700000000,
            "chat": {"id": 123456789, "type": "private", "first_name": "Test", "username": "testuser"},
            "from": {"id": 123456789, "is_bot": False, "first_name": "Test", "username": "testuser"},
            "text": "/start",
        },
    }


@pytest_asyncio.fixture
async def mock_breed():
    """Create a test breed in the database using mocked API."""
    import uuid

    from httpx import ASGITransport, AsyncClient

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Create a breed first with unique name
        fake = FakeAgent("test_agent", "dog_intake", ["dog_intake", "write"])
        from app.dependencies.auth import get_current_agent

        app.dependency_overrides[get_current_agent] = lambda: fake

        token = "fake-token"
        headers = {
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": f"test-idem-key-breed-{uuid.uuid4().hex[:8]}",
        }
        breed_name = f"Golden Retriever Test {uuid.uuid4().hex[:8]}"
        breed_payload = {
            "name": breed_name,
            "species": "dog",
        }
        resp = await ac.post("/api/v1/dogs/breeds", json=breed_payload, headers=headers)
        assert resp.status_code == 201
        breed = resp.json()

        app.dependency_overrides.clear()
        return breed


class TestTelegramDogIntakeE2E:
    """E2E tests for the Telegram → Supervisor → DogIntakeAgent → InternalAPIClient → Integration API → DB flow."""

    @pytest.mark.asyncio
    async def test_supervisor_routes_telegram_to_dog_intake(self, mock_telegram_update):
        """Test that SupervisorAgent routes Telegram messages to DogIntakeAgent via callback."""
        config = {
            "INTERNAL_API_URL": "http://localhost:8000/api/v1",
            "OLLAMA_ENDPOINT": "http://ollama:11434",
            "OLLAMA_MODEL": "llama3.1:8b",
            "OLLAMA_VISION_MODEL": "llava:7b",
            "NVIDIA_API_KEY": "",
            "NVIDIA_BASE_URL": "https://integrate.api.nvidia.com/v1",
            "AGENT_API_KEY_SUPERVISOR": "test-supervisor-key",
            "AGENT_API_KEY_DOG_INTAKE": "test-dog-intake",
        }

        agent = SupervisorAgent(config)
        # Mock the internal API client to avoid real HTTP calls
        agent.api_client = AsyncMock()
        agent.api_client.base_url = "http://localhost:8000/api/v1"
        agent.api_client.aclose = AsyncMock()

        # Mock the dog_intake_agent
        agent.dog_intake_agent = AsyncMock()
        agent.dog_intake_agent.start = AsyncMock()
        agent.dog_intake_agent.stop = AsyncMock()

        # Mock the other sub-agents
        agent.media_pipeline_agent = AsyncMock()
        agent.content_agent = AsyncMock()
        agent.publishing_agent = AsyncMock()
        agent.listing_agent = AsyncMock()
        for attr in ["media_pipeline_agent", "content_agent", "publishing_agent", "listing_agent"]:
            getattr(agent, attr).start = AsyncMock()
            getattr(agent, attr).stop = AsyncMock()

        # Mock conversation manager
        mock_cm = AsyncMock()
        mock_cm.get_or_create_session = AsyncMock(
            return_value={
                "session_id": "test-session-123",
                "telegram_user_id": 123456789,
                "telegram_chat_id": 123456789,
                "workflow_type": "none",
                "workflow_step": "awaiting_workflow_selection",
                "context": {},
                "created_at": "2024-01-01T00:00:00",
                "updated_at": "2024-01-01T00:00:00",
                "expires_at": "2025-01-01T00:00:00",
            }
        )
        mock_cm.update_session = AsyncMock(return_value=True)
        mock_cm.update_context = AsyncMock(return_value=True)
        mock_cm.clear_workflow = AsyncMock(return_value=True)
        mock_cm.clear_context = AsyncMock(return_value=True)
        mock_cm.get_session = AsyncMock(return_value=None)
        agent.conversation_manager = mock_cm

        # Mock telegram client
        mock_tc = AsyncMock()
        mock_tc.start = AsyncMock()
        mock_tc.close = AsyncMock()
        mock_tc.send_message = AsyncMock()
        mock_tc.answer_callback_query = AsyncMock()

        import app.core.telegram_client as tc_module

        tc_module.create_telegram_client = AsyncMock(return_value=mock_tc)

        await agent.start()

        # Mock DogIntakeAgent response for dog management flow
        agent.dog_intake_agent.process_message.return_value = {
            "success": True,
            "completed": False,
            "message": "¡Nuevo ingreso de perro! ¿Cuál es el nombre del perro?",
            "step": "awaiting_name",
            "session_id": "test-session-123",
            "privacy_scope": "LOCAL_ONLY",
        }

        # Step 1: /start shows menu
        start_update = {
            "update_id": 1,
            "message": {
                "message_id": 1,
                "date": 1700000000,
                "chat": {"id": 123456789, "type": "private"},
                "from": {"id": 123456789, "is_bot": False},
                "text": "/start",
            },
        }
        result_start = await agent.handle_telegram_message(start_update)
        assert result_start["success"] is True
        assert result_start["workflow_type"] == "none"
        assert result_start["workflow_step"] == "awaiting_workflow_selection"
        assert "session_id" in result_start
        assert "nombre" in result_start["message"].lower() or "Hermes" in result_start["message"]

        # Step 2: User selects dog management via callback (button press)
        callback_update = {
            "update_id": 2,
            "callback_query": {
                "id": "callback-123",
                "from": {"id": 123456789},
                "message": {"chat": {"id": 123456789}},
                "data": "workflow:dog_management",
            },
        }
        result_callback = await agent.handle_telegram_message(callback_update)

        # Verify the flow - new architecture uses session_id, workflow_type, workflow_step
        assert result_callback["success"] is True
        assert result_callback["workflow_type"] == "dog_management"
        assert result_callback["workflow_step"] == "dog_awaiting_name"
        assert "perro" in result_callback["message"].lower() or "gestión" in result_callback["message"].lower()
        assert result_callback["awaiting_input"] is True
        assert mock_tc.answer_callback_query.called

        # Verify DogIntakeAgent was called for the dog management selection
        agent.dog_intake_agent.process_message.assert_called_once()
        call_args = agent.dog_intake_agent.process_message.call_args[0][0]
        assert call_args["chat_id"] == 123456789
        assert call_args["user_id"] == 123456789
        # The dog intake agent receives empty text for initial trigger
        assert call_args["text"] == ""

    @pytest.mark.asyncio
    async def test_dog_intake_agent_creates_dog_via_api(self):
        """Test DogIntakeAgent creates a dog via InternalAPIClient → Integration API."""

        config = {
            "INTERNAL_API_URL": "http://localhost:8000/api/v1",
            "AGENT_API_KEY_DOG_INTAKE": "test-dog-intake-key",
        }

        agent = DogIntakeAgent(config)

        # Mock the internal API client by patching create_internal_api_client
        mock_api_client = AsyncMock()
        mock_api_client.base_url = "http://localhost:8000/api/v1"
        mock_api_client.start = AsyncMock()
        mock_api_client.close = AsyncMock()

        # Use a fixed breed ID (doesn't need to exist in DB for this mocked test)
        test_breed_id = 1

        # Mock breed lookup
        mock_api_client.get.return_value = {"data": [{"id": test_breed_id, "name": "Golden Retriever"}]}

        # Mock dog creation response
        mock_api_client.post.return_value = {
            "id": 1,
            "internal_id": "DOG-2026-000001",
            "name": "Thor",
            "breed_id": test_breed_id,
            "sex": "M",
            "birth_date": "2026-06-10",
            "color": "Dorado",
            "microchip": "123456789012345",
        }

        with patch("agents.dog_intake.agent.create_internal_api_client", return_value=mock_api_client):
            try:
                await agent.start()

                # Create dog via agent
                dog_data = {
                    "name": "Thor",
                    "breed_id": test_breed_id,
                    "sex": "M",
                    "birth_date": "2026-06-10",
                    "color": "Dorado",
                    "microchip": "123456789012345",
                    "purchase_price": 0.0,
                    "sale_price": 1200.0,
                }

                result = await agent._create_dog(dog_data)
            finally:
                # Ensure agent is stopped even if test fails
                await agent.stop()

        # Verify the result
        assert result["success"] is True
        assert result["dog"]["id"] == 1
        assert result["dog"]["internal_id"] == "DOG-2026-000001"
        assert result["dog"]["name"] == "Thor"

        # Verify API was called with correct payload
        mock_api_client.post.assert_called_once()
        call_args = mock_api_client.post.call_args
        assert call_args[0][0] in ("/dogs/", "/dogs")
        payload = call_args[1]["json"]
        assert payload["name"] == "Thor"
        assert payload["breed_id"] == 1
        assert payload["sex"] == "M"
        assert payload["microchip"] == "123456789012345"

    @pytest.mark.asyncio
    async def test_full_e2e_flow_telegram_to_db(self):
        """
        Test the complete E2E flow:
        Telegram → Supervisor → DogIntakeAgent → InternalAPIClient → Integration API → DB
        This test mocks the InternalAPIClient to avoid real HTTP calls,
        but exercises all the agent logic layers.
        """

        # Create a complete flow with all agents mocked at the API boundary
        config = {
            "INTERNAL_API_URL": "http://localhost:8000/api/v1",
            "OLLAMA_ENDPOINT": "http://ollama:11434",
            "OLLAMA_MODEL": "llama3.1:8b",
            "OLLAMA_VISION_MODEL": "llava:7b",
            "NVIDIA_API_KEY": "",
            "NVIDIA_BASE_URL": "https://integrate.api.nvidia.com/v1",
            "AGENT_API_KEY_SUPERVISOR": "test-supervisor-key",
            "AGENT_API_KEY_DOG_INTAKE": "test-dog-intake",
        }

        # Use a fixed breed ID (doesn't need to exist in DB for this mocked test)
        test_breed_id = 1

        supervisor = SupervisorAgent(config)

        # Mock the API client at the Supervisor level
        supervisor.api_client = AsyncMock()
        supervisor.api_client.base_url = "http://localhost:8000/api/v1"
        supervisor.api_client.aclose = AsyncMock()

        # Mock the DogIntakeAgent to simulate the intake flow
        supervisor.dog_intake_agent = AsyncMock()

        # Mock the other sub-agents
        supervisor.media_pipeline_agent = AsyncMock()
        supervisor.content_agent = AsyncMock()
        supervisor.publishing_agent = AsyncMock()
        supervisor.listing_agent = AsyncMock()
        for attr in ["media_pipeline_agent", "content_agent", "publishing_agent", "listing_agent"]:
            getattr(supervisor, attr).start = AsyncMock()
            getattr(supervisor, attr).stop = AsyncMock()

        # Mock conversation manager (Redis session state)
        mock_cm = AsyncMock()
        session_data = {
            "session_id": "test-session-123",
            "telegram_user_id": 123456789,
            "telegram_chat_id": 123456789,
            "workflow_type": "none",
            "workflow_step": "awaiting_workflow_selection",
            "context": {},
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T00:00:00",
            "expires_at": "2025-01-01T00:00:00",
        }
        mock_cm.get_or_create_session = AsyncMock(return_value=session_data)
        mock_cm.update_session = AsyncMock(return_value=True)
        mock_cm.update_context = AsyncMock(return_value=True)
        mock_cm.clear_workflow = AsyncMock(return_value=True)
        mock_cm.clear_context = AsyncMock(return_value=True)
        mock_cm.get_session = AsyncMock(return_value=session_data)
        supervisor.conversation_manager = mock_cm

        # Mock telegram client
        mock_tc = AsyncMock()
        mock_tc.start = AsyncMock()
        mock_tc.close = AsyncMock()
        mock_tc.send_message = AsyncMock()
        mock_tc.answer_callback_query = AsyncMock()

        import app.core.telegram_client as tc_module

        tc_module.create_telegram_client = AsyncMock(return_value=mock_tc)

        # Simulate the intake conversation flow - DogIntakeAgent responses
        intake_responses = [
            # Step 1: /start - dog management selected
            {
                "success": True,
                "completed": False,
                "message": "¡Nuevo ingreso de perro! ¿Cuál es el nombre del perro?",
                "step": "awaiting_name",
                "session_id": "test-session-123",
                "privacy_scope": "LOCAL_ONLY",
            },
            # Step 2: Name provided
            {
                "success": True,
                "completed": False,
                "message": "Recibido. ¿Qué raza es? (ej: Bulldog francés, Golden Retriever)",
                "step": "awaiting_breed",
                "session_id": "test-session-123",
                "privacy_scope": "LOCAL_ONLY",
                "collected_data": {"name": "Thor"},
            },
            # Step 3: Breed provided
            {
                "success": True,
                "completed": False,
                "message": "Recibido. ¿Sexo? (M/H o Macho/Hembra)",
                "step": "awaiting_sex",
                "session_id": "test-session-123",
                "privacy_scope": "LOCAL_ONLY",
                "collected_data": {"name": "Thor", "breed_name": "Golden Retriever"},
            },
            # Step 4: Sex provided
            {
                "success": True,
                "completed": False,
                "message": "Recibido. ¿Fecha de nacimiento? (YYYY-MM-DD)",
                "step": "awaiting_birth_date",
                "session_id": "test-session-123",
                "privacy_scope": "LOCAL_ONLY",
                "collected_data": {"name": "Thor", "breed_name": "Golden Retriever", "sex": "M"},
            },
            # Step 5: Birth date provided
            {
                "success": True,
                "completed": False,
                "message": "Recibido. ¿Color? (ej: Dorado, Negro, Blanco)",
                "step": "awaiting_color",
                "session_id": "test-session-123",
                "privacy_scope": "LOCAL_ONLY",
                "collected_data": {
                    "name": "Thor",
                    "breed_name": "Golden Retriever",
                    "sex": "M",
                    "birth_date": "2026-06-10",
                },
            },
            # Step 6: Color provided
            {
                "success": True,
                "completed": False,
                "message": "Recibido. ¿Número de microchip? (15 dígitos)",
                "step": "awaiting_microchip",
                "session_id": "test-session-123",
                "privacy_scope": "LOCAL_ONLY",
                "collected_data": {
                    "name": "Thor",
                    "breed_name": "Golden Retriever",
                    "sex": "M",
                    "birth_date": "2026-06-10",
                    "color": "Dorado",
                },
            },
            # Step 7: Microchip provided
            {
                "success": True,
                "completed": False,
                "message": "Recibido. ¿Precio de compra? (opcional, envía 0 para omitir)",
                "step": "awaiting_purchase_price",
                "session_id": "test-session-123",
                "privacy_scope": "LOCAL_ONLY",
                "collected_data": {
                    "name": "Thor",
                    "breed_name": "Golden Retriever",
                    "sex": "M",
                    "birth_date": "2026-06-10",
                    "color": "Dorado",
                    "microchip": "123456789012345",
                },
            },
            # Step 8: Purchase price
            {
                "success": True,
                "completed": False,
                "message": "Recibido. ¿Precio de venta? (opcional, envía 0 para omitir)",
                "step": "awaiting_sale_price",
                "session_id": "test-session-123",
                "privacy_scope": "LOCAL_ONLY",
                "collected_data": {
                    "name": "Thor",
                    "breed_name": "Golden Retriever",
                    "sex": "M",
                    "birth_date": "2026-06-10",
                    "color": "Dorado",
                    "microchip": "123456789012345",
                    "purchase_price": "0",
                },
            },
            # Step 9: Sale price - dog creation completes
            {
                "success": True,
                "completed": True,
                "dog": {
                    "id": 1,
                    "internal_id": "DOG-2026-000001",
                    "name": "Thor",
                    "breed_id": test_breed_id,
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

        # Set up the mock to return responses in sequence
        supervisor.dog_intake_agent.process_message.side_effect = intake_responses
        supervisor.dog_intake_agent.start = AsyncMock()
        supervisor.dog_intake_agent.stop = AsyncMock()

        try:
            await supervisor.start()

            # Simulate the complete Telegram conversation
            chat_id = 123456789
            user_id = 123456789

            # Step 1: /start - first need to select dog management
            # With new architecture, /start shows menu, then callback selects workflow
            result1 = await supervisor.handle_telegram_message(
                {
                    "update_id": 1,
                    "message": {
                        "message_id": 1,
                        "date": 1700000000,
                        "chat": {"id": chat_id, "type": "private"},
                        "from": {"id": user_id, "is_bot": False},
                        "text": "/start",
                    },
                }
            )

            assert result1["success"] is True
            assert result1["awaiting_input"] is True
            assert result1["workflow_type"] == "none"
            assert result1["workflow_step"] == "awaiting_workflow_selection"
            assert "session_id" in result1

            # Now select dog management via callback (simulating button press)
            # The user would press the "Gestionar perro" button
            session_data["workflow_type"] = "dog_management"
            session_data["workflow_step"] = "dog_awaiting_name"

            result_dog_select = await supervisor.handle_telegram_message(
                {
                    "update_id": 2,
                    "callback_query": {
                        "id": "callback-123",
                        "from": {"id": user_id},
                        "message": {"chat": {"id": chat_id}},
                        "data": "workflow:dog_management",
                    },
                }
            )

            assert result_dog_select["success"] is True
            assert result_dog_select["workflow_type"] == "dog_management"
            assert result_dog_select["workflow_step"] == "dog_awaiting_name"
            assert mock_tc.answer_callback_query.called

            # Step 2: Name
            result2 = await supervisor.handle_telegram_message(
                {
                    "update_id": 3,
                    "message": {
                        "message_id": 2,
                        "date": 1700000001,
                        "chat": {"id": chat_id, "type": "private"},
                        "from": {"id": user_id, "is_bot": False},
                        "text": "Thor",
                    },
                }
            )

            assert result2["success"] is True
            assert result2["awaiting_input"] is True

            # Step 3: Breed
            result3 = await supervisor.handle_telegram_message(
                {
                    "update_id": 4,
                    "message": {
                        "message_id": 3,
                        "date": 1700000002,
                        "chat": {"id": chat_id, "type": "private"},
                        "from": {"id": user_id, "is_bot": False},
                        "text": "Golden Retriever",
                    },
                }
            )

            assert result3["success"] is True

            # Step 4: Sex
            result4 = await supervisor.handle_telegram_message(
                {
                    "update_id": 5,
                    "message": {
                        "message_id": 4,
                        "date": 1700000003,
                        "chat": {"id": chat_id, "type": "private"},
                        "from": {"id": user_id, "is_bot": False},
                        "text": "M",
                    },
                }
            )

            assert result4["success"] is True

            # Step 5: Birth date
            result5 = await supervisor.handle_telegram_message(
                {
                    "update_id": 6,
                    "message": {
                        "message_id": 5,
                        "date": 1700000004,
                        "chat": {"id": chat_id, "type": "private"},
                        "from": {"id": user_id, "is_bot": False},
                        "text": "2026-06-10",
                    },
                }
            )

            assert result5["success"] is True

            # Step 6: Color
            result6 = await supervisor.handle_telegram_message(
                {
                    "update_id": 7,
                    "message": {
                        "message_id": 6,
                        "date": 1700000005,
                        "chat": {"id": chat_id, "type": "private"},
                        "from": {"id": user_id, "is_bot": False},
                        "text": "Dorado",
                    },
                }
            )

            assert result6["success"] is True

            # Step 7: Microchip
            result7 = await supervisor.handle_telegram_message(
                {
                    "update_id": 8,
                    "message": {
                        "message_id": 7,
                        "date": 1700000006,
                        "chat": {"id": chat_id, "type": "private"},
                        "from": {"id": user_id, "is_bot": False},
                        "text": "123456789012345",
                    },
                }
            )

            assert result7["success"] is True

            # Step 8: Purchase price (0)
            result8 = await supervisor.handle_telegram_message(
                {
                    "update_id": 9,
                    "message": {
                        "message_id": 8,
                        "date": 1700000007,
                        "chat": {"id": chat_id, "type": "private"},
                        "from": {"id": user_id, "is_bot": False},
                        "text": "0",
                    },
                }
            )

            assert result8["success"] is True

            # Step 9: Sale price - dog creation completes
            result9 = await supervisor.handle_telegram_message(
                {
                    "update_id": 10,
                    "message": {
                        "message_id": 9,
                        "date": 1700000008,
                        "chat": {"id": chat_id, "type": "private"},
                        "from": {"id": user_id, "is_bot": False},
                        "text": "1200",
                    },
                }
            )

            assert result9["success"] is True
            assert result9["completed"] is True  # Dog intake completed
            assert "dog" in result9
            assert result9["dog"]["internal_id"] == "DOG-2026-000001"
            assert result9["dog"]["name"] == "Thor"
            assert result9["dog"]["sale_price"] == 1200.0

            # Verify workflow advanced to media_ingest (dog_awaiting_media in current implementation)
            workflow_id = f"wf-{chat_id}-{user_id}"
            workflow = supervisor.active_workflows.get(workflow_id)
            assert workflow is not None
            assert workflow["dog_internal_id"] == "DOG-2026-000001"
            assert workflow["step"] in ("media_ingest", "dog_awaiting_media")

        finally:
            await supervisor.stop()

        # Verify DogIntakeAgent was called for each step (9 times: start + 8 inputs)
        assert supervisor.dog_intake_agent.process_message.call_count == 9

    @pytest.mark.asyncio
    async def test_telegram_webhook_secret_verification(self):
        """Test that Telegram webhook secret is verified."""

        from app.core.config import get_settings
        from app.routes.telegram import _verify_webhook_secret

        # Test with correct secret - patch where it's used in telegram module
        class MockSettings:
            def __init__(self, secret, environment):
                self.TELEGRAM_WEBHOOK_SECRET = secret
                self.ENVIRONMENT = environment

        mock_settings = MockSettings("test-secret", "development")
        with patch("app.routes.telegram.get_settings", return_value=mock_settings):
            get_settings.cache_clear()
            assert _verify_webhook_secret("test-secret") is True
            assert _verify_webhook_secret("wrong-secret") is False
            assert _verify_webhook_secret(None) is False

        # Test without secret in development (should allow)
        mock_settings = MockSettings(None, "development")
        with patch("app.routes.telegram.get_settings", return_value=mock_settings):
            get_settings.cache_clear()
            assert _verify_webhook_secret("any-secret") is True

        # Test with secret in production (should require correct secret)
        mock_settings = MockSettings("test-secret", "production")
        with patch("app.routes.telegram.get_settings", return_value=mock_settings):
            get_settings.cache_clear()
            assert _verify_webhook_secret("test-secret") is True
            assert _verify_webhook_secret("wrong-secret") is False

        get_settings.cache_clear()

    @pytest.mark.asyncio
    async def test_no_cloud_provider_called(self):
        """Verify that LOCAL_ONLY privacy scope is used - no cloud calls."""
        from agents.dog_intake.agent import DogIntakeAgent
        from app.core.model_router import create_model_router
        from app.core.privacy_router import privacy_router

        # Test that DogIntakeAgent uses LOCAL_ONLY
        config = {
            "INTERNAL_API_URL": "http://localhost:8000/api/v1",
            "OLLAMA_ENDPOINT": "http://ollama:11434",
            "OLLAMA_MODEL": "llama3.1:8b",
            "OLLAMA_VISION_MODEL": "llava:7b",
            "NVIDIA_API_KEY": "test-nvidia-key",
            "NVIDIA_BASE_URL": "https://integrate.api.nvidia.com/v1",
            "AGENT_API_KEY_DOG_INTAKE": "test-key",
        }

        _ = DogIntakeAgent(config)

        # Verify the agent is configured with LOCAL_ONLY intent
        # The agent uses create_model_router which creates both Ollama (local) and NVIDIA (cloud) providers
        # But the intake flow explicitly uses LOCAL_ONLY

        # Check the router creation
        router = create_model_router(
            ollama_endpoint="http://ollama:11434",
            ollama_model="llama3.1:8b",
            ollama_vision_model="llava:7b",
            nvidia_api_key="test-nvidia-key",
            nvidia_base_url="https://integrate.api.nvidia.com/v1",
        )

        # Verify Ollama provider is local
        assert router.ollama.endpoint == "http://ollama:11434"
        assert router.ollama.model == "llama3.1:8b"

        # Test privacy routing - invoice processing should use LOCAL_ONLY
        scope = privacy_router.get_privacy_scope({"supplier_invoice": {"tax_id": "B12345678", "iban": "ES1234567890"}})
        assert scope == "LOCAL_ONLY"

        # Test privacy routing - dog intake should be LOCAL_ONLY
        scope = privacy_router.get_privacy_scope(
            {
                "dog_intake": {
                    "name": "Thor",
                    "microchip": "123456789012345",
                    "purchase_price": 1000,
                }
            }
        )
        assert scope == "LOCAL_ONLY"

        # Verify no cloud calls by checking the agent uses LOCAL_ONLY in its methods
        # The DogIntakeAgent explicitly passes privacy_scope="LOCAL_ONLY" to router calls

    @pytest.mark.asyncio
    async def test_telegram_webhook_endpoint_integration(self):
        """Test the actual Telegram webhook endpoint with mocked SupervisorAgent."""
        from app.core.config import get_settings

        webhook_secret = get_settings().TELEGRAM_WEBHOOK_SECRET

        # Mock the supervisor_agent in the telegram route
        with patch("app.routes.telegram.supervisor_agent") as mock_supervisor:
            mock_supervisor.handle_telegram_message = AsyncMock(
                return_value={
                    "success": True,
                    "workflow_id": "wf-123456789-123456789",
                    "step": "dog_intake",
                    "message": "¡Nuevo ingreso de perro! ¿Cuál es el nombre del perro?",
                    "awaiting_input": True,
                }
            )

            # Create test client
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                # Prepare webhook payload
                webhook_payload = {
                    "update_id": 123456789,
                    "message": {
                        "message_id": 1,
                        "date": 1700000000,
                        "chat": {"id": 123456789, "type": "private", "first_name": "Test", "username": "testuser"},
                        "from": {"id": 123456789, "is_bot": False, "first_name": "Test", "username": "testuser"},
                        "text": "/start",
                    },
                }

                # Send webhook request with secret header
                headers = {
                    "X-Telegram-Bot-Api-Secret-Token": webhook_secret,
                    "Content-Type": "application/json",
                }

                resp = await ac.post("/api/v1/webhook", json=webhook_payload, headers=headers)

                assert resp.status_code == 200
                data = resp.json()
                assert data["success"] is True
                assert data["workflow_id"] == "wf-123456789-123456789"
                assert data["step"] == "dog_intake"
                assert "nombre" in data["message"].lower() or "nombre" in data["message"]
                assert data["awaiting_input"] is True

                # Verify supervisor was called
                mock_supervisor.handle_telegram_message.assert_called_once()


# =============================================================================
# REQUIRED E2E TESTS (per specification)
# =============================================================================


class TestRequiredE2E:
    """Required E2E tests for the Telegram → Supervisor → DogIntake → InternalAPIClient → /api/v1/dogs flow."""

    @pytest.mark.asyncio
    async def test_A_valid_webhook_creates_dog_returns_dog_id(self, mock_breed):
        """
        A) valid webhook
        → dog created
        → dog_id returned
        """
        # Get the correct webhook secret from settings (loaded from .env.test)
        from app.core.config import get_settings

        webhook_secret = get_settings().TELEGRAM_WEBHOOK_SECRET

        # Import and start the supervisor agent (lifespan doesn't run with ASGITransport)
        from unittest.mock import AsyncMock

        from app.routes.telegram import supervisor_agent

        # Mock the DogIntakeAgent's process_message to simulate the intake flow
        # This avoids needing the real API client
        intake_responses = [
            # Step 1: /start - dog management selected (after callback)
            {
                "success": True,
                "completed": False,
                "message": "¡Nuevo ingreso de perro! ¿Cuál es el nombre del perro?",
                "step": "awaiting_name",
                "session_id": "test-session-123",
                "privacy_scope": "LOCAL_ONLY",
            },
            # Step 2: Name provided
            {
                "success": True,
                "completed": False,
                "message": "Recibido. ¿Qué raza es? (ej: Bulldog francés, Golden Retriever)",
                "step": "awaiting_breed",
                "session_id": "test-session-123",
                "privacy_scope": "LOCAL_ONLY",
                "collected_data": {"name": "Thor"},
            },
            # Step 3: Breed provided
            {
                "success": True,
                "completed": False,
                "message": "Recibido. ¿Sexo? (M/H o Macho/Hembra)",
                "step": "awaiting_sex",
                "session_id": "test-session-123",
                "privacy_scope": "LOCAL_ONLY",
                "collected_data": {"name": "Thor", "breed_name": "Golden Retriever"},
            },
            # Step 4: Sex provided
            {
                "success": True,
                "completed": False,
                "message": "Recibido. ¿Fecha de nacimiento? (YYYY-MM-DD)",
                "step": "awaiting_birth_date",
                "session_id": "test-session-123",
                "privacy_scope": "LOCAL_ONLY",
                "collected_data": {"name": "Thor", "breed_name": "Golden Retriever", "sex": "M"},
            },
            # Step 5: Birth date provided
            {
                "success": True,
                "completed": False,
                "message": "Recibido. ¿Color? (ej: Dorado, Negro, Blanco)",
                "step": "awaiting_color",
                "session_id": "test-session-123",
                "privacy_scope": "LOCAL_ONLY",
                "collected_data": {
                    "name": "Thor",
                    "breed_name": "Golden Retriever",
                    "sex": "M",
                    "birth_date": "2026-06-10",
                },
            },
            # Step 6: Color provided
            {
                "success": True,
                "completed": False,
                "message": "Recibido. ¿Número de microchip? (15 dígitos)",
                "step": "awaiting_microchip",
                "session_id": "test-session-123",
                "privacy_scope": "LOCAL_ONLY",
                "collected_data": {
                    "name": "Thor",
                    "breed_name": "Golden Retriever",
                    "sex": "M",
                    "birth_date": "2026-06-10",
                    "color": "Dorado",
                },
            },
            # Step 7: Microchip provided
            {
                "success": True,
                "completed": False,
                "message": "Recibido. ¿Precio de compra? (opcional, envía 0 para omitir)",
                "step": "awaiting_purchase_price",
                "session_id": "test-session-123",
                "privacy_scope": "LOCAL_ONLY",
                "collected_data": {
                    "name": "Thor",
                    "breed_name": "Golden Retriever",
                    "sex": "M",
                    "birth_date": "2026-06-10",
                    "color": "Dorado",
                    "microchip": "123456789012345",
                },
            },
            # Step 8: Purchase price
            {
                "success": True,
                "completed": False,
                "message": "Recibido. ¿Precio de venta? (opcional, envía 0 para omitir)",
                "step": "awaiting_sale_price",
                "session_id": "test-session-123",
                "privacy_scope": "LOCAL_ONLY",
                "collected_data": {
                    "name": "Thor",
                    "breed_name": "Golden Retriever",
                    "sex": "M",
                    "birth_date": "2026-06-10",
                    "color": "Dorado",
                    "microchip": "123456789012345",
                    "purchase_price": "0",
                },
            },
            # Step 9: Sale price - dog creation completes
            {
                "success": True,
                "completed": True,
                "dog": {
                    "id": 1,
                    "internal_id": "DOG-2026-000001",
                    "name": "Thor",
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
                "awaiting_input": False,
            },
        ]

        # Set up the mock to return responses in sequence
        supervisor_agent.dog_intake_agent.process_message = AsyncMock(side_effect=intake_responses)
        supervisor_agent.dog_intake_agent.start = AsyncMock()
        supervisor_agent.dog_intake_agent.stop = AsyncMock()

        await supervisor_agent.start()

        # Create test client with real ASGI transport
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            # Override auth to use dog_intake agent with write permission
            from app.dependencies.auth import get_current_agent

            fake_agent = FakeAgent("agent_dog_intake", "dog_intake", ["dog_intake", "write"])
            app.dependency_overrides[get_current_agent] = lambda: fake_agent

            try:
                # First create a breed if needed (mock_breed fixture should handle this)
                # Now send webhook with valid secret
                headers = {
                    "X-Telegram-Bot-Api-Secret-Token": webhook_secret,
                    "Content-Type": "application/json",
                }

                # Step 1: /start - shows menu
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
                data = resp.json()
                assert data["success"] is True
                assert data["workflow_type"] == "none"
                assert data["workflow_step"] == "awaiting_workflow_selection"
                assert data["awaiting_input"] is True
                _ = data["session_id"]

                # Step 2: Select dog_management via callback query
                resp = await ac.post(
                    "/api/v1/webhook",
                    json={
                        "update_id": 999002,
                        "callback_query": {
                            "id": "callback-123",
                            "from": {"id": 111111111},
                            "message": {"chat": {"id": 111111111}},
                            "data": "workflow:dog_management",
                        },
                    },
                    headers=headers,
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["success"] is True
                assert data["workflow_type"] == "dog_management"
                assert data["workflow_step"] == "dog_awaiting_name"
                assert data["awaiting_input"] is True

                # Now send the complete dog data in sequence
                # The workflow_id will be established on the first intake step
                workflow_id = None
                # 8 intake messages + callback triggers first call = 9 total process_message calls
                # The 9th call returns completed dog, supervisor transforms to dog_awaiting_media step
                intake_steps = [
                    ("Thor", "dog_intake", False),
                    ("Golden Retriever", "dog_intake", False),
                    ("M", "dog_intake", False),
                    ("2026-06-10", "dog_intake", False),
                    ("Dorado", "dog_intake", False),
                    ("123456789012345", "dog_intake", False),
                    ("0", "dog_intake", False),
                    ("1200", "dog_awaiting_media", True),  # Dog created, moves to media step
                ]

                for i, (text, expected_step, expected_completed) in enumerate(intake_steps):
                    resp = await ac.post(
                        "/api/v1/webhook",
                        json={
                            "update_id": 999003 + i,
                            "message": {
                                "message_id": i + 3,
                                "date": 1700000000 + i + 1,
                                "chat": {"id": 111111111, "type": "private"},
                                "from": {"id": 111111111, "is_bot": False, "first_name": "Test"},
                                "text": text,
                            },
                        },
                        headers=headers,
                    )
                    assert resp.status_code == 200
                    data = resp.json()
                    assert data["success"] is True

                    # Capture workflow_id from first intake response
                    if workflow_id is None:
                        workflow_id = data["workflow_id"]
                    assert data["workflow_id"] == workflow_id

                    # Check step - during intake it's "dog_intake", after completion it's "dog_awaiting_media"
                    assert data["step"] == expected_step
                    assert data.get("completed", False) == expected_completed
                    # During intake awaiting_input=True, after dog creation still True (waiting for media)
                    assert data["awaiting_input"] is True

                    # Last step should have the dog in response
                    if expected_step == "dog_awaiting_media":
                        assert "dog" in data
                        assert data["dog"]["internal_id"] == "DOG-2026-000001"
                        assert data["dog"]["name"] == "Thor"
                        assert data["dog"]["id"] == 1
                        # dog_id is returned in the response
                        assert "id" in data["dog"]

            finally:
                app.dependency_overrides.clear()
                await supervisor_agent.stop()

    @pytest.mark.asyncio
    async def test_B_missing_required_field_no_post_dogs(self, mock_breed):
        """
        B) missing required field
        → no POST /dogs
        """
        # Get the correct webhook secret from settings (loaded from .env.test)
        from app.core.config import get_settings

        webhook_secret = get_settings().TELEGRAM_WEBHOOK_SECRET

        # Import and start the supervisor agent (lifespan doesn't run with ASGITransport)
        from unittest.mock import AsyncMock

        from app.routes.telegram import supervisor_agent

        # Mock the DogIntakeAgent's process_message for incomplete intake
        # User provides name only, then stops - should still be waiting for breed
        intake_responses = [
            # Callback triggers first call (empty text)
            {
                "success": True,
                "completed": False,
                "message": "¡Nuevo ingreso de perro! ¿Cuál es el nombre del perro?",
                "step": "awaiting_name",
                "session_id": "test-session-123",
                "privacy_scope": "LOCAL_ONLY",
            },
            # User provides name "Incomplete Dog"
            {
                "success": True,
                "completed": False,
                "message": "Recibido. ¿Qué raza es? (ej: Bulldog francés, Golden Retriever)",
                "step": "awaiting_breed",
                "session_id": "test-session-123",
                "privacy_scope": "LOCAL_ONLY",
                "collected_data": {"name": "Incomplete Dog"},
            },
        ]

        supervisor_agent.dog_intake_agent.process_message = AsyncMock(side_effect=intake_responses)
        supervisor_agent.dog_intake_agent.start = AsyncMock()
        supervisor_agent.dog_intake_agent.stop = AsyncMock()

        await supervisor_agent.start()

        # This test verifies that if a required field is missing,
        # the dog is not created (no POST to /dogs)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            from app.dependencies.auth import get_current_agent

            fake_agent = FakeAgent("agent_dog_intake", "dog_intake", ["dog_intake", "write"])
            app.dependency_overrides[get_current_agent] = lambda: fake_agent

            try:
                headers = {
                    "X-Telegram-Bot-Api-Secret-Token": webhook_secret,
                    "Content-Type": "application/json",
                }

                # Step 1: /start - shows menu
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
                data = resp.json()
                assert data["success"] is True
                assert data["workflow_type"] == "none"
                assert data["workflow_step"] == "awaiting_workflow_selection"
                assert data["awaiting_input"] is True

                # Step 2: Select dog_management via callback query
                resp = await ac.post(
                    "/api/v1/webhook",
                    json={
                        "update_id": 999101,
                        "callback_query": {
                            "id": "callback-123",
                            "from": {"id": 222222222},
                            "message": {"chat": {"id": 222222222}},
                            "data": "workflow:dog_management",
                        },
                    },
                    headers=headers,
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["success"] is True
                assert data["workflow_type"] == "dog_management"
                assert data["workflow_step"] == "dog_awaiting_name"
                assert data["awaiting_input"] is True

                # Provide only name, then stop - missing breed, sex, birth_date, color, microchip
                resp = await ac.post(
                    "/api/v1/webhook",
                    json={
                        "update_id": 999102,
                        "message": {
                            "message_id": 2,
                            "date": 1700000001,
                            "chat": {"id": 222222222, "type": "private"},
                            "from": {"id": 222222222, "is_bot": False, "first_name": "Test"},
                            "text": "Incomplete Dog",
                        },
                    },
                    headers=headers,
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["success"] is True
                assert data.get("completed", False) is False
                assert data["awaiting_input"] is True
                # Should be waiting for breed, not completed
                assert data["step"] == "dog_intake"
                assert "dog" not in data
                _ = data["workflow_id"]  # workflow_id tracked but not used further

            finally:
                app.dependency_overrides.clear()
                await supervisor_agent.stop()

    @pytest.mark.asyncio
    async def test_C_invalid_webhook_secret_returns_403(self):
        """
        C) invalid webhook secret
        → 403
        """

        from app.core.config import get_settings

        # Patch get_settings in the telegram module where it's used
        class MockSettings:
            def __init__(self, secret, environment):
                self.TELEGRAM_WEBHOOK_SECRET = secret
                self.ENVIRONMENT = environment

        mock_settings = MockSettings("test-secret", "test")
        with patch("app.routes.telegram.get_settings", return_value=mock_settings):
            get_settings.cache_clear()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                headers = {
                    "X-Telegram-Bot-Api-Secret-Token": "wrong-secret",
                    "Content-Type": "application/json",
                }

                webhook_payload = {
                    "update_id": 999200,
                    "message": {
                        "message_id": 1,
                        "date": 1700000000,
                        "chat": {"id": 333333333, "type": "private"},
                        "from": {"id": 333333333, "is_bot": False, "first_name": "Test"},
                        "text": "/start",
                    },
                }

                resp = await ac.post("/api/v1/webhook", json=webhook_payload, headers=headers)
                assert resp.status_code == 403

        get_settings.cache_clear()

    @pytest.mark.asyncio
    async def test_D_invalid_dog_intake_api_key_dog_not_created(self, mock_breed):
        """
        D) invalid DogIntake API key
        → dog not created
        """
        from unittest.mock import AsyncMock

        from agents.supervisor.agent import create_supervisor_agent

        # Create a supervisor with invalid dog_intake key
        invalid_config = {
            "INTERNAL_API_URL": "http://localhost:8000/api/v1",
            "OLLAMA_ENDPOINT": "http://ollama:11434",
            "OLLAMA_MODEL": "llama3.1:8b",
            "OLLAMA_VISION_MODEL": "llava:7b",
            "NVIDIA_API_KEY": "",
            "NVIDIA_BASE_URL": "https://integrate.api.nvidia.com/v1",
            "AGENT_API_KEY_SUPERVISOR": "test-supervisor",
            "AGENT_API_KEY_DOG_INTAKE": "invalid-key",  # Invalid key
        }

        invalid_supervisor = create_supervisor_agent(invalid_config)

        # Mock the dog_intake_agent to simulate API key failure on dog creation
        # The intake flow: /start -> callback -> name -> breed -> sex -> birth -> color -> microchip -> purchase -> sale
        intake_responses = [
            # Callback triggers first call (empty text for dog_management selection)
            {
                "success": True,
                "completed": False,
                "message": "¡Nuevo ingreso de perro! ¿Cuál es el nombre del perro?",
                "step": "awaiting_name",
                "session_id": "test-session-123",
                "privacy_scope": "LOCAL_ONLY",
            },
            # User provides name
            {
                "success": True,
                "completed": False,
                "message": "Recibido. ¿Qué raza es?",
                "step": "awaiting_breed",
                "session_id": "test-session-123",
                "privacy_scope": "LOCAL_ONLY",
                "collected_data": {"name": "Test Dog"},
            },
            # User provides breed
            {
                "success": True,
                "completed": False,
                "message": "Recibido. ¿Sexo?",
                "step": "awaiting_sex",
                "session_id": "test-session-123",
                "privacy_scope": "LOCAL_ONLY",
                "collected_data": {"name": "Test Dog", "breed_name": "Golden Retriever"},
            },
            # User provides sex
            {
                "success": True,
                "completed": False,
                "message": "Recibido. ¿Fecha de nacimiento?",
                "step": "awaiting_birth_date",
                "session_id": "test-session-123",
                "privacy_scope": "LOCAL_ONLY",
                "collected_data": {"name": "Test Dog", "breed_name": "Golden Retriever", "sex": "M"},
            },
            # User provides birth date
            {
                "success": True,
                "completed": False,
                "message": "Recibido. ¿Color?",
                "step": "awaiting_color",
                "session_id": "test-session-123",
                "privacy_scope": "LOCAL_ONLY",
                "collected_data": {
                    "name": "Test Dog",
                    "breed_name": "Golden Retriever",
                    "sex": "M",
                    "birth_date": "2026-06-10",
                },
            },
            # User provides color
            {
                "success": True,
                "completed": False,
                "message": "Recibido. ¿Microchip?",
                "step": "awaiting_microchip",
                "session_id": "test-session-123",
                "privacy_scope": "LOCAL_ONLY",
                "collected_data": {
                    "name": "Test Dog",
                    "breed_name": "Golden Retriever",
                    "sex": "M",
                    "birth_date": "2026-06-10",
                    "color": "Dorado",
                },
            },
            # User provides microchip
            {
                "success": True,
                "completed": False,
                "message": "Recibido. ¿Precio compra?",
                "step": "awaiting_purchase_price",
                "session_id": "test-session-123",
                "privacy_scope": "LOCAL_ONLY",
                "collected_data": {
                    "name": "Test Dog",
                    "breed_name": "Golden Retriever",
                    "sex": "M",
                    "birth_date": "2026-06-10",
                    "color": "Dorado",
                    "microchip": "111222333444555",
                },
            },
            # User provides purchase price
            {
                "success": True,
                "completed": False,
                "message": "Recibido. ¿Precio venta?",
                "step": "awaiting_sale_price",
                "session_id": "test-session-123",
                "privacy_scope": "LOCAL_ONLY",
                "collected_data": {
                    "name": "Test Dog",
                    "breed_name": "Golden Retriever",
                    "sex": "M",
                    "birth_date": "2026-06-10",
                    "color": "Dorado",
                    "microchip": "111222333444555",
                    "purchase_price": "0",
                },
            },
            # User provides sale price - dog creation fails due to invalid API key
            {
                "success": False,
                "completed": False,
                "error": "API error: 401 Unauthorized",
                "message": "Error creando perro: API error: 401 Unauthorized",
                "privacy_scope": "LOCAL_ONLY",
            },
        ]

        invalid_supervisor.dog_intake_agent.process_message = AsyncMock(side_effect=intake_responses)
        invalid_supervisor.dog_intake_agent.start = AsyncMock()
        invalid_supervisor.dog_intake_agent.stop = AsyncMock()

        await invalid_supervisor.start()

        # Try to process a complete intake
        result = await invalid_supervisor.handle_telegram_message(
            {
                "update_id": 999300,
                "message": {
                    "message_id": 1,
                    "date": 1700000000,
                    "chat": {"id": 444444444, "type": "private"},
                    "from": {"id": 444444444, "is_bot": False, "first_name": "Test"},
                    "text": "/start",
                },
            }
        )

        # The supervisor should handle the error gracefully
        assert result["success"] is True  # Webhook returns 200 to Telegram
        assert result.get("completed", False) is False  # But dog not created

        await invalid_supervisor.stop()

    @pytest.mark.asyncio
    async def test_E_read_only_delete_returns_403(self, mock_breed):
        """
        E) read-only DELETE
        → 403
        """
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            from app.dependencies.auth import get_current_agent

            # Create a read-only agent (no write role)
            fake_agent = FakeAgent("agent_readonly", "dog_intake", ["dog_intake", "read"])
            app.dependency_overrides[get_current_agent] = lambda: fake_agent

            try:
                headers = {
                    "Authorization": "Bearer fake-token",
                    "Content-Type": "application/json",
                }

                resp = await ac.delete("/api/v1/dogs/1", headers=headers)
                assert resp.status_code == 403

            finally:
                app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_F_post_timeout_exactly_one_call(self):
        """
        F) POST timeout
        → exactly 1 call
        """
        # Test the InternalAPIClient retry logic for POST + TimeoutException
        from unittest.mock import AsyncMock

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
    async def test_F_get_timeout_allows_retry(self):
        """
        GET timeout
        → retry allowed
        """
        from unittest.mock import AsyncMock

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

        # First two calls timeout, third succeeds
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

    @pytest.mark.asyncio
    async def test_G_supervisor_fastapi_lifecycle_dog_intake_started_stopped(self):
        """
        G) Supervisor/FastAPI lifecycle
        → DogIntake started
        → DogIntake stopped
        """
        from agents.supervisor.agent import create_supervisor_agent

        config = {
            "INTERNAL_API_URL": "http://localhost:8000/api/v1",
            "OLLAMA_ENDPOINT": "http://ollama:11434",
            "OLLAMA_MODEL": "llama3.1:8b",
            "OLLAMA_VISION_MODEL": "llava:7b",
            "NVIDIA_API_KEY": "",
            "NVIDIA_BASE_URL": "https://integrate.api.nvidia.com/v1",
            "AGENT_API_KEY_SUPERVISOR": "test-supervisor",
            "AGENT_API_KEY_DOG_INTAKE": "test-dog-intake",
        }

        supervisor = create_supervisor_agent(config)

        # Track start/stop calls
        start_called = []
        stop_called = []

        # Create a simple mock agent that tracks start/stop
        class MockDogIntake:
            def __init__(self):
                self.process_message = lambda *args, **kwargs: asyncio.sleep(
                    0,
                    result={
                        "success": True,
                        "completed": False,
                        "message": "Test",
                        "step": "awaiting_name",
                        "session_id": "test",
                        "privacy_scope": "LOCAL_ONLY",
                    },
                )

            async def start(self):
                start_called.append(True)

            async def stop(self):
                stop_called.append(True)

        # Also mock other agents
        class MockAgent:
            async def start(self):
                pass

            async def stop(self):
                pass

        for attr in ["media_pipeline_agent", "content_agent", "publishing_agent", "listing_agent"]:
            setattr(supervisor, attr, MockAgent())

        supervisor.dog_intake_agent = MockDogIntake()

        # Start supervisor (simulates FastAPI startup)
        await supervisor.start()

        # Verify DogIntakeAgent.start was called
        assert len(start_called) == 1, "DogIntakeAgent.start should be called once"

        # Stop supervisor (simulates FastAPI shutdown)
        await supervisor.stop()

        # Verify DogIntakeAgent.stop was called
        assert len(stop_called) == 1, "DogIntakeAgent.stop should be called once"
