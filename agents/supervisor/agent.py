"""
Supervisor Agent - Orchestrates the complete multi-agent pipeline.
Integrates: Telegram → Dog Intake → Media Pipeline → Content Marketing → Publishing
AND: Telegram → Invoice Processing → Dolibarr (Supplier Invoices)
"""

import asyncio
import re
import uuid
from datetime import datetime
from typing import Any

import httpx
import structlog

from agents.content_marketing.agent import create_content_marketing_agent
from agents.dog_intake.agent import DogIntakeAgent
from agents.invoice_processing.agent import create_invoice_processing_agent
from agents.listing.agent import create_listing_agent
from agents.media_pipeline.agent import create_media_pipeline_agent
from agents.publishing.agent import create_publishing_agent
from app.schemas.conversation import (
    WorkflowStep,
    WorkflowType,
    get_cancel_keyboard,
    get_correction_keyboard,
    get_correction_prompt_text,
    get_dog_management_keyboard,
    get_help_text,
    get_invoice_approval_keyboard,
    get_invoice_approval_text,
    get_main_menu_keyboard,
    get_supplier_not_found_keyboard,
    get_supplier_not_found_text,
    get_workflow_selection_text,
)
from app.services.conversation_manager import TelegramConversationManager, get_conversation_manager

logger = structlog.get_logger()


class SupervisorAgent:
    """
    Supervisor Agent - Central orchestrator for the multi-agent system.

    Pipelines:
    1. Telegram webhook → Dog Intake → Media Pipeline → Content → Publishing
    2. Telegram webhook → Invoice Processing → Dolibarr (Supplier Invoices)

    Responsibilities:
    - Route incoming Telegram messages to appropriate agent (DogIntake or InvoiceProcessing)
    - Coordinate media processing after dog creation
    - Trigger content generation for approved dogs
    - Manage publishing workflow with human approvals
    - Manage invoice processing workflow with human approvals
    - Handle errors and retries
    - Audit logging
    """

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.agent_id = "supervisor"
        self.agent_name = "Supervisor Agent"
        self.status = "idle"

        # Test mode: disable background tasks for testing
        self._test_mode = config.get("TEST_MODE", False)

        # Internal API client
        self.api_base = config.get("INTERNAL_API_URL", "http://localhost:8000/api/v1")
        self.api_client = httpx.AsyncClient(base_url=self.api_base, timeout=60.0)
        self.api_key = config.get("AGENT_API_KEY_SUPERVISOR", "")

        # Sub-agents - pass full config to DogIntakeAgent
        dog_intake_config = dict(config)
        dog_intake_config["INTERNAL_API_URL"] = self.api_base
        self.dog_intake_agent = DogIntakeAgent(dog_intake_config)

        # Invoice Processing Agent
        invoice_config = dict(config)
        invoice_config["INTERNAL_API_URL"] = self.api_base
        self.invoice_agent = create_invoice_processing_agent(invoice_config)

        self.media_pipeline_agent = create_media_pipeline_agent(config)
        self.content_agent = create_content_marketing_agent(config)
        self.publishing_agent = create_publishing_agent(config)
        self.listing_agent = create_listing_agent(config)

        # Conversation Manager (replaces in-memory active_workflows for Telegram)
        self.conversation_manager: TelegramConversationManager | None = None

        # Legacy in-memory workflows for NON-Telegram flows (media pipeline, content, publishing)
        # These are internal workflows not driven by Telegram conversation state
        self.active_workflows: dict[str, dict] = {}

        # Pending approvals for non-conversation flows
        self.pending_approvals: dict[str, dict] = {}

        self.capabilities = [
            "orchestrate_dog_intake",
            "orchestrate_media_pipeline",
            "orchestrate_content_generation",
            "orchestrate_publishing",
            "orchestrate_invoice_processing",
            "manage_approvals",
            "get_workflow_status",
            "retry_failed_step",
        ]
        self.restrictions = [
            "no_direct_db_access",
            "human_approval_required_for_publish",
            "human_approval_required_for_price_change",
            "human_approval_required_for_invoice",
        ]

        # Background tasks for monitoring/cleanup (disabled in test mode)
        self._monitor_task: asyncio.Task | None = None
        self._cleanup_task: asyncio.Task | None = None

    async def start(self):
        """Start the supervisor and sub-agents."""
        logger.info("starting_supervisor", agent_id=self.agent_id)
        self.status = "running"

        # Initialize Conversation Manager
        self.conversation_manager = await get_conversation_manager()

        # Start sub-agents
        await self.dog_intake_agent.start()
        await self.invoice_agent.start()
        await self.media_pipeline_agent.start()
        await self.content_agent.start()
        await self.publishing_agent.start()
        await self.listing_agent.start()

        # Start background tasks (skip in test mode)
        if not self._test_mode:
            self._monitor_task = asyncio.create_task(self._monitor_workflows())
            self._cleanup_task = asyncio.create_task(self._cleanup_completed_workflows())

        logger.info("supervisor_started")

    async def stop(self):
        """Stop the supervisor and close connections."""
        logger.info("stopping_supervisor")
        self.status = "stopped"

        # Cancel background tasks (skip in test mode)
        if not self._test_mode:
            for task in (self._monitor_task, self._cleanup_task):
                if task and not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

        await self.api_client.aclose()
        await self.invoice_agent.stop()
        await self.media_pipeline_agent.stop()
        await self.content_agent.stop()
        await self.publishing_agent.stop()
        await self.dog_intake_agent.stop()
        await self.listing_agent.stop()
        if self.conversation_manager:
            await self.conversation_manager.close()

    # =========================================================================
    # WORKFLOW ENTRY POINTS
    # =========================================================================

    def _detect_invoice_intent(self, tg_message: dict, text: str) -> bool:
        """
        Detect if the message should be processed as an invoice.

        Priority:
        1. Active invoice approval/correction workflow
        2. Explicit business action in caption/text
        3. Document/media that looks like an invoice
        """
        # Check if there's an active invoice approval/correction workflow for this user
        # This is handled separately in the main routing logic

        # Check caption/text for explicit invoice keywords
        caption = tg_message.get("caption", "").lower()
        text_lower = text.lower()

        invoice_keywords = [
            "factura",
            "factura proveedor",
            "gasto",
            "registrar factura",
            "procesar factura",
            "invoice",
            "supplier invoice",
            "expense",
        ]

        for keyword in invoice_keywords:
            if keyword in caption or keyword in text_lower:
                return True

        # Check if it's a document (PDF) - likely an invoice
        if "document" in tg_message:
            doc = tg_message["document"]
            mime_type = doc.get("mime_type", "").lower()
            if mime_type == "application/pdf":
                return True
            # Image documents could be invoices
            if mime_type.startswith("image/"):
                return True

        # Check if it's a photo - could be invoice photo
        if "photo" in tg_message:
            # If there's a caption suggesting invoice, or no active dog intake
            if caption or not self._has_active_dog_intake(tg_message):
                return True

        return False

    def _has_active_dog_intake(self, tg_message: dict) -> bool:
        """Check if there's an active dog intake workflow for this user."""
        user_id = tg_message.get("from", {}).get("id")
        chat_id = tg_message.get("chat", {}).get("id")
        if user_id and chat_id:
            workflow_id = f"wf-{chat_id}-{user_id}"
            workflow = self.active_workflows.get(workflow_id)
            if workflow and workflow.get("step") in [
                WorkflowStep.DOG_INTAKE,
                WorkflowStep.DOG_AWAITING_NAME,
                WorkflowStep.DOG_AWAITING_BREED,
                WorkflowStep.DOG_AWAITING_SEX,
                WorkflowStep.DOG_AWAITING_BIRTH_DATE,
                WorkflowStep.DOG_AWAITING_COLOR,
                WorkflowStep.DOG_AWAITING_MICROCHIP,
                WorkflowStep.DOG_AWAITING_PURCHASE_PRICE,
                WorkflowStep.DOG_AWAITING_SALE_PRICE,
                WorkflowStep.DOG_AWAITING_MEDIA,
            ]:
                return True
        return False

    def _is_approval_response(self, text: str) -> str | None:
        """Check if text is an approval/correction/cancellation response."""
        text_lower = text.lower().strip()
        if text_lower in ["aprobar", "aprobado", "apruebo", "sí", "si", "yes", "ok", "confirmar"]:
            return "approve"
        if text_lower in ["corregir", "corrección", "correccion", "cambiar", "modificar"]:
            return "correct"
        if text_lower in ["cancelar", "cancelado", "no", "cancel"]:
            return "cancel"
        return None

    def _parse_correction(self, text: str) -> dict[str, Any] | None:
        """Parse conversational corrections like 'El total son 125,40', 'Es combustible', etc."""
        text_lower = text.lower().strip()
        corrections = {}

        # Total amount correction
        total_match = re.search(r"total\s*(?:es|son|:)\s*([\d.,]+)", text_lower)
        if total_match:
            val = total_match.group(1).replace(".", "").replace(",", ".")
            try:
                corrections["total"] = float(val)
            except ValueError:
                pass

        # Subtotal correction
        subtotal_match = re.search(r"(?:subtotal|base)\s*(?:es|son|:)\s*([\d.,]+)", text_lower)
        if subtotal_match:
            val = subtotal_match.group(1).replace(".", "").replace(",", ".")
            try:
                corrections["subtotal"] = float(val)
            except ValueError:
                pass

        # VAT correction
        vat_match = re.search(r"(?:iva|vat)\s*(?:es|son|:)\s*([\d.,]+)", text_lower)
        if vat_match:
            val = vat_match.group(1).replace(".", "").replace(",", ".")
            try:
                corrections["tax_total"] = float(val)
            except ValueError:
                pass

        # VAT rate correction (e.g., "El IVA es 10%")
        vat_rate_match = re.search(r"(?:iva|vat)\s*(?:es|son|:)\s*(\d+)%", text_lower)
        if vat_rate_match:
            corrections["vat_rate"] = float(vat_rate_match.group(1))

        # Category correction
        category_keywords = {
            "veterinary": ["veterinario", "veterinaria", "vet"],
            "feed": ["pienso", "alimento", "comida", "feed"],
            "fuel": ["combustible", "gasolina", "diesel", "gasoil", "fuel"],
            "transport": ["transporte", "envío", "envio", "shipping"],
            "advertising": ["publicidad", "anuncio", "ads", "marketing"],
            "training": ["formación", "formacion", "curso", "entrenamiento", "training"],
            "office": ["oficina", "material", "office", "papeleria", "papelería"],
            "professional_services": ["profesional", "servicios", "asesor", "abogado", "contable"],
            "utilities": ["suministros", "luz", "agua", "gas", "electricidad", "utilities"],
            "pet_supplies": ["mascota", "perro", "gato", "pet", "accesorios"],
            "insurance": ["seguro", "insurance", "póliza", "poliza"],
            "rent": ["alquiler", "renta", "rent", "local"],
            "taxes_fees": ["tasas", "impuestos", "tax", "tasa"],
            "other": ["otros", "otro", "varios", "misc"],
        }

        for code, keywords in category_keywords.items():
            for kw in keywords:
                if kw in text_lower:
                    corrections["expense_category"] = code
                    break
            if "expense_category" in corrections:
                break

        # Supplier correction
        supplier_match = re.search(r"proveedor\s*(?:es|son|:)\s*(.+)", text_lower)
        if supplier_match:
            corrections["supplier_name"] = supplier_match.group(1).strip()

        # Invoice number correction
        invoice_num_match = re.search(r"(?:número|numero|factura)\s*(?:es|son|:)\s*([A-Za-z0-9\-]+)", text_lower)
        if invoice_num_match:
            corrections["invoice_number"] = invoice_num_match.group(1).strip()

        return corrections if corrections else None

    async def handle_telegram_message(self, message: dict) -> dict:
        """
        Entry point for Telegram webhook.
        Routes to appropriate agent based on message content and context.

        Priority (using ConversationManager for session state):
        1. Global commands: /start, /menu, /cancel, /status
        2. callback_query (inline button responses)
        3. Active workflow awaiting response (approval/correction)
        4. Pending clarification (supplier not found, etc.)
        5. Media within active workflow (invoice document/photo)
        6. Explicit workflow selection (button or text)
        7. Media without workflow → pending_media + ask clarification
        8. General intent detection / fallback
        """
        # Extract update type and message
        tg_message = message.get("message") or message.get("edited_message")
        callback_query = message.get("callback_query")

        if not tg_message and not callback_query:
            return {"success": False, "error": "No message or callback_query in update"}

        # Get chat_id and user_id from either message or callback_query
        if callback_query:
            chat_id = callback_query.get("message", {}).get("chat", {}).get("id")
            user_id = callback_query.get("from", {}).get("id")
            text = callback_query.get("data", "")  # callback_data
            update_id = message.get("update_id")
            is_callback = True
        else:
            chat_id = tg_message.get("chat", {}).get("id")
            user_id = tg_message.get("from", {}).get("id")
            text = tg_message.get("text", "") or tg_message.get("caption", "")
            update_id = message.get("update_id")
            is_callback = False

        if chat_id is None or user_id is None:
            return {"success": False, "error": "Could not extract chat/user ID"}

        # Get or create session via ConversationManager
        if not self.conversation_manager:
            self.conversation_manager = await get_conversation_manager()

        session = await self.conversation_manager.get_or_create_session(user_id, chat_id)
        session_id = session["session_id"]
        workflow_type = session.get("workflow_type", WorkflowType.NONE)
        workflow_step = session.get("workflow_step", WorkflowStep.AWAITING_WORKFLOW_SELECTION)

        # =========================================================================
        # PRIORITY 1: Global commands (always handled first)
        # =========================================================================
        if not is_callback and text:
            text_lower = text.strip().casefold()

            if text_lower == "/start":
                return await self._handle_start_command(user_id, chat_id)
            elif text_lower == "/menu":
                return await self._handle_menu_command(user_id, chat_id, session)
            elif text_lower == "/cancel":
                return await self._handle_cancel_command(user_id, chat_id, session)
            elif text_lower == "/status":
                return await self._handle_status_command(user_id, chat_id, session)

        # =========================================================================
        # PRIORITY 2: callback_query (inline button responses)
        # =========================================================================
        if is_callback:
            # Answer callback to stop Telegram spinner
            await self._answer_callback_query(callback_query.get("id"))
            return await self._handle_callback_query(user_id, chat_id, session, text, callback_query)

        # =========================================================================
        # PRIORITY 3: Active workflow awaiting response
        # =========================================================================
        if workflow_type == WorkflowType.SUPPLIER_INVOICE:
            if workflow_step in [WorkflowStep.INVOICE_AWAITING_APPROVAL, WorkflowStep.INVOICE_AWAITING_CORRECTION]:
                return await self._handle_invoice_approval_correction(user_id, chat_id, session, text)
            elif workflow_step == WorkflowStep.INVOICE_AWAITING_SUPPLIER_CONFIRMATION:
                return await self._handle_supplier_confirmation(user_id, chat_id, session, text)
            elif workflow_step == WorkflowStep.INVOICE_AWAITING_CORRECTION:
                return await self._handle_invoice_correction_text(user_id, chat_id, session, text)
            elif workflow_step == WorkflowStep.INVOICE_AWAITING_DOCUMENT:
                return await self._handle_invoice_document(user_id, chat_id, session, tg_message, update_id)

        elif workflow_type == WorkflowType.DOG_MANAGEMENT:
            # Delegate to DogIntakeAgent for dog management workflow
            return await self._handle_dog_workflow(user_id, chat_id, session, tg_message, text)

        # =========================================================================
        # PRIORITY 4: Pending clarification (supplier not found, etc.)
        # =========================================================================
        if session.get("status") == "supplier_not_found":
            return await self._handle_supplier_confirmation(user_id, chat_id, session, text)

        # =========================================================================
        # PRIORITY 5: Media within active invoice workflow
        # =========================================================================
        has_document = "document" in tg_message if tg_message else False
        has_photo = "photo" in tg_message if tg_message else False

        if workflow_type == WorkflowType.SUPPLIER_INVOICE and workflow_step == WorkflowStep.INVOICE_AWAITING_DOCUMENT:
            if has_document or has_photo:
                return await self._handle_invoice_document(user_id, chat_id, session, tg_message, update_id)

        # =========================================================================
        # PRIORITY 6: Explicit workflow selection (text commands)
        # =========================================================================
        if text:
            text_lower = text.strip().casefold()

            # Invoice workflow triggers
            invoice_keywords = [
                "factura",
                "factura proveedor",
                "gasto",
                "registrar factura",
                "procesar factura",
                "invoice",
                "supplier invoice",
                "expense",
                "introducir factura",
                "nueva factura",
            ]

            # Dog workflow triggers
            dog_keywords = [
                "perro",
                "gestionar perro",
                "nuevo perro",
                "registrar perro",
                "dog",
                "manage dog",
                "new dog",
            ]

            is_invoice_text = any(kw in text_lower for kw in invoice_keywords)
            is_dog_text = any(kw in text_lower for kw in dog_keywords)

            if is_invoice_text and not is_dog_text:
                return await self._start_invoice_workflow(user_id, chat_id, session)
            elif is_dog_text and not is_invoice_text:
                return await self._start_dog_workflow(user_id, chat_id, session)
            elif is_invoice_text and is_dog_text:
                # Ambiguous - ask user
                return await self._send_workflow_selection(
                    user_id, chat_id, session, "Ambos workflows detectados. ¿Qué quieres hacer?"
                )

        # =========================================================================
        # PRIORITY 7: Media without workflow → pending_media + ask
        # =========================================================================
        if tg_message and (has_document or has_photo):
            # Store pending media in session context
            pending_media = self._extract_pending_media(tg_message)
            await self.conversation_manager.update_context(user_id, chat_id, {"pending_media": pending_media})

            # Ask user what to do
            keyboard = get_main_menu_keyboard()
            await self._send_telegram_message(
                chat_id, "He recibido un archivo.\n¿Qué quieres hacer con él?", reply_markup=keyboard
            )
            return {
                "success": True,
                "session_id": session_id,
                "workflow_type": WorkflowType.NONE,
                "workflow_step": WorkflowStep.AWAITING_WORKFLOW_SELECTION,
                "message": "Pending media stored, workflow selection requested",
                "awaiting_input": True,
            }

        # =========================================================================
        # PRIORITY 8: Fallback - show menu
        # =========================================================================
        return await self._send_workflow_selection(user_id, chat_id, session)

    async def _start_invoice_processing(
        self, message: dict, workflow: dict, workflow_id: str, update_id: int | None
    ) -> dict:
        """Start invoice processing workflow."""
        tg_message = message.get("message") or message.get("edited_message")

        # Extract file info
        file_content = None
        filename = "invoice.pdf"

        if "document" in tg_message:
            doc = tg_message["document"]
            file_id = doc.get("file_id")
            filename = doc.get("file_name", "invoice.pdf")
            file_content = await self._download_telegram_file(file_id) if file_id else None
        elif "photo" in tg_message:
            # Get largest photo
            photos = tg_message["photo"]
            largest = max(photos, key=lambda p: p.get("file_size", 0))
            file_id = largest.get("file_id")
            filename = f"invoice_photo_{file_id}.jpg"
            file_content = await self._download_telegram_file(file_id) if file_id else None

        if not file_content:
            return {
                "success": False,
                "error": "Could not download file from Telegram",
                "workflow_id": workflow_id,
            }

        # Process invoice
        try:
            result = await self.invoice_agent.process_invoice(file_content, filename)
        except Exception as e:
            logger.error("invoice_processing_failed", error=str(e))
            return {
                "success": False,
                "error": f"Error procesando factura: {str(e)}",
                "workflow_id": workflow_id,
            }

        if not result.get("success"):
            # Check if supplier not found - need to ask user
            if result.get("error") == "supplier_not_found":
                workflow["step"] = WorkflowStep.INVOICE_PENDING_APPROVAL
                workflow["status"] = "supplier_not_found"
                workflow["invoice_draft_id"] = None  # Not persisted yet
                workflow["pending_invoice_data"] = {
                    "file_content": file_content,
                    "filename": filename,
                    "result": result,
                }
                tax_id = result.get("tax_id", "desconocido")
                return {
                    "success": True,
                    "workflow_id": workflow_id,
                    "step": workflow["step"],
                    "message": (
                        f"Proveedor no encontrado en Dolibarr (CIF/NIF: {tax_id}).\n\n"
                        "Opciones:\nCREAR PROVEEDOR\nCORREGIR\nCANCELAR"
                    ),
                    "awaiting_input": True,
                    "requires_supplier_decision": True,
                }

            # Other error
            return {
                "success": False,
                "error": result.get("error", "Error desconocido"),
                "details": result.get("details"),
                "workflow_id": workflow_id,
            }

        # Success - create draft for approval
        correlation_id = str(uuid.uuid4())

        # Persist draft
        from app.services.invoice_draft_service import get_invoice_draft_service

        draft_service = await get_invoice_draft_service()
        chat_id = tg_message.get("chat", {}).get("id", 0)
        draft = await draft_service.create_draft(
            correlation_id=correlation_id,
            telegram_user_id=tg_message.get("from", {}).get("id", 0),
            telegram_chat_id=chat_id,
            telegram_message_id=tg_message.get("message_id", 0),
            telegram_update_id=update_id or 0,
            file_content=file_content,
            file_path=result["file_path"],
            final_path=result["final_path"],
            supplier_tax_id=result["invoice"]["supplier"]["tax_id"],
            supplier_name=result["invoice"]["supplier"]["name"],
            invoice_data=result["invoice"],
            summary=result["summary"],
        )

        # Update workflow
        workflow["step"] = WorkflowStep.INVOICE_PENDING_APPROVAL
        workflow["status"] = "awaiting_approval"
        workflow["invoice_draft_id"] = draft.draft_id
        workflow["invoice_correlation_id"] = correlation_id

        # Format approval message
        summary = result["summary"]
        validation_status = "OK" if not result.get("requires_review") else "REQUIERE REVISIÓN"

        msg = (
            f"📄 FACTURA PROVEEDOR\n\n"
            f"Proveedor: {summary['supplier_name']}\n"
            f"CIF/NIF: {summary['supplier_tax_id']}\n"
            f"Factura: {summary['invoice_number']}\n"
            f"Fecha: {summary['invoice_date']}\n"
            f"Categoría: {summary.get('expense_category', 'pendiente')}\n"
            f"Base: {summary['subtotal']:.2f} {summary['currency']}\n"
            f"IVA: {summary['tax_total']:.2f} {summary['currency']}\n"
            f"Retención: {summary.get('withholding_total', 0):.2f} {summary['currency']}\n"
            f"TOTAL: {summary['total']:.2f} {summary['currency']}\n\n"
            f"Validación: {validation_status}\n\n"
            f"Opciones:\n"
            f"APROBAR\n"
            f"CORREGIR\n"
            f"CANCELAR"
        )

        return {
            "success": True,
            "workflow_id": workflow_id,
            "step": workflow["step"],
            "message": msg,
            "awaiting_input": True,
            "invoice_summary": summary,
        }

    async def _download_telegram_file(self, file_id: str) -> bytes | None:
        """Download file from Telegram using the Telegram client."""
        try:
            from app.core.telegram_client import create_telegram_client

            client = await create_telegram_client()
            return await client.get_file_and_download(file_id)
        except Exception as e:
            logger.error("telegram_download_failed", file_id=file_id, error=str(e))
            return None

    async def _handle_invoice_approval(self, workflow: dict, workflow_id: str) -> dict:
        """Handle invoice approval - create in Dolibarr."""
        draft_id = workflow.get("invoice_draft_id")
        if not draft_id:
            return {"success": False, "error": "No draft ID in workflow"}

        # Update status to creating
        workflow["step"] = WorkflowStep.INVOICE_CREATING_DOLIBARR
        workflow["status"] = "creating_dolibarr"

        from app.services.invoice_draft_service import get_invoice_draft_service

        draft_service = await get_invoice_draft_service()

        await draft_service.update_draft_status(draft_id, "CREATING_DOLIBARR")

        # Get draft
        draft = await draft_service.get_draft(draft_id)
        if not draft:
            return {"success": False, "error": "Draft not found"}

        # Approve invoice
        try:
            result = await self.invoice_agent.approve_invoice(
                pending_file_path=draft.file_path,
                final_path=draft.final_path,
                invoice_data=draft.invoice_data,
            )
        except Exception as e:
            logger.error("invoice_approval_failed", error=str(e))
            await draft_service.update_draft_status(draft_id, "REQUIRES_REVIEW")
            workflow["step"] = WorkflowStep.INVOICE_FAILED
            workflow["status"] = "failed"
            return {
                "success": False,
                "error": f"Error registrando en Dolibarr: {str(e)}",
                "workflow_id": workflow_id,
            }

        # Handle attachment failure (invoice created but document not attached)
        if not result.get("success") and result.get("requires_cleanup"):
            dolibarr_invoice_id = result.get("dolibarr_invoice_id")
            await draft_service.update_draft_status(draft_id, "REQUIRES_CLEANUP")
            workflow["step"] = WorkflowStep.INVOICE_FAILED
            workflow["status"] = "requires_cleanup"
            workflow["dolibarr_invoice_id"] = dolibarr_invoice_id
            return {
                "success": False,
                "error": "document_attachment_failed",
                "dolibarr_invoice_id": dolibarr_invoice_id,
                "message": (
                    f"❌ Factura creada en Dolibarr (ID: {dolibarr_invoice_id}) "
                    f"pero no se pudo adjuntar el documento original.\n"
                    f"Requiere intervención manual para adjuntar el justificante."
                ),
                "requires_cleanup": True,
                "workflow_id": workflow_id,
            }

        if result.get("success"):
            # Update draft status
            await draft_service.update_draft_status(
                draft_id, "REGISTERED", dolibarr_invoice_id=result.get("dolibarr_invoice_id")
            )

            workflow["step"] = WorkflowStep.INVOICE_REGISTERED
            workflow["status"] = "completed"
            workflow["dolibarr_invoice_id"] = result.get("dolibarr_invoice_id")

            summary = draft.summary
            return {
                "success": True,
                "workflow_id": workflow_id,
                "step": workflow["step"],
                "message": (
                    f"✅ Factura registrada correctamente\n\n"
                    f"Proveedor: {summary['supplier_name']}\n"
                    f"Factura: {summary['invoice_number']}\n"
                    f"Total: {summary['total']:.2f} {summary['currency']}\n"
                    f"Categoría: {summary.get('expense_category', 'N/A')}\n"
                    f"Dolibarr: {result.get('dolibarr_invoice_id')}"
                ),
            }
        else:
            await draft_service.update_draft_status(draft_id, "REQUIRES_REVIEW")
            workflow["step"] = WorkflowStep.INVOICE_FAILED
            workflow["status"] = "failed"
            return {
                "success": False,
                "error": result.get("error", "Error desconocido"),
                "workflow_id": workflow_id,
            }

    async def _handle_invoice_correction(self, workflow: dict, workflow_id: str, corrections: dict[str, Any]) -> dict:
        """Handle invoice correction from user."""
        draft_id = workflow.get("invoice_draft_id")
        if not draft_id:
            return {"success": False, "error": "No draft ID in workflow"}

        from app.services.invoice_draft_service import get_invoice_draft_service

        draft_service = await get_invoice_draft_service()

        draft = await draft_service.get_draft(draft_id)
        if not draft:
            return {"success": False, "error": "Draft not found"}

        # Apply corrections to invoice_data
        invoice_data = dict(draft.invoice_data)
        summary = dict(draft.summary)

        # Apply corrections
        if "total" in corrections:
            invoice_data["total"] = corrections["total"]
            summary["total"] = corrections["total"]
        if "subtotal" in corrections:
            invoice_data["subtotal"] = corrections["subtotal"]
            summary["subtotal"] = corrections["subtotal"]
        if "tax_total" in corrections:
            invoice_data["tax_total"] = corrections["tax_total"]
            summary["tax_total"] = corrections["tax_total"]
        if "vat_rate" in corrections:
            # Apply to all lines or taxes
            for line in invoice_data.get("lines", []):
                line["vat_rate"] = corrections["vat_rate"]
                line["total"] = line["quantity"] * line["unit_price"]
            # Recalculate
            invoice_data["subtotal"] = sum(line["total"] for line in invoice_data.get("lines", []))
            invoice_data["tax_total"] = invoice_data["subtotal"] * corrections["vat_rate"] / 100
            invoice_data["total"] = invoice_data["subtotal"] + invoice_data["tax_total"]
            summary.update(
                {
                    "subtotal": invoice_data["subtotal"],
                    "tax_total": invoice_data["tax_total"],
                    "total": invoice_data["total"],
                }
            )
        if "expense_category" in corrections:
            invoice_data["expense_category"] = corrections["expense_category"]
            summary["expense_category"] = corrections["expense_category"]
        if "supplier_name" in corrections:
            invoice_data["supplier"]["name"] = corrections["supplier_name"]
            summary["supplier_name"] = corrections["supplier_name"]
        if "invoice_number" in corrections:
            invoice_data["invoice"]["number"] = corrections["invoice_number"]
            summary["invoice_number"] = corrections["invoice_number"]

        # Re-run deterministic checks
        from agents.invoice_processing.agent import InvoiceData

        try:
            validated = InvoiceData(**invoice_data)
            invoice_data = validated.dict()
        except Exception as e:
            return {
                "success": False,
                "error": f"Validación fallida tras corrección: {str(e)}",
                "workflow_id": workflow_id,
            }

        # Update draft
        await draft_service.update_invoice_data(draft_id, invoice_data, summary)

        # Format updated message
        validation_status = "OK"
        msg = (
            f"📄 FACTURA PROVEEDOR (CORREGIDA)\n\n"
            f"Proveedor: {summary['supplier_name']}\n"
            f"CIF/NIF: {summary['supplier_tax_id']}\n"
            f"Factura: {summary['invoice_number']}\n"
            f"Fecha: {summary['invoice_date']}\n"
            f"Categoría: {summary.get('expense_category', 'pendiente')}\n"
            f"Base: {summary['subtotal']:.2f} {summary['currency']}\n"
            f"IVA: {summary['tax_total']:.2f} {summary['currency']}\n"
            f"Retención: {summary.get('withholding_total', 0):.2f} {summary['currency']}\n"
            f"TOTAL: {summary['total']:.2f} {summary['currency']}\n\n"
            f"Validación: {validation_status}\n\n"
            f"Opciones:\n"
            f"APROBAR\n"
            f"CORREGIR\n"
            f"CANCELAR"
        )

        return {
            "success": True,
            "workflow_id": workflow_id,
            "step": WorkflowStep.INVOICE_PENDING_APPROVAL,
            "message": msg,
            "awaiting_input": True,
            "invoice_summary": summary,
        }

    async def _handle_invoice_cancellation(self, workflow: dict, workflow_id: str) -> dict:
        """Handle invoice cancellation."""
        draft_id = workflow.get("invoice_draft_id")
        if draft_id:
            from app.services.invoice_draft_service import get_invoice_draft_service

            draft_service = await get_invoice_draft_service()
            await draft_service.update_draft_status(draft_id, "REJECTED")
            draft = await draft_service.get_draft(draft_id)
            if draft:
                # Move file to rejected
                await self.invoice_agent.reject_invoice(draft.file_path, "Cancelled by user")

        workflow["step"] = WorkflowStep.INVOICE_FAILED
        workflow["status"] = "cancelled"

        return {
            "success": True,
            "workflow_id": workflow_id,
            "step": workflow["step"],
            "message": "Factura cancelada.",
        }

    async def _handle_supplier_creation(self, workflow: dict, workflow_id: str) -> dict:
        """Handle supplier creation after user confirmation."""
        pending_data = workflow.get("pending_invoice_data")
        if not pending_data:
            return {"success": False, "error": "No pending invoice data", "workflow_id": workflow_id}

        file_content = pending_data["file_content"]
        filename = pending_data["filename"]
        result = pending_data["result"]

        tax_id = result.get("tax_id", "desconocido")
        supplier_name = result.get("invoice", {}).get("supplier", {}).get("name", "Proveedor desconocido")

        # Extract address from invoice if available
        address = result.get("invoice", {}).get("supplier", {}).get("address")

        # Create supplier in Dolibarr
        try:
            from app.services.invoice_integration_service import InvoiceIntegrationService

            service = InvoiceIntegrationService()
            async with service as s:
                supplier = await s.create_supplier(
                    name=supplier_name,
                    tax_id=tax_id,
                    address=address,
                )
            supplier_id = supplier.get("id")

            if not supplier_id:
                return {
                    "success": False,
                    "error": "Failed to create supplier - no ID returned",
                    "workflow_id": workflow_id,
                }

            logger.info("supplier_created", supplier_id=supplier_id, tax_id=tax_id)

            # Now re-process the invoice with the new supplier
            # We need to update the invoice data with the supplier info
            invoice_data = result.get("invoice", {})
            invoice_data["supplier"]["name"] = supplier.get("name", supplier_name)

            # Re-process invoice (will now find the supplier)
            process_result = await self.invoice_agent.process_invoice(file_content, filename)

            if not process_result.get("success"):
                return {
                    "success": False,
                    "error": f"Error re-procesando factura tras crear proveedor: {process_result.get('error')}",
                    "workflow_id": workflow_id,
                }

            # Create draft for approval
            correlation_id = str(uuid.uuid4())

            from app.services.invoice_draft_service import get_invoice_draft_service

            draft_service = await get_invoice_draft_service()
            draft = await draft_service.create_draft(
                correlation_id=correlation_id,
                telegram_user_id=workflow.get("user_id", 0),
                telegram_chat_id=workflow.get("chat_id", 0),
                telegram_message_id=0,  # Will be updated when we have the actual message
                telegram_update_id=0,
                file_content=file_content,
                file_path=process_result["file_path"],
                final_path=process_result["final_path"],
                supplier_tax_id=process_result["invoice"]["supplier"]["tax_id"],
                supplier_name=process_result["invoice"]["supplier"]["name"],
                invoice_data=process_result["invoice"],
                summary=process_result["summary"],
            )

            # Update workflow
            workflow["step"] = WorkflowStep.INVOICE_PENDING_APPROVAL
            workflow["status"] = "awaiting_approval"
            workflow["invoice_draft_id"] = draft.draft_id
            workflow["invoice_correlation_id"] = correlation_id
            workflow["pending_invoice_data"] = None  # Clear pending data

            # Format approval message
            summary = process_result["summary"]
            validation_status = "OK" if not process_result.get("requires_review") else "REQUIERE REVISIÓN"

            msg = (
                f"✅ Proveedor creado correctamente (ID: {supplier_id})\n\n"
                f"📄 FACTURA PROVEEDOR\n\n"
                f"Proveedor: {summary['supplier_name']}\n"
                f"CIF/NIF: {summary['supplier_tax_id']}\n"
                f"Factura: {summary['invoice_number']}\n"
                f"Fecha: {summary['invoice_date']}\n"
                f"Categoría: {summary.get('expense_category', 'pendiente')}\n"
                f"Base: {summary['subtotal']:.2f} {summary['currency']}\n"
                f"IVA: {summary['tax_total']:.2f} {summary['currency']}\n"
                f"Retención: {summary.get('withholding_total', 0):.2f} {summary['currency']}\n"
                f"TOTAL: {summary['total']:.2f} {summary['currency']}\n\n"
                f"Validación: {validation_status}\n\n"
                f"Opciones:\n"
                f"APROBAR\n"
                f"CORREGIR\n"
                f"CANCELAR"
            )

            return {
                "success": True,
                "workflow_id": workflow_id,
                "step": workflow["step"],
                "message": msg,
                "awaiting_input": True,
                "invoice_summary": summary,
            }

        except Exception as e:
            logger.error("supplier_creation_failed", error=str(e))
            return {
                "success": False,
                "error": f"Error creando proveedor: {str(e)}",
                "workflow_id": workflow_id,
            }

    async def handle_media_upload(
        self, workflow_id: str, file_content: bytes, filename: str, purpose: str = "original"
    ) -> dict:
        """
        Handle media upload for a dog.
        Part of Media Pipeline: INGEST → ANALYZE → SELECT
        """
        workflow = self.active_workflows.get(workflow_id)
        if not workflow:
            return {"success": False, "error": "Workflow not found"}

        dog_internal_id = workflow["dog_internal_id"]
        if not dog_internal_id:
            return {"success": False, "error": "No dog associated with workflow"}

        # Ingest media
        ingest_result = await self.media_pipeline_agent.ingest_media(
            file_content=file_content,
            filename=filename,
            dog_internal_id=dog_internal_id,
            purpose=purpose,
        )

        if not ingest_result["success"]:
            return ingest_result

        media_meta = ingest_result["media_metadata"]
        workflow["media_items"].append(media_meta)

        # Auto-analyze if photo
        if media_meta["media_type"] == "photo":
            analysis = await self.media_pipeline_agent.selection_agent.analyze_image(media_meta["file_path"])
            media_meta["analysis"] = analysis

        return {
            "success": True,
            "workflow_id": workflow_id,
            "step": WorkflowStep.MEDIA_ANALYZE,
            "message": f"Media recibida ({len(workflow['media_items'])} total). Análisis completado.",
            "media": media_meta,
        }

    async def finalize_media_selection(self, workflow_id: str) -> dict:
        """
        Finalize media selection after all uploads.
        Triggers: SELECT best → GENERATE variants → PREPARE for publishing
        """
        workflow = self.active_workflows.get(workflow_id)
        if not workflow:
            return {"success": False, "error": "Workflow not found"}

        if not workflow["media_items"]:
            return {"success": False, "error": "No media to select from"}

        # Select best media for publishing
        selection = await self.media_pipeline_agent.select_best_for_publishing(
            workflow["dog_internal_id"], workflow["media_items"]
        )

        # Generate social variants (optional, async)
        cover_path = None
        if selection.get("cover"):
            # Find cover file path
            for m in workflow["media_items"]:
                if m["file_hash"] in selection["cover"]:
                    cover_path = m["file_path"]
                    break

            if cover_path:
                # Get dog info for prompts
                dog_info = await self._get_dog_info(workflow["dog_id"])
                if dog_info:
                    await self.media_pipeline_agent.generate_social_variants(
                        dog_internal_id=workflow["dog_internal_id"],
                        cover_image_path=cover_path,
                        breed=dog_info.get("breed_name", ""),
                        dog_name=dog_info.get("name", ""),
                        privacy_scope="LOCAL_ONLY",
                    )

        workflow["step"] = WorkflowStep.CONTENT_GENERATE
        workflow["media_selection"] = selection

        return {
            "success": True,
            "workflow_id": workflow_id,
            "step": workflow["step"],
            "message": "Selección de media completada. Generando contenido...",
            "selection": selection,
        }

    async def generate_content(self, workflow_id: str) -> dict:
        """
        Generate marketing content for the dog.
        Uses ContentMarketingAgent with dog data + selected media.
        """
        workflow = self.active_workflows.get(workflow_id)
        if not workflow:
            return {"success": False, "error": "Workflow not found"}

        dog_id = workflow["dog_id"]

        # Generate individual dog content
        content_result = await self.content_agent.generate_individual_content(dog_id)

        if not content_result["success"]:
            return content_result

        # Add selected media paths to content
        selection = workflow.get("media_selection", {})
        content_result["suggested_media"] = {
            "cover": selection.get("cover"),
            "listing": selection.get("listing", []),
            "social": selection.get("social", []),
        }

        workflow["content"] = content_result
        workflow["step"] = WorkflowStep.CONTENT_APPROVE
        workflow["status"] = "awaiting_content_approval"

        return {
            "success": True,
            "workflow_id": workflow_id,
            "step": workflow["step"],
            "message": "Contenido generado. Requiere aprobación antes de publicar.",
            "content": content_result,
            "requires_approval": True,
        }

    async def approve_content(self, workflow_id: str, approved: bool, feedback: str = "") -> dict:
        """
        Human approval for generated content.
        """
        workflow = self.active_workflows.get(workflow_id)
        if not workflow:
            return {"success": False, "error": "Workflow not found"}

        if not approved:
            workflow["status"] = "content_rejected"
            workflow["rejection_feedback"] = feedback
            return {
                "success": True,
                "workflow_id": workflow_id,
                "message": "Contenido rechazado. Puedes regenerar o editar.",
            }

        # Approved - create publication draft
        workflow["step"] = WorkflowStep.PUBLISH_DRAFT
        return await self.create_publication_draft(workflow_id)

    async def create_publication_draft(self, workflow_id: str) -> dict:
        """
        Create publication draft from approved content.
        """
        workflow = self.active_workflows.get(workflow_id)
        if not workflow:
            return {"success": False, "error": "Workflow not found"}

        content = workflow["content"]
        selection = workflow.get("media_selection", {})
        dog_info = await self._get_dog_info(workflow["dog_id"])

        # Create publication via API
        pub_data = {
            "expediente_id": dog_info.get("expediente_id", 1),
            "platform": "milanuncios",
            "title": content["title"],
            "description": content["copy"],
            "photos": selection.get("listing", [])[:10],  # Milanuncios max 20
            "price": dog_info.get("sale_price"),
        }

        response = await self._api_post("/publicaciones/", pub_data)
        if not response.get("success"):
            return {"success": False, "error": response.get("error")}

        publication = response["data"]
        workflow["publication_id"] = publication["id"]
        workflow["step"] = WorkflowStep.PUBLISH_APPROVE
        workflow["status"] = "awaiting_publish_approval"

        return {
            "success": True,
            "workflow_id": workflow_id,
            "step": workflow["step"],
            "message": "Borrador de publicación creado. Requiere aprobación para publicar.",
            "publication": publication,
            "requires_approval": True,
        }

    async def approve_publication(self, workflow_id: str, approved: bool, feedback: str = "") -> dict:
        """
        Human approval to publish.
        """
        workflow = self.active_workflows.get(workflow_id)
        if not workflow:
            return {"success": False, "error": "Workflow not found"}

        if not approved:
            workflow["status"] = "publish_rejected"
            return {
                "success": True,
                "workflow_id": workflow_id,
                "message": "Publicación rechazada.",
            }

        # Approve via API
        pub_id = workflow["publication_id"]
        approve_resp = await self._api_post(f"/publicaciones/{pub_id}/approve")

        if not approve_resp.get("success"):
            return {"success": False, "error": approve_resp.get("error")}

        workflow["step"] = WorkflowStep.PUBLISH_EXECUTE
        return await self.execute_publication(workflow_id)

    async def execute_publication(self, workflow_id: str) -> dict:
        """
        Execute actual publication on platform (Milanuncios via Playwright).

        Flow:
        1. Prepare assets for publishing
        2. Call PublishingAgent.auto_publish() to do real Milanuncios publishing via Playwright
        3. If successful, call API with external_id and external_url
        4. If failed, call API to mark as failed
        5. NEVER mark as published without real platform confirmation
        """
        workflow = self.active_workflows.get(workflow_id)
        if not workflow:
            return {"success": False, "error": "Workflow not found"}

        pub_id = workflow["publication_id"]

        # Prepare assets for publishing
        assets = await self.media_pipeline_agent.prepare_for_publishing(
            workflow["dog_internal_id"], platforms=["milanuncios"]
        )

        milanuncios_assets = assets.get("assets", {}).get("milanuncios", {})
        cover = milanuncios_assets.get("cover")
        photos = milanuncios_assets.get("photos", [])

        if not cover or not photos:
            return {
                "success": False,
                "error": "No assets available for publishing",
                "step": WorkflowStep.PUBLISH_EXECUTE,
            }

        # Get publication data to pass to PublishingAgent
        pub_resp = await self._api_get(f"/publicaciones/{pub_id}")
        if not pub_resp.get("success"):
            return {"success": False, "error": "Could not fetch publication data"}

        _ = pub_resp.get("data")

        # Call PublishingAgent to do REAL Milanuncios publishing
        publish_result = await self.publishing_agent.auto_publish(
            listing_id=pub_id,  # Using publication ID as listing_id
            platform="milanuncios",
        )

        if not publish_result.get("success"):
            error = publish_result.get("error", "Unknown error")
            detail = publish_result.get("detail", error)

            # If requires_human_action, don't mark as failed - let human handle
            if publish_result.get("requires_human_action"):
                return {
                    "success": False,
                    "error": "requires_human_action",
                    "detail": detail,
                    "step": WorkflowStep.PUBLISH_EXECUTE,
                    "message": "Se requiere intervención humana para completar la publicación.",
                }

            # Mark as failed in API
            await self._api_post(f"/publicaciones/{pub_id}/publish-failed", data={"error": detail})

            return {
                "success": False,
                "error": "publish_failed",
                "detail": detail,
                "step": WorkflowStep.PUBLISH_EXECUTE,
                "message": f"Falló la publicación en Milanuncios: {detail}",
            }

        # SUCCESS: Real Milanuncios publishing confirmed!
        external_id = publish_result.get("external_id")
        external_url = publish_result.get("external_url")

        if not external_id or not external_url:
            # Should not happen if PublishingAgent works correctly, but safeguard
            await self._api_post(
                f"/publicaciones/{pub_id}/publish-failed",
                data={"error": "PublishingAgent succeeded but did not return external_id/external_url"},
            )
            return {
                "success": False,
                "error": "missing_confirmation",
                "detail": "PublishingAgent did not return platform confirmation",
                "step": WorkflowStep.PUBLISH_EXECUTE,
            }

        # Mark as published in API with REAL confirmation
        publish_resp = await self._api_post(
            f"/publicaciones/{pub_id}/publish", data={"external_id": external_id, "external_url": external_url}
        )

        if not publish_resp.get("success"):
            return {"success": False, "error": publish_resp.get("error")}

        workflow["step"] = WorkflowStep.COMPLETE
        workflow["status"] = "completed"
        workflow["completed_at"] = datetime.utcnow().isoformat()
        workflow["external_id"] = external_id
        workflow["external_url"] = external_url

        return {
            "success": True,
            "workflow_id": workflow_id,
            "step": workflow["step"],
            "message": f"Publicación confirmada en Milanuncios. ID externo: {external_id}",
            "publication": publish_resp.get("data"),
            "external_id": external_id,
            "external_url": external_url,
        }

    # =========================================================================
    # HELPER METHODS - ConversationManager-based Telegram workflow
    # =========================================================================

    async def _send_telegram_message(
        self, chat_id: int, text: str, reply_markup=None, parse_mode: str = "HTML"
    ) -> bool:
        """Send message via Telegram client with optional inline keyboard."""
        try:
            from app.core.telegram_client import create_telegram_client

            client = await create_telegram_client()
            await client.send_message(chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup)
            await client.close()
            return True
        except Exception as e:
            logger.error("telegram_send_failed", chat_id=chat_id, error=str(e))
            return False

    async def _answer_callback_query(self, callback_query_id: str, text: str | None = None) -> bool:
        """Answer callback query to stop Telegram spinner."""
        try:
            from app.core.telegram_client import create_telegram_client

            client = await create_telegram_client()
            await client.answer_callback_query(callback_query_id, text=text)
            await client.close()
            return True
        except Exception as e:
            logger.error("answer_callback_failed", callback_query_id=callback_query_id, error=str(e))
            return False

    async def _send_workflow_selection(
        self, user_id: int, chat_id: int, session: dict, custom_text: str = None
    ) -> dict:
        """Send main menu with workflow selection buttons."""
        keyboard = get_main_menu_keyboard()
        text = custom_text or get_workflow_selection_text()
        await self._send_telegram_message(chat_id, text, reply_markup=keyboard)

        await self.conversation_manager.update_session(
            user_id,
            chat_id,
            workflow_type=WorkflowType.NONE,
            workflow_step=WorkflowStep.AWAITING_WORKFLOW_SELECTION,
            context={},
        )

        return {
            "success": True,
            "session_id": session["session_id"],
            "workflow_type": WorkflowType.NONE,
            "workflow_step": WorkflowStep.AWAITING_WORKFLOW_SELECTION,
            "message": text,
            "awaiting_input": True,
        }

    def _extract_pending_media(self, tg_message: dict) -> dict:
        """Extract pending media info from Telegram message."""
        pending = {
            "media_kind": None,
            "file_id": None,
            "file_unique_id": None,
            "file_name": None,
            "mime_type": None,
            "file_size": None,
            "original_message_id": tg_message.get("message_id"),
            "correlation_id": str(uuid.uuid4()),
        }

        if "document" in tg_message:
            doc = tg_message["document"]
            pending.update(
                {
                    "media_kind": "document",
                    "file_id": doc.get("file_id"),
                    "file_unique_id": doc.get("file_unique_id"),
                    "file_name": doc.get("file_name"),
                    "mime_type": doc.get("mime_type"),
                    "file_size": doc.get("file_size"),
                }
            )
        elif "photo" in tg_message:
            photos = tg_message["photo"]
            largest = max(photos, key=lambda p: p.get("file_size", 0))
            pending.update(
                {
                    "media_kind": "photo",
                    "file_id": largest.get("file_id"),
                    "file_unique_id": largest.get("file_unique_id"),
                    "file_name": f"photo_{largest.get('file_unique_id', 'unknown')}.jpg",
                    "mime_type": "image/jpeg",
                    "file_size": largest.get("file_size"),
                }
            )

        return pending

    async def _handle_start_command(self, user_id: int, chat_id: int) -> dict:
        """Handle /start command - show main menu."""
        keyboard = get_main_menu_keyboard()
        text = "🤖 <b>Hermes - Asistente Transvega</b>\n\n¿Qué quieres hacer?"
        await self._send_telegram_message(chat_id, text, reply_markup=keyboard)

        if self.conversation_manager:
            session = await self.conversation_manager.update_session(
                user_id,
                chat_id,
                workflow_type=WorkflowType.NONE,
                workflow_step=WorkflowStep.AWAITING_WORKFLOW_SELECTION,
                context={},
            )
            session_id = session.get("session_id") if session else None
        else:
            session_id = None

        return {
            "success": True,
            "workflow_type": WorkflowType.NONE,
            "workflow_step": WorkflowStep.AWAITING_WORKFLOW_SELECTION,
            "message": text,
            "awaiting_input": True,
            "session_id": session_id,
        }

    async def _handle_menu_command(self, user_id: int, chat_id: int, session: dict) -> dict:
        """Handle /menu command - show main menu, preserve critical drafts."""
        workflow_type = session.get("workflow_type")
        workflow_step = session.get("workflow_step")

        # If there's a critical pending draft (awaiting approval), warn but don't lose it
        if workflow_type == WorkflowType.SUPPLIER_INVOICE and workflow_step == WorkflowStep.INVOICE_AWAITING_APPROVAL:
            draft_id = session.get("context", {}).get("invoice_draft_id")
            if draft_id:
                keyboard = get_main_menu_keyboard()
                text = (
                    "⚠️ <b>Tienes una factura pendiente de aprobación</b>\n\n"
                    "El borrador se conserva. Puedes volver a él más tarde.\n\n"
                    "¿Qué quieres hacer?"
                )
                await self._send_telegram_message(chat_id, text, reply_markup=keyboard)
                return {
                    "success": True,
                    "workflow_type": workflow_type,
                    "workflow_step": workflow_step,
                    "message": text,
                    "awaiting_input": True,
                    "draft_preserved": True,
                }

        return await self._send_workflow_selection(user_id, chat_id, session)

    async def _handle_cancel_command(self, user_id: int, chat_id: int, session: dict) -> dict:
        """Handle /cancel command - cancel active workflow, clear pending media."""
        workflow_type = session.get("workflow_type")
        workflow_step = session.get("workflow_step")
        context = session.get("context", {})

        # Cancel invoice workflow if active
        if workflow_type == WorkflowType.SUPPLIER_INVOICE and workflow_step in [
            WorkflowStep.INVOICE_AWAITING_APPROVAL,
            WorkflowStep.INVOICE_AWAITING_CORRECTION,
            WorkflowStep.INVOICE_AWAITING_DOCUMENT,
            WorkflowStep.INVOICE_AWAITING_SUPPLIER_CONFIRMATION,
        ]:
            draft_id = context.get("invoice_draft_id")
            if draft_id:
                from app.services.invoice_draft_service import get_invoice_draft_service

                draft_service = await get_invoice_draft_service()
                await draft_service.update_draft_status(draft_id, "REJECTED")
                draft = await draft_service.get_draft(draft_id)
                if draft:
                    await self.invoice_agent.reject_invoice(draft.file_path, "Cancelled by user")

        # Clear pending media
        if context.get("pending_media"):
            await self.conversation_manager.update_context(user_id, chat_id, {"pending_media": None})

        # Reset session
        if self.conversation_manager:
            await self.conversation_manager.clear_workflow(user_id, chat_id)
            await self.conversation_manager.clear_context(user_id, chat_id)

        keyboard = get_main_menu_keyboard()
        text = "❌ Operación cancelada.\n\n¿Qué quieres hacer?"
        await self._send_telegram_message(chat_id, text, reply_markup=keyboard)

        return {
            "success": True,
            "workflow_type": WorkflowType.NONE,
            "workflow_step": WorkflowStep.AWAITING_WORKFLOW_SELECTION,
            "message": text,
            "awaiting_input": True,
        }

    async def _handle_status_command(self, user_id: int, chat_id: int, session: dict) -> dict:
        """Handle /status command - show current workflow state."""
        workflow_type = session.get("workflow_type")
        workflow_step = session.get("workflow_step")
        context = session.get("context", {})

        if workflow_type == WorkflowType.NONE:
            text = "📭 <b>Sin workflow activo</b>\n\nUsa /menu para ver opciones."
        elif workflow_type == WorkflowType.SUPPLIER_INVOICE:
            step_texts = {
                WorkflowStep.INVOICE_AWAITING_DOCUMENT: "Esperando documento (PDF/foto)",
                WorkflowStep.INVOICE_PROCESSING: "Procesando factura...",
                WorkflowStep.INVOICE_AWAITING_SUPPLIER_CONFIRMATION: "Proveedor no encontrado - requiere confirmación",
                WorkflowStep.INVOICE_AWAITING_APPROVAL: "Factura lista - esperando aprobación",
                WorkflowStep.INVOICE_AWAITING_CORRECTION: "Esperando corrección",
                WorkflowStep.INVOICE_CREATING_DOLIBARR: "Registrando en Dolibarr...",
                WorkflowStep.INVOICE_COMPLETED: "Factura registrada",
                WorkflowStep.INVOICE_CANCELLED: "Factura cancelada",
                WorkflowStep.INVOICE_FAILED: "Error en procesamiento",
            }
            step_text = step_texts.get(workflow_step, workflow_step)
            draft_id = context.get("invoice_draft_id", "N/A")
            text = f"📄 <b>Workflow: Factura de proveedor</b>\n\nEstado: {step_text}\nDraft ID: {draft_id}"
        elif workflow_type == WorkflowType.DOG_MANAGEMENT:
            text = f"🐶 <b>Workflow: Gestión de perros</b>\n\nEstado: {workflow_step}"
        else:
            text = f"Workflow: {workflow_type}\nEstado: {workflow_step}"

        await self._send_telegram_message(chat_id, text)

        return {
            "success": True,
            "workflow_type": workflow_type,
            "workflow_step": workflow_step,
            "message": text,
            "awaiting_input": True,
        }

    async def _handle_callback_query(
        self, user_id: int, chat_id: int, session: dict, callback_data: str, callback_query: dict
    ) -> dict:
        """Handle inline keyboard callback queries."""
        workflow_type = session.get("workflow_type")

        # Handle workflow selection callbacks
        if callback_data == "workflow:supplier_invoice":
            return await self._start_invoice_workflow(user_id, chat_id, session)

        if callback_data == "workflow:dog_management":
            return await self._start_dog_workflow(user_id, chat_id, session)

        if callback_data == "action:cancel":
            return await self._handle_cancel_command(user_id, chat_id, session)

        if callback_data == "action:menu":
            return await self._send_workflow_selection(user_id, chat_id, session)

        if callback_data == "action:help":
            text = get_help_text()
            await self._send_telegram_message(chat_id, text)
            return {"success": True, "message": text, "awaiting_input": True}

        # Invoice approval callbacks
        if workflow_type == WorkflowType.SUPPLIER_INVOICE:
            if callback_data == "invoice:approve":
                return await self._handle_invoice_approval_callback(user_id, chat_id, session)
            elif callback_data == "invoice:correct":
                return await self._start_invoice_correction(user_id, chat_id, session)
            elif callback_data == "invoice:cancel":
                return await self._handle_cancel_command(user_id, chat_id, session)
            elif callback_data == "invoice:back_to_approval":
                return await self._show_invoice_approval(user_id, chat_id, session)
            elif callback_data.startswith("correct:"):
                return await self._handle_correction_button(user_id, chat_id, session, callback_data)

        # Supplier not found callbacks
        if callback_data == "supplier:create":
            return await self._handle_supplier_creation_callback(user_id, chat_id, session)
        elif callback_data == "supplier:correct":
            return await self._start_invoice_correction(user_id, chat_id, session)
        elif callback_data == "supplier:cancel":
            return await self._handle_cancel_command(user_id, chat_id, session)

        # Dog management callbacks
        if workflow_type == WorkflowType.DOG_MANAGEMENT or callback_data.startswith("dog:"):
            return await self._handle_dog_callback(user_id, chat_id, session, callback_data)

        # Unknown callback
        return {"success": True, "message": "Acción no reconocida", "awaiting_input": True}

    async def _start_invoice_workflow(self, user_id: int, chat_id: int, session: dict) -> dict:
        """Start invoice processing workflow."""
        # Clear any pending media from previous fallback
        pending_media = session.get("context", {}).get("pending_media")

        await self.conversation_manager.update_session(
            user_id,
            chat_id,
            workflow_type=WorkflowType.SUPPLIER_INVOICE,
            workflow_step=WorkflowStep.INVOICE_AWAITING_DOCUMENT,
            context={"pending_media": pending_media} if pending_media else {},
        )

        text = (
            "📄 <b>Introducir factura de proveedor</b>\n\n"
            "Envíame la factura.\n\n"
            "Puedes enviar:\n"
            "• PDF\n"
            "• Fotografía\n"
            "• PDF escaneado\n\n"
            "La analizaré localmente y te mostraré los datos antes de registrarla."
        )

        keyboard = get_cancel_keyboard()
        await self._send_telegram_message(chat_id, text, reply_markup=keyboard)

        return {
            "success": True,
            "workflow_type": WorkflowType.SUPPLIER_INVOICE,
            "workflow_step": WorkflowStep.INVOICE_AWAITING_DOCUMENT,
            "message": text,
            "awaiting_input": True,
            "pending_media_recovered": pending_media is not None,
        }

    async def _handle_invoice_document(
        self, user_id: int, chat_id: int, session: dict, tg_message: dict, update_id: int | None
    ) -> dict:
        """Process invoice document/photo within active workflow."""
        # Use pending media if available, else extract from current message
        pending_media = session.get("context", {}).get("pending_media")

        if pending_media and not (tg_message and ("document" in tg_message or "photo" in tg_message)):
            # Recover pending media - need to download it
            file_content = await self._download_telegram_file(pending_media["file_id"])
            filename = pending_media.get("file_name", "invoice.pdf")
        elif tg_message and ("document" in tg_message or "photo" in tg_message):
            # New document in current message
            if "document" in tg_message:
                doc = tg_message["document"]
                file_id = doc.get("file_id")
                filename = doc.get("file_name", "invoice.pdf")
            else:
                photos = tg_message["photo"]
                largest = max(photos, key=lambda p: p.get("file_size", 0))
                file_id = largest.get("file_id")
                filename = f"invoice_photo_{file_id}.jpg"
            file_content = await self._download_telegram_file(file_id) if file_id else None
        else:
            return {"success": False, "error": "No document found"}

        if not file_content:
            return {"success": False, "error": "Could not download file from Telegram"}

        # Clear pending media after recovery
        await self.conversation_manager.update_context(user_id, chat_id, {"pending_media": None})

        # Update step to processing
        await self.conversation_manager.update_session(user_id, chat_id, workflow_step=WorkflowStep.INVOICE_PROCESSING)

        # Process invoice
        try:
            result = await self.invoice_agent.process_invoice(file_content, filename)
        except Exception as e:
            logger.error("invoice_processing_failed", error=str(e))
            await self.conversation_manager.update_session(user_id, chat_id, workflow_step=WorkflowStep.INVOICE_FAILED)
            return {"success": False, "error": f"Error procesando factura: {str(e)}"}

        if not result.get("success"):
            # Check if supplier not found
            if result.get("error") == "supplier_not_found":
                await self.conversation_manager.update_session(
                    user_id,
                    chat_id,
                    workflow_step=WorkflowStep.INVOICE_AWAITING_SUPPLIER_CONFIRMATION,
                    context={
                        "pending_invoice_data": {
                            "file_content": file_content,
                            "filename": filename,
                            "result": result,
                        },
                        "status": "supplier_not_found",
                    },
                )
                tax_id = result.get("tax_id", "desconocido")
                keyboard = get_supplier_not_found_keyboard()
                text = get_supplier_not_found_text(tax_id)
                await self._send_telegram_message(chat_id, text, reply_markup=keyboard)
                return {
                    "success": True,
                    "workflow_type": WorkflowType.SUPPLIER_INVOICE,
                    "workflow_step": WorkflowStep.INVOICE_AWAITING_SUPPLIER_CONFIRMATION,
                    "message": text,
                    "awaiting_input": True,
                }

            # Other error
            await self.conversation_manager.update_session(user_id, chat_id, workflow_step=WorkflowStep.INVOICE_FAILED)
            return {
                "success": False,
                "error": result.get("error", "Error desconocido"),
                "details": result.get("details"),
            }

        # Success - create draft for approval
        correlation_id = str(uuid.uuid4())
        from app.services.invoice_draft_service import get_invoice_draft_service

        draft_service = await get_invoice_draft_service()
        draft = await draft_service.create_draft(
            correlation_id=correlation_id,
            telegram_user_id=user_id,
            telegram_chat_id=chat_id,
            telegram_message_id=tg_message.get("message_id", 0) if tg_message else 0,
            telegram_update_id=update_id or 0,
            file_content=file_content,
            file_path=result["file_path"],
            final_path=result["final_path"],
            supplier_tax_id=result["invoice"]["supplier"]["tax_id"],
            supplier_name=result["invoice"]["supplier"]["name"],
            invoice_data=result["invoice"],
            summary=result["summary"],
        )

        # Update session with draft info
        await self.conversation_manager.update_session(
            user_id,
            chat_id,
            workflow_step=WorkflowStep.INVOICE_AWAITING_APPROVAL,
            context={
                "invoice_draft_id": draft.draft_id,
                "invoice_correlation_id": correlation_id,
            },
        )

        # Format approval message
        summary = result["summary"]
        validation_status = "OK" if not result.get("requires_review") else "REQUIERE REVISIÓN"
        text = get_invoice_approval_text({**summary, "validation_status": validation_status})
        keyboard = get_invoice_approval_keyboard()

        await self._send_telegram_message(chat_id, text, reply_markup=keyboard)

        return {
            "success": True,
            "workflow_type": WorkflowType.SUPPLIER_INVOICE,
            "workflow_step": WorkflowStep.INVOICE_AWAITING_APPROVAL,
            "message": text,
            "awaiting_input": True,
            "invoice_summary": summary,
        }

    async def _handle_invoice_approval_correction(self, user_id: int, chat_id: int, session: dict, text: str) -> dict:
        """Handle approval/correction/cancel text responses for invoice."""
        text_lower = text.strip().casefold()

        if text_lower in ["aprobar", "aprobado", "apruebo", "sí", "si", "yes", "ok", "confirmar"]:
            return await self._handle_invoice_approval_callback(user_id, chat_id, session)
        elif text_lower in ["corregir", "corrección", "correccion", "cambiar", "modificar"]:
            return await self._start_invoice_correction(user_id, chat_id, session)
        elif text_lower in ["cancelar", "cancelado", "no", "cancel"]:
            return await self._handle_cancel_command(user_id, chat_id, session)

        # Not recognized - re-prompt
        keyboard = get_invoice_approval_keyboard()
        msg = (
            "Responde con: APROBAR, CORREGIR o CANCELAR.\nPara corregir: 'El total son 125,40', 'Es combustible', etc."
        )
        await self._send_telegram_message(chat_id, msg, reply_markup=keyboard)
        return {"success": True, "awaiting_input": True}

    async def _handle_invoice_approval_callback(self, user_id: int, chat_id: int, session: dict) -> dict:
        """Handle invoice approval via callback or text."""
        context = session.get("context", {})
        draft_id = context.get("invoice_draft_id")

        if not draft_id:
            return {"success": False, "error": "No draft ID in session"}

        # Update step to creating
        await self.conversation_manager.update_session(
            user_id, chat_id, workflow_step=WorkflowStep.INVOICE_CREATING_DOLIBARR
        )

        from app.services.invoice_draft_service import get_invoice_draft_service

        draft_service = await get_invoice_draft_service()
        await draft_service.update_draft_status(draft_id, "CREATING_DOLIBARR")

        draft = await draft_service.get_draft(draft_id)
        if not draft:
            return {"success": False, "error": "Draft not found"}

        # Approve invoice
        try:
            result = await self.invoice_agent.approve_invoice(
                pending_file_path=draft.file_path,
                final_path=draft.final_path,
                invoice_data=draft.invoice_data,
            )
        except Exception as e:
            logger.error("invoice_approval_failed", error=str(e))
            await draft_service.update_draft_status(draft_id, "REQUIRES_REVIEW")
            await self.conversation_manager.update_session(user_id, chat_id, workflow_step=WorkflowStep.INVOICE_FAILED)
            return {"success": False, "error": f"Error registrando en Dolibarr: {str(e)}"}

        # Handle attachment failure
        if not result.get("success") and result.get("requires_cleanup"):
            dolibarr_invoice_id = result.get("dolibarr_invoice_id")
            await draft_service.update_draft_status(draft_id, "REQUIRES_CLEANUP")
            await self.conversation_manager.update_session(
                user_id,
                chat_id,
                workflow_step=WorkflowStep.INVOICE_FAILED,
                context={"dolibarr_invoice_id": dolibarr_invoice_id},
            )
            text = (
                f"❌ Factura creada en Dolibarr (ID: {dolibarr_invoice_id}) "
                f"pero no se pudo adjuntar el documento original.\n"
                f"Requiere intervención manual."
            )
            await self._send_telegram_message(chat_id, text)
            return {"success": False, "error": "document_attachment_failed", "dolibarr_invoice_id": dolibarr_invoice_id}

        if result.get("success"):
            await draft_service.update_draft_status(
                draft_id, "REGISTERED", dolibarr_invoice_id=result.get("dolibarr_invoice_id")
            )
            await self.conversation_manager.update_session(
                user_id,
                chat_id,
                workflow_type=WorkflowType.NONE,
                workflow_step=WorkflowStep.INVOICE_COMPLETED,
                context={},
            )

            summary = draft.summary
            text = (
                f"✅ Factura registrada correctamente\n\n"
                f"Proveedor: {summary['supplier_name']}\n"
                f"Factura: {summary['invoice_number']}\n"
                f"Total: {summary['total']:.2f} {summary['currency']}\n"
                f"Categoría: {summary.get('expense_category', 'N/A')}\n"
                f"Dolibarr: {result.get('dolibarr_invoice_id')}"
            )
            await self._send_telegram_message(chat_id, text)

            # Show menu after success
            keyboard = get_main_menu_keyboard()
            await self._send_telegram_message(chat_id, "¿Qué más quieres hacer?", reply_markup=keyboard)

            return {
                "success": True,
                "workflow_type": WorkflowType.NONE,
                "workflow_step": WorkflowStep.INVOICE_COMPLETED,
                "message": text,
            }
        else:
            await draft_service.update_draft_status(draft_id, "REQUIRES_REVIEW")
            await self.conversation_manager.update_session(user_id, chat_id, workflow_step=WorkflowStep.INVOICE_FAILED)
            return {"success": False, "error": result.get("error", "Error desconocido")}

    async def _start_invoice_correction(self, user_id: int, chat_id: int, session: dict) -> dict:
        """Start invoice correction flow."""
        await self.conversation_manager.update_session(
            user_id, chat_id, workflow_step=WorkflowStep.INVOICE_AWAITING_CORRECTION
        )

        keyboard = get_correction_keyboard()
        text = get_correction_prompt_text()
        await self._send_telegram_message(chat_id, text, reply_markup=keyboard)

        return {
            "success": True,
            "workflow_type": WorkflowType.SUPPLIER_INVOICE,
            "workflow_step": WorkflowStep.INVOICE_AWAITING_CORRECTION,
            "message": text,
            "awaiting_input": True,
        }

    async def _handle_invoice_correction_text(self, user_id: int, chat_id: int, session: dict, text: str) -> dict:
        """Handle text-based invoice correction."""
        corrections = self._parse_correction(text)
        if not corrections:
            keyboard = get_correction_keyboard()
            msg = (
                "No entendí la corrección. Usa los botones o escribe:\n"
                "• 'El total son 125,40'\n"
                "• 'Es combustible'\n"
                "• 'El IVA es 10%'"
            )
            await self._send_telegram_message(chat_id, msg, reply_markup=keyboard)
            return {"success": True, "awaiting_input": True}

        context = session.get("context", {})
        draft_id = context.get("invoice_draft_id")

        if not draft_id:
            return {"success": False, "error": "No draft ID in session"}

        from app.services.invoice_draft_service import get_invoice_draft_service

        draft_service = await get_invoice_draft_service()
        draft = await draft_service.get_draft(draft_id)

        if not draft:
            return {"success": False, "error": "Draft not found"}

        # Apply corrections
        invoice_data = dict(draft.invoice_data)
        summary = dict(draft.summary)

        if "total" in corrections:
            invoice_data["total"] = corrections["total"]
            summary["total"] = corrections["total"]
        if "subtotal" in corrections:
            invoice_data["subtotal"] = corrections["subtotal"]
            summary["subtotal"] = corrections["subtotal"]
        if "tax_total" in corrections:
            invoice_data["tax_total"] = corrections["tax_total"]
            summary["tax_total"] = corrections["tax_total"]
        if "vat_rate" in corrections:
            for line in invoice_data.get("lines", []):
                line["vat_rate"] = corrections["vat_rate"]
                line["total"] = line["quantity"] * line["unit_price"]
            invoice_data["subtotal"] = sum(line["total"] for line in invoice_data.get("lines", []))
            invoice_data["tax_total"] = invoice_data["subtotal"] * corrections["vat_rate"] / 100
            invoice_data["total"] = invoice_data["subtotal"] + invoice_data["tax_total"]
            summary.update(
                {
                    "subtotal": invoice_data["subtotal"],
                    "tax_total": invoice_data["tax_total"],
                    "total": invoice_data["total"],
                }
            )
        if "expense_category" in corrections:
            invoice_data["expense_category"] = corrections["expense_category"]
            summary["expense_category"] = corrections["expense_category"]
        if "supplier_name" in corrections:
            invoice_data["supplier"]["name"] = corrections["supplier_name"]
            summary["supplier_name"] = corrections["supplier_name"]
        if "invoice_number" in corrections:
            invoice_data["invoice"]["number"] = corrections["invoice_number"]
            summary["invoice_number"] = corrections["invoice_number"]

        # Validate
        from agents.invoice_processing.agent import InvoiceData

        try:
            validated = InvoiceData(**invoice_data)
            invoice_data = validated.dict()
        except Exception as e:
            return {"success": False, "error": f"Validación fallida: {str(e)}"}

        await draft_service.update_invoice_data(draft_id, invoice_data, summary)

        # Show updated approval
        validation_status = "OK"
        text = get_invoice_approval_text({**summary, "validation_status": validation_status})
        keyboard = get_invoice_approval_keyboard()
        await self._send_telegram_message(chat_id, text, reply_markup=keyboard)

        await self.conversation_manager.update_session(
            user_id, chat_id, workflow_step=WorkflowStep.INVOICE_AWAITING_APPROVAL
        )

        return {"success": True, "workflow_step": WorkflowStep.INVOICE_AWAITING_APPROVAL, "awaiting_input": True}

    async def _handle_correction_button(self, user_id: int, chat_id: int, session: dict, callback_data: str) -> dict:
        """Handle correction button callbacks."""
        # For now, just prompt for text input
        # Could be enhanced to ask specific field
        return await self._start_invoice_correction(user_id, chat_id, session)

    async def _show_invoice_approval(self, user_id: int, chat_id: int, session: dict) -> dict:
        """Show invoice approval screen again."""
        context = session.get("context", {})
        draft_id = context.get("invoice_draft_id")

        if not draft_id:
            return {"success": False, "error": "No draft ID"}

        from app.services.invoice_draft_service import get_invoice_draft_service

        draft_service = await get_invoice_draft_service()
        draft = await draft_service.get_draft(draft_id)

        if not draft:
            return {"success": False, "error": "Draft not found"}

        summary = draft.summary
        validation_status = "OK"
        text = get_invoice_approval_text({**summary, "validation_status": validation_status})
        keyboard = get_invoice_approval_keyboard()

        await self._send_telegram_message(chat_id, text, reply_markup=keyboard)

        await self.conversation_manager.update_session(
            user_id, chat_id, workflow_step=WorkflowStep.INVOICE_AWAITING_APPROVAL
        )

        return {"success": True, "workflow_step": WorkflowStep.INVOICE_AWAITING_APPROVAL, "awaiting_input": True}

    async def _handle_supplier_confirmation(self, user_id: int, chat_id: int, session: dict, text: str) -> dict:
        """Handle supplier not found text responses."""
        text_lower = text.strip().casefold()

        if text_lower in ["crear proveedor", "crear", "create supplier", "create"]:
            return await self._handle_supplier_creation_callback(user_id, chat_id, session)
        elif text_lower in ["corregir", "corrección", "correccion", "cambiar", "modificar", "correct"]:
            return await self._start_invoice_correction(user_id, chat_id, session)
        elif text_lower in ["cancelar", "cancelado", "no", "cancel"]:
            return await self._handle_cancel_command(user_id, chat_id, session)

        keyboard = get_supplier_not_found_keyboard()
        msg = "Responde con: CREAR PROVEEDOR, CORREGIR o CANCELAR."
        await self._send_telegram_message(chat_id, msg, reply_markup=keyboard)
        return {"success": True, "awaiting_input": True}

    async def _handle_supplier_creation_callback(self, user_id: int, chat_id: int, session: dict) -> dict:
        """Handle supplier creation after user confirmation."""
        context = session.get("context", {})
        pending_data = context.get("pending_invoice_data")

        if not pending_data:
            return {"success": False, "error": "No pending invoice data"}

        file_content = pending_data["file_content"]
        filename = pending_data["filename"]
        result = pending_data["result"]

        tax_id = result.get("tax_id", "desconocido")
        supplier_name = result.get("invoice", {}).get("supplier", {}).get("name", "Proveedor desconocido")
        address = result.get("invoice", {}).get("supplier", {}).get("address")

        # Create supplier in Dolibarr
        try:
            from app.services.invoice_integration_service import InvoiceIntegrationService

            service = InvoiceIntegrationService()
            async with service as s:
                supplier = await s.create_supplier(name=supplier_name, tax_id=tax_id, address=address)
            supplier_id = supplier.get("id")

            if not supplier_id:
                return {"success": False, "error": "Failed to create supplier - no ID returned"}

            logger.info("supplier_created", supplier_id=supplier_id, tax_id=tax_id)

            # Re-process invoice with new supplier
            process_result = await self.invoice_agent.process_invoice(file_content, filename)

            if not process_result.get("success"):
                return {"success": False, "error": f"Error re-procesando: {process_result.get('error')}"}

            # Create draft for approval
            correlation_id = str(uuid.uuid4())
            from app.services.invoice_draft_service import get_invoice_draft_service

            draft_service = await get_invoice_draft_service()
            draft = await draft_service.create_draft(
                correlation_id=correlation_id,
                telegram_user_id=user_id,
                telegram_chat_id=chat_id,
                telegram_message_id=0,
                telegram_update_id=0,
                file_content=file_content,
                file_path=process_result["file_path"],
                final_path=process_result["final_path"],
                supplier_tax_id=process_result["invoice"]["supplier"]["tax_id"],
                supplier_name=process_result["invoice"]["supplier"]["name"],
                invoice_data=process_result["invoice"],
                summary=process_result["summary"],
            )

            await self.conversation_manager.update_session(
                user_id,
                chat_id,
                workflow_step=WorkflowStep.INVOICE_AWAITING_APPROVAL,
                context={
                    "invoice_draft_id": draft.draft_id,
                    "invoice_correlation_id": correlation_id,
                },
            )

            summary = process_result["summary"]
            validation_status = "OK" if not process_result.get("requires_review") else "REQUIERE REVISIÓN"
            text = (
                f"✅ Proveedor creado correctamente (ID: {supplier_id})\n\n"
                f"{get_invoice_approval_text({**summary, 'validation_status': validation_status})}"
            )
            keyboard = get_invoice_approval_keyboard()
            await self._send_telegram_message(chat_id, text, reply_markup=keyboard)

            return {"success": True, "workflow_step": WorkflowStep.INVOICE_AWAITING_APPROVAL, "awaiting_input": True}

        except Exception as e:
            logger.error("supplier_creation_failed", error=str(e))
            return {"success": False, "error": f"Error creando proveedor: {str(e)}"}

    async def _start_dog_workflow(self, user_id: int, chat_id: int, session: dict) -> dict:
        """Start dog management workflow - delegate to DogIntakeAgent."""
        await self.conversation_manager.update_session(
            user_id,
            chat_id,
            workflow_type=WorkflowType.DOG_MANAGEMENT,
            workflow_step=WorkflowStep.DOG_AWAITING_NAME,
            context={},
        )

        # Trigger DogIntakeAgent to start the intake flow
        await self.dog_intake_agent.process_message(
            {
                "chat_id": chat_id,
                "user_id": user_id,
                "text": "",
                "message": {},
            }
        )

        keyboard = get_dog_management_keyboard()
        text = "🐶 <b>Gestión de perros</b>\n\n¿Qué quieres hacer?"
        await self._send_telegram_message(chat_id, text, reply_markup=keyboard)

        workflow_id = session.get("session_id", f"wf-{chat_id}-{user_id}")
        return {
            "success": True,
            "workflow_type": WorkflowType.DOG_MANAGEMENT,
            "workflow_step": WorkflowStep.DOG_AWAITING_NAME,
            "message": text,
            "awaiting_input": True,
            "workflow_id": workflow_id,
        }

    async def _handle_dog_workflow(
        self, user_id: int, chat_id: int, session: dict, tg_message: dict | None, text: str
    ) -> dict:
        """Handle dog workflow - delegate to DogIntakeAgent."""
        # Use legacy active_workflows for dog intake internal state
        workflow_id = f"wf-{chat_id}-{user_id}"

        if workflow_id not in self.active_workflows:
            self.active_workflows[workflow_id] = {
                "workflow_id": workflow_id,
                "chat_id": chat_id,
                "user_id": user_id,
                "step": WorkflowStep.DOG_INTAKE,
                "status": "in_progress",
                "created_at": datetime.utcnow().isoformat(),
                "dog_id": None,
                "dog_internal_id": None,
                "media_items": [],
            }

        workflow = self.active_workflows[workflow_id]

        result = await self.dog_intake_agent.process_message(
            {
                "chat_id": chat_id,
                "user_id": user_id,
                "text": text,
                "message": tg_message,
            }
        )

        if result.get("completed") and result.get("dog"):
            workflow["dog_id"] = result["dog"]["id"]
            workflow["dog_internal_id"] = result["dog"]["internal_id"]
            workflow["step"] = WorkflowStep.DOG_AWAITING_MEDIA
            workflow["status"] = "awaiting_media"

            await self.conversation_manager.update_session(
                user_id, chat_id, workflow_step=WorkflowStep.DOG_AWAITING_MEDIA
            )

            text = f"Perro {result['dog']['internal_id']} creado. Ahora envía fotos/vídeos."
            keyboard = get_cancel_keyboard()
            await self._send_telegram_message(chat_id, text, reply_markup=keyboard)

            return {
                "success": True,
                "workflow_id": workflow_id,
                "step": workflow["step"],
                "message": text,
                "dog": result["dog"],
                "completed": True,
                "awaiting_input": True,
            }

        if result.get("completed") and not result.get("dog"):
            # Cancelled
            if workflow_id in self.active_workflows:
                del self.active_workflows[workflow_id]
            await self.conversation_manager.clear_workflow(user_id, chat_id)
            return await self._send_workflow_selection(
                user_id, chat_id, session, "Ingreso cancelado. ¿Qué quieres hacer?"
            )

        return {
            "success": True,
            "workflow_id": workflow_id,
            "step": workflow["step"],
            "message": result.get("message", "Continúa..."),
            "awaiting_input": True,
        }

    async def _handle_dog_callback(self, user_id: int, chat_id: int, session: dict, callback_data: str) -> dict:
        """Handle dog management callbacks."""
        if callback_data == "dog:new":
            return await self._start_dog_intake(user_id, chat_id, session)
        elif callback_data == "dog:list":
            text = "📋 Listado de perros - funcionalidad pendiente"
            await self._send_telegram_message(chat_id, text)
            return {"success": True, "message": text, "awaiting_input": True}
        elif callback_data == "action:menu":
            return await self._send_workflow_selection(user_id, chat_id, session)
        return {"success": True, "message": "Acción perro no reconocida", "awaiting_input": True}

    async def _start_dog_intake(self, user_id: int, chat_id: int, session: dict) -> dict:
        """Start new dog intake."""
        workflow_id = f"wf-{chat_id}-{user_id}"
        self.active_workflows[workflow_id] = {
            "workflow_id": workflow_id,
            "chat_id": chat_id,
            "user_id": user_id,
            "step": WorkflowStep.DOG_INTAKE,
            "status": "in_progress",
            "created_at": datetime.utcnow().isoformat(),
            "dog_id": None,
            "dog_internal_id": None,
            "media_items": [],
        }

        await self.conversation_manager.update_session(user_id, chat_id, workflow_step=WorkflowStep.DOG_AWAITING_NAME)

        result = await self.dog_intake_agent.process_message(
            {
                "chat_id": chat_id,
                "user_id": user_id,
                "text": "",
                "message": {},
            }
        )

        text = result.get("message", "¡Nuevo ingreso de perro! ¿Cuál es el nombre del perro?")
        keyboard = get_cancel_keyboard()
        await self._send_telegram_message(chat_id, text, reply_markup=keyboard)

        return {"success": True, "message": text, "awaiting_input": True}

    # =========================================================================
    # HELPER METHODS - Legacy internal workflows (non-Telegram)
    # =========================================================================

    async def _get_dog_info(self, dog_id: int) -> dict | None:
        """Fetch dog info from internal API."""
        try:
            resp = await self.api_client.get(f"/dogs/{dog_id}", headers={"Authorization": f"Bearer {self.api_key}"})
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            logger.error("failed_to_get_dog", dog_id=dog_id, error=str(e))
        return None

    async def _api_post(self, path: str, data: dict = None) -> dict:
        """POST to internal API with auth."""
        try:
            resp = await self.api_client.post(path, json=data, headers={"Authorization": f"Bearer {self.api_key}"})
            if resp.status_code in (200, 201, 202):
                return {"success": True, "data": resp.json()}
            return {"success": False, "error": resp.text}
        except Exception as e:
            logger.error("api_post_failed", path=path, error=str(e))
            return {"success": False, "error": str(e)}

    async def _api_get(self, path: str) -> dict:
        """GET from internal API with auth."""
        try:
            resp = await self.api_client.get(path, headers={"Authorization": f"Bearer {self.api_key}"})
            if resp.status_code == 200:
                return {"success": True, "data": resp.json()}
            return {"success": False, "error": resp.text}
        except Exception as e:
            logger.error("api_get_failed", path=path, error=str(e))
            return {"success": False, "error": str(e)}

    async def _monitor_workflows(self):
        """Monitor workflows for timeouts/stale states."""
        while self.status == "running":
            await asyncio.sleep(60)
            now = datetime.utcnow()

            for wf_id, workflow in list(self.active_workflows.items()):
                # Check for stale workflows (>1 hour in same step)
                created = datetime.fromisoformat(workflow["created_at"])
                if (now - created).total_seconds() > 3600:
                    if workflow["status"] in [
                        "awaiting_media",
                        "awaiting_content_approval",
                        "awaiting_publish_approval",
                    ]:
                        logger.warning("workflow_stale", workflow_id=wf_id, step=workflow["step"])

    async def _cleanup_completed_workflows(self):
        """Clean up old completed workflows."""
        while self.status == "running":
            await asyncio.sleep(3600)  # Every hour

            now = datetime.utcnow()
            to_remove = []

            for wf_id, workflow in self.active_workflows.items():
                if workflow["status"] == "completed":
                    completed_at = datetime.fromisoformat(workflow.get("completed_at", workflow["created_at"]))
                    if (now - completed_at).total_seconds() > 86400:  # 24 hours
                        to_remove.append(wf_id)

            for wf_id in to_remove:
                del self.active_workflows[wf_id]
                logger.info("workflow_cleaned", workflow_id=wf_id)

    def get_workflow_status(self, workflow_id: str) -> dict | None:
        """Get current workflow status."""
        return self.active_workflows.get(workflow_id)

    def list_active_workflows(self) -> list[dict]:
        """List all active workflows."""
        return list(self.active_workflows.values())


def create_supervisor_agent(config: dict) -> SupervisorAgent:
    """Factory function."""
    return SupervisorAgent(config)
