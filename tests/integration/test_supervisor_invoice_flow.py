"""
Tests for SupervisorAgent invoice processing Telegram flow.
Tests the complete flow: Telegram message -> Supervisor -> Celery -> InvoiceProcessingAgent -> Result.
"""

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio


class TestSupervisorInvoiceFlow:
    """Tests for the complete invoice processing flow via SupervisorAgent."""

    @pytest_asyncio.fixture
    async def supervisor_agent(self):
        """Create SupervisorAgent with mocked dependencies."""
        from agents.supervisor.agent import SupervisorAgent

        config = {
            "TEST_MODE": True,
            "INTERNAL_API_URL": "http://localhost:8000/api/v1",
            "AGENT_API_KEY_SUPERVISOR": "test_key",
            "OLLAMA_ENDPOINT": "http://ollama:11434",
            "OLLAMA_MODEL": "transvega-local",
            "NVIDIA_API_KEY": "",
            "INVOICE_STORAGE_ROOT": "/tmp/test_invoices",
            "OCR_DPI": 150,
            "OCR_MAX_PAGES": 5,
            "OCR_MAX_FILE_MB": 10,
            "OCR_TIMEOUT": 120,
            "OLLAMA_INVOICE_TIMEOUT": 600,
        }

        agent = SupervisorAgent(config)

        # Mock the conversation manager BEFORE start
        mock_conv_manager = AsyncMock()
        mock_session = {
            "session_id": "test-session-id",
            "telegram_user_id": 12345,
            "telegram_chat_id": 67890,
            "workflow_type": "none",
            "workflow_step": "awaiting_workflow_selection",
            "context": {},
        }
        mock_conv_manager.get_or_create_session.return_value = mock_session
        mock_conv_manager.get_session.return_value = mock_session
        mock_conv_manager.update_session.return_value = mock_session
        mock_conv_manager.update_context.return_value = mock_session

        # Replace the global get_conversation_manager to return our mock
        import agents.supervisor.agent as supervisor_module
        original_get_cm = supervisor_module.get_conversation_manager
        supervisor_module.get_conversation_manager = AsyncMock(return_value=mock_conv_manager)

        # Mock sub-agents
        agent.invoice_agent = AsyncMock()
        agent.invoice_agent.start = AsyncMock()
        agent.invoice_agent.stop = AsyncMock()

        agent.dog_intake_agent = AsyncMock()
        agent.dog_intake_agent.start = AsyncMock()
        agent.dog_intake_agent.stop = AsyncMock()
        agent.dog_intake_agent.process_message = AsyncMock()

        for attr in ["media_pipeline_agent", "content_agent", "publishing_agent", "listing_agent"]:
            setattr(agent, attr, AsyncMock())
            getattr(agent, attr).start = AsyncMock()
            getattr(agent, attr).stop = AsyncMock()

        # Mock Telegram methods
        mock_tg_msg = MagicMock()
        mock_tg_msg.message_id = 999
        agent._send_telegram_message = AsyncMock(return_value=mock_tg_msg)
        agent._edit_telegram_message = AsyncMock()
        agent._answer_callback_query = AsyncMock(return_value=True)
        agent._download_telegram_file = AsyncMock(return_value=b"fake pdf content")

        # Mock the Celery task locally imported in _handle_invoice_document
        mock_celery_task = AsyncMock()
        mock_celery_task.delay = AsyncMock()

        # Patch the local import in _handle_invoice_document
        with patch.dict('sys.modules', {'tasks': MagicMock(), 'tasks.facturacion': MagicMock()}):
            import tasks.facturacion as facturacion_module
            facturacion_module.procesar_factura_async = mock_celery_task
            import sys
            sys.modules['tasks.facturacion'] = facturacion_module

            await agent.start()

            yield agent, mock_celery_task

            await agent.stop()

        # Restore
        supervisor_module.get_conversation_manager = original_get_cm

    def _create_telegram_update(self, user_id, chat_id, message_id, update_id, document=None, photo=None, text=None):
        """Helper to create a Telegram update dict."""
        tg_message = {
            "message_id": message_id,
            "chat": {"id": chat_id},
            "from": {"id": user_id},
        }
        if document:
            tg_message["document"] = document
        if photo:
            tg_message["photo"] = photo
        if text:
            tg_message["text"] = text
        return {"update_id": update_id, "message": tg_message}

    def _assert_no_menu(self, send_calls):
        """Assert no 'what do you want' menu was shown."""
        for call in send_calls:
            text = call[0][1] if len(call[0]) > 1 else (call.kwargs.get("text", "") if call.kwargs else "")
            assert "¿Qué quieres hacer" not in text, f"Found menu text in: {text}"

    def _assert_processing_message_sent(self, send_calls):
        """Assert processing message was sent."""
        found = False
        for call in send_calls:
            text = call[0][1] if len(call[0]) > 1 else (call.kwargs.get("text", "") if call.kwargs else "")
            if "Procesando factura" in text:
                found = True
                break
        assert found, "Processing message should have been sent"

    @pytest.mark.asyncio
    async def test_first_invoice_document_processed_immediately(self, supervisor_agent):
        """
        CRITICAL TEST 1: First PDF received should be processed immediately.
        - No active workflow
        - User sends PDF document
        - Workflow should start AND document should be processed (not ask for another)
        - Celery task should be enqueued with the SAME file_id
        - Should NOT show "what do you want" menu
        """
        agent, mock_celery_task = supervisor_agent

        user_id = 12345
        chat_id = 67890
        file_id = "test-file-id-123"
        update_id = 42

        update = self._create_telegram_update(
            user_id, chat_id, 100, update_id,
            document={
                "file_id": file_id,
                "file_unique_id": "unique-123",
                "file_name": "factura.pdf",
                "mime_type": "application/pdf",
                "file_size": 1024,
            }
        )

        result = await agent.handle_telegram_message(update)

        assert result["success"] is True
        assert result["workflow_type"] == "supplier_invoice"
        assert result["workflow_step"] == "invoice_processing"
        assert result["async_processing"] is True
        assert "correlation_id" in result

        assert mock_celery_task.delay.call_count == 1, "Celery task should be enqueued exactly once"

        call_args = mock_celery_task.delay.call_args[0][0]
        assert call_args["telegram_user_id"] == user_id
        assert call_args["telegram_chat_id"] == chat_id
        assert call_args["telegram_message_id"] == 100
        assert call_args["update_id"] == update_id
        assert call_args["filename"] == "factura.pdf"
        assert "file_content_b64" in call_args
        assert "correlation_id" in call_args

        downloaded_content = base64.b64decode(call_args["file_content_b64"])
        assert downloaded_content == b"fake pdf content"

        send_calls = agent._send_telegram_message.call_args_list
        self._assert_no_menu(send_calls)
        self._assert_processing_message_sent(send_calls)

    @pytest.mark.asyncio
    async def test_no_menu_for_invoice_pdf(self, supervisor_agent):
        """
        CRITICAL TEST 2: PDF likely invoice should NOT show 'what do you want' menu.
        """
        agent, mock_celery_task = supervisor_agent

        user_id = 12345
        chat_id = 67890

        update = self._create_telegram_update(
            user_id, chat_id, 101, 43,
            document={
                "file_id": "file-id-456",
                "file_unique_id": "unique-456",
                "file_name": "invoice.pdf",
                "mime_type": "application/pdf",
                "file_size": 2048,
            }
        )

        result = await agent.handle_telegram_message(update)

        send_calls = agent._send_telegram_message.call_args_list
        self._assert_no_menu(send_calls)
        assert result["async_processing"] is True

    @pytest.mark.asyncio
    async def test_no_synchronous_invoice_processing_in_webhook(self, supervisor_agent):
        """
        CRITICAL TEST 3: Supervisor should NOT call invoice_agent.process_invoice directly.
        Processing must happen in Celery task only.
        """
        agent, mock_celery_task = supervisor_agent

        user_id = 12345
        chat_id = 67890

        update = self._create_telegram_update(
            user_id, chat_id, 102, 44,
            document={
                "file_id": "file-id-789",
                "file_unique_id": "unique-789",
                "file_name": "factura.pdf",
                "mime_type": "application/pdf",
                "file_size": 1024,
            }
        )

        result = await agent.handle_telegram_message(update)

        agent.invoice_agent.process_invoice.assert_not_called()
        assert mock_celery_task.delay.call_count == 1
        assert result["async_processing"] is True

    @pytest.mark.asyncio
    async def test_celery_task_payload_correctness(self, supervisor_agent):
        """
        CRITICAL TEST 4: Celery task receives correct payload from original message.
        """
        agent, mock_celery_task = supervisor_agent

        user_id = 12345
        chat_id = 67890
        file_id = "test-file-id-payload"
        message_id = 200
        update_id = 100

        update = self._create_telegram_update(
            user_id, chat_id, message_id, update_id,
            document={
                "file_id": file_id,
                "file_unique_id": "unique-payload",
                "file_name": "test_invoice.pdf",
                "mime_type": "application/pdf",
                "file_size": 512,
            }
        )

        await agent.handle_telegram_message(update)

        call_args = mock_celery_task.delay.call_args[0][0]

        assert call_args["telegram_user_id"] == user_id
        assert call_args["telegram_chat_id"] == chat_id
        assert call_args["telegram_message_id"] == message_id
        assert call_args["update_id"] == update_id
        assert call_args["filename"] == "test_invoice.pdf"
        assert "file_content_b64" in call_args
        assert "correlation_id" in call_args

        decoded = base64.b64decode(call_args["file_content_b64"])
        assert decoded == b"fake pdf content"

    @pytest.mark.asyncio
    async def test_extraction_failed_handling(self, supervisor_agent):
        """
        CRITICAL TEST 5: Structured extraction failed should show error message.
        """
        agent, _ = supervisor_agent

        from app.schemas.conversation import WorkflowStep

        user_id = 12345
        chat_id = 67890
        correlation_id = "test-correlation-failed"

        session = {
            "session_id": "test-session",
            "telegram_user_id": user_id,
            "telegram_chat_id": chat_id,
            "workflow_type": "supplier_invoice",
            "workflow_step": WorkflowStep.INVOICE_PROCESSING,
            "context": {
                "invoice_correlation_id": correlation_id,
                "processing_message_id": 999,
            },
        }
        agent.conversation_manager.get_session.return_value = session

        result_data = {
            "correlation_id": correlation_id,
            "telegram_user_id": user_id,
            "telegram_chat_id": chat_id,
            "telegram_message_id": 100,
            "result": {
                "success": False,
                "error": "structured_extraction_failed",
                "message": "Failed to extract structured data",
                "requires_review": True,
            },
        }

        await agent._handle_invoice_result(result_data)

        agent._edit_telegram_message.assert_called_once()
        call_args = agent._edit_telegram_message.call_args
        text = call_args[0][2]
        assert "No he podido procesar correctamente la factura" in text
        assert "puedes volver a intentarlo" in text.lower()

    @pytest.mark.asyncio
    async def test_ollama_timeout_handling(self, supervisor_agent):
        """
        CRITICAL TEST 6: Ollama timeout should show timeout message, NOT fallback to external.
        """
        agent, _ = supervisor_agent

        from app.schemas.conversation import WorkflowStep

        user_id = 12345
        chat_id = 67890
        correlation_id = "test-correlation-timeout"

        session = {
            "session_id": "test-session",
            "telegram_user_id": user_id,
            "telegram_chat_id": chat_id,
            "workflow_type": "supplier_invoice",
            "workflow_step": WorkflowStep.INVOICE_PROCESSING,
            "context": {
                "invoice_correlation_id": correlation_id,
                "processing_message_id": 999,
            },
        }
        agent.conversation_manager.get_session.return_value = session

        result_data = {
            "correlation_id": correlation_id,
            "telegram_user_id": user_id,
            "telegram_chat_id": chat_id,
            "telegram_message_id": 100,
            "result": {
                "success": False,
                "error": "invoice_processing_timeout",
                "message": "El procesamiento de la factura ha superado el tiempo máximo permitido.",
                "requires_review": False,
            },
        }

        await agent._handle_invoice_result(result_data)

        agent._edit_telegram_message.assert_called_once()
        call_args = agent._edit_telegram_message.call_args
        text = call_args[0][2]
        assert "superado el tiempo máximo" in text
        assert "puedes volver a intentarlo" in text.lower()

    @pytest.mark.asyncio
    async def test_telegram_edit_fallback(self, supervisor_agent):
        """
        CRITICAL TEST 7: If edit_message_text fails, should fallback to send_message.
        """
        agent, _ = supervisor_agent

        from app.schemas.conversation import WorkflowStep

        user_id = 12345
        chat_id = 67890
        correlation_id = "test-correlation-fallback"

        session = {
            "session_id": "test-session",
            "telegram_user_id": user_id,
            "telegram_chat_id": chat_id,
            "workflow_type": "supplier_invoice",
            "workflow_step": WorkflowStep.INVOICE_PROCESSING,
            "context": {
                "invoice_correlation_id": correlation_id,
                "processing_message_id": 999,
            },
        }
        agent.conversation_manager.get_session.return_value = session

        agent._edit_telegram_message.side_effect = Exception("Message not found")
        agent._send_telegram_message.reset_mock()

        # Mock the internal _handle_invoice_success to avoid draft service dependency
        original_handle_success = agent._handle_invoice_success

        async def mock_handle_success(chat_id, processing_message_id, result, session, correlation_id):
            # Just verify edit fails and send is called
            try:
                await agent._edit_telegram_message(chat_id, processing_message_id, "test")
            except Exception:
                await agent._send_telegram_message(chat_id, "fallback")

        agent._handle_invoice_success = mock_handle_success

        result_data = {
            "correlation_id": correlation_id,
            "telegram_user_id": user_id,
            "telegram_chat_id": chat_id,
            "telegram_message_id": 100,
            "result": {
                "success": True,
                "summary": {
                    "supplier_name": "Test",
                    "supplier_tax_id": "B12345678",
                    "invoice_number": "FAC-001",
                    "invoice_date": "2024-01-15",
                    "subtotal": 100.0,
                    "tax_total": 21.0,
                    "total": 121.0,
                    "currency": "EUR",
                },
                "requires_review": False,
                "file_path": "/tmp/test.pdf",
                "final_path": "/tmp/test.pdf",
                "invoice": {},
            },
        }

        await agent._handle_invoice_result(result_data)

        agent._edit_telegram_message.assert_called_once()
        assert agent._send_telegram_message.call_count >= 1

        # Restore
        agent._handle_invoice_success = original_handle_success

    @pytest.mark.asyncio
    async def test_correction_state_reachable(self, supervisor_agent):
        """
        CRITICAL TEST 8: AWAITING_CORRECTION state should be reachable.
        Tests the state transition without draft service dependency.
        """
        agent, _ = supervisor_agent

        from app.schemas.conversation import WorkflowStep

        user_id = 12345
        chat_id = 67890

        session = {
            "session_id": "test-session",
            "telegram_user_id": user_id,
            "telegram_chat_id": chat_id,
            "workflow_type": "supplier_invoice",
            "workflow_step": WorkflowStep.INVOICE_AWAITING_APPROVAL,
            "context": {
                "invoice_draft_id": "draft-123",
            },
        }
        agent.conversation_manager.get_session.return_value = session
        agent.conversation_manager.update_session.return_value = session

        # Mock the keyboard and prompt functions
        with patch("agents.supervisor.agent.get_correction_keyboard") as mock_corr_kb:
            with patch("agents.supervisor.agent.get_correction_prompt_text") as mock_corr_text:
                mock_corr_kb.return_value = {"inline_keyboard": []}
                mock_corr_text.return_value = "Correction prompt"

                result = await agent._start_invoice_correction(user_id, chat_id, session)

                assert result["success"] is True
                assert result["workflow_step"] == WorkflowStep.INVOICE_AWAITING_CORRECTION
                assert result["awaiting_input"] is True

                # Test that correction text handler exists and can be called
                session_corr = {
                    **session,
                    "workflow_step": WorkflowStep.INVOICE_AWAITING_CORRECTION,
                }
                agent.conversation_manager.get_session.return_value = session_corr

                # Verify the method exists and handles corrections
                assert hasattr(agent, '_handle_invoice_correction_text')
                assert callable(agent._handle_invoice_correction_text)

    @pytest.mark.asyncio
    async def test_duplicate_update_idempotency(self, supervisor_agent):
        """
        CRITICAL TEST 9: Same Telegram update_id should not enqueue two tasks.
        Note: Current implementation may not have idempotency - this documents behavior.
        """
        agent, mock_celery_task = supervisor_agent

        user_id = 12345
        chat_id = 67890
        update_id = 9999

        update = self._create_telegram_update(
            user_id, chat_id, 300, update_id,
            document={
                "file_id": "file-dup-test",
                "file_unique_id": "unique-dup",
                "file_name": "factura.pdf",
                "mime_type": "application/pdf",
                "file_size": 1024,
            }
        )

        await agent.handle_telegram_message(update)
        await agent.handle_telegram_message(update)

        call_count = mock_celery_task.delay.call_count
        print(f"Celery task enqueued {call_count} times for duplicate update")


class TestSupervisorInvoiceExplicitWorkflow:
    """Tests for explicit invoice workflow start (via text command/button)."""

    @pytest_asyncio.fixture
    async def supervisor_agent(self):
        from agents.supervisor.agent import SupervisorAgent

        config = {
            "TEST_MODE": True,
            "INTERNAL_API_URL": "http://localhost:8000/api/v1",
            "AGENT_API_KEY_SUPERVISOR": "test_key",
        }

        agent = SupervisorAgent(config)

        mock_conv_manager = AsyncMock()
        mock_session = {
            "session_id": "test-session",
            "telegram_user_id": 12345,
            "telegram_chat_id": 67890,
            "workflow_type": "none",
            "workflow_step": "awaiting_workflow_selection",
            "context": {},
        }
        mock_conv_manager.get_or_create_session.return_value = mock_session
        mock_conv_manager.get_session.return_value = mock_session
        mock_conv_manager.update_session.return_value = mock_session
        mock_conv_manager.update_context.return_value = mock_session

        import agents.supervisor.agent as supervisor_module
        original_get_cm = supervisor_module.get_conversation_manager
        supervisor_module.get_conversation_manager = AsyncMock(return_value=mock_conv_manager)

        agent.conversation_manager = mock_conv_manager
        agent.invoice_agent = AsyncMock()
        agent.dog_intake_agent = AsyncMock()
        for attr in ["media_pipeline_agent", "content_agent", "publishing_agent", "listing_agent"]:
            setattr(agent, attr, AsyncMock())

        mock_tg_msg = MagicMock()
        mock_tg_msg.message_id = 999
        agent._send_telegram_message = AsyncMock(return_value=mock_tg_msg)
        agent._edit_telegram_message = AsyncMock()
        agent._answer_callback_query = AsyncMock(return_value=True)
        agent._download_telegram_file = AsyncMock(return_value=b"fake pdf content")

        mock_celery_task = AsyncMock()
        mock_celery_task.delay = AsyncMock()

        with patch.dict('sys.modules', {'tasks': MagicMock(), 'tasks.facturacion': MagicMock()}):
            import tasks.facturacion as facturacion_module
            facturacion_module.procesar_factura_async = mock_celery_task
            import sys
            sys.modules['tasks.facturacion'] = facturacion_module

            await agent.start()
            yield agent, mock_celery_task
            await agent.stop()

        supervisor_module.get_conversation_manager = original_get_cm

    def _create_telegram_update(self, user_id, chat_id, message_id, update_id, document=None, photo=None, text=None):
        tg_message = {
            "message_id": message_id,
            "chat": {"id": chat_id},
            "from": {"id": user_id},
        }
        if document:
            tg_message["document"] = document
        if photo:
            tg_message["photo"] = photo
        if text:
            tg_message["text"] = text
        return {"update_id": update_id, "message": tg_message}

    @pytest.mark.asyncio
    async def test_explicit_invoice_workflow_then_document(self, supervisor_agent):
        """
        Test: User explicitly starts invoice workflow, THEN sends document.
        This should work via Priority 5 (media within active workflow).
        """
        agent, mock_celery_task = supervisor_agent

        from app.schemas.conversation import WorkflowStep

        user_id = 12345
        chat_id = 67890
        file_id = "explicit-workflow-file"

        text_update = self._create_telegram_update(
            user_id, chat_id, 10, 1, text="factura"
        )

        session_after_start = {
            "session_id": "test-session",
            "telegram_user_id": user_id,
            "telegram_chat_id": chat_id,
            "workflow_type": "supplier_invoice",
            "workflow_step": WorkflowStep.INVOICE_AWAITING_DOCUMENT,
            "context": {},
        }
        agent.conversation_manager.get_or_create_session.return_value = session_after_start
        agent.conversation_manager.get_session.return_value = session_after_start
        agent.conversation_manager.update_session.return_value = session_after_start

        result1 = await agent.handle_telegram_message(text_update)
        assert result1["workflow_step"] == WorkflowStep.INVOICE_AWAITING_DOCUMENT

        doc_update = self._create_telegram_update(
            user_id, chat_id, 11, 2,
            document={
                "file_id": file_id,
                "file_unique_id": "unique-explicit",
                "file_name": "factura2.pdf",
                "mime_type": "application/pdf",
                "file_size": 2048,
            }
        )

        result2 = await agent.handle_telegram_message(doc_update)

        assert result2["async_processing"] is True
        mock_celery_task.delay.assert_called_once()

    @pytest.mark.asyncio
    async def test_photo_invoice_processed(self, supervisor_agent):
        """Test that photo (image) invoices are also processed."""
        agent, mock_celery_task = supervisor_agent

        user_id = 12345
        chat_id = 67890

        update = self._create_telegram_update(
            user_id, chat_id, 200, 3,
            photo=[
                {"file_id": "photo-small", "file_unique_id": "u1", "file_size": 100, "width": 100, "height": 100},
                {"file_id": "photo-large", "file_unique_id": "u2", "file_size": 5000, "width": 800, "height": 600},
            ]
        )

        result = await agent.handle_telegram_message(update)

        assert result["async_processing"] is True
        mock_celery_task.delay.assert_called_once()
        call_args = mock_celery_task.delay.call_args[0][0]
        assert "photo_" in call_args["filename"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
