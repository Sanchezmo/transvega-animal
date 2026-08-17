"""Telegram webhook routes for dog intake - integrated with SupervisorAgent."""

import hmac
import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from agents.supervisor.agent import create_supervisor_agent
from app.core.config import settings
from app.core.telegram_client import TelegramAPIError, TelegramClient
from app.dependencies.rate_limit import (
    save_telegram_idempotency_result,
    telegram_idempotency_dependency,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["telegram"])

# Initialize the supervisor agent with full config
agent_config = {
    "INTERNAL_API_URL": getattr(settings, "INTERNAL_API_URL", "http://localhost:8000"),
    "OLLAMA_ENDPOINT": getattr(settings, "OLLAMA_ENDPOINT", "http://ollama:11434"),
    "OLLAMA_MODEL": getattr(settings, "OLLAMA_MODEL", "llama3.1:8b"),
    "OLLAMA_VISION_MODEL": getattr(settings, "OLLAMA_VISION_MODEL", "llava:7b"),
    "NVIDIA_API_KEY": getattr(settings, "NVIDIA_API_KEY", ""),
    "NVIDIA_BASE_URL": getattr(settings, "NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
    "AGENT_API_KEY_SUPERVISOR": getattr(settings, "AGENT_API_KEY_SUPERVISOR", ""),
    "AGENT_API_KEY_DOG_INTAKE": getattr(settings, "AGENT_API_KEY_DOG_INTAKE", ""),
}
supervisor_agent = create_supervisor_agent(config=agent_config)

# Initialize Telegram client for outbound messages
telegram_client = TelegramClient()


def _verify_webhook_secret(provided: str | None) -> bool:
    """Verify the Telegram webhook secret using constant-time comparison."""
    expected = settings.TELEGRAM_WEBHOOK_SECRET
    if not expected:
        # In development, allow missing secret; in production, require it
        return settings.ENVIRONMENT == "development"
    if not provided:
        return False
    return hmac.compare_digest(provided, expected)


async def _require_webhook_secret(
    x_telegram_bot_api_secret_token: str | None = Header(None),
):
    """Dependency to verify webhook secret."""
    if not _verify_webhook_secret(x_telegram_bot_api_secret_token):
        logger.warning("Invalid or missing webhook secret token")
        raise HTTPException(status_code=403, detail="Invalid secret token")


def _extract_chat_id(update: dict) -> int | None:
    """Extract chat_id from Telegram update (message or callback_query)."""
    # Try message first
    message = update.get("message") or update.get("edited_message")
    if message:
        chat = message.get("chat")
        if chat:
            return chat.get("id")

    # Try callback_query
    callback_query = update.get("callback_query")
    if callback_query:
        chat = callback_query.get("message", {}).get("chat")
        if chat:
            return chat.get("id")

    return None


def _extract_user_id(update: dict) -> int | None:
    """Extract user_id from Telegram update."""
    message = update.get("message") or update.get("edited_message")
    if message:
        return message.get("from", {}).get("id")

    callback_query = update.get("callback_query")
    if callback_query:
        return callback_query.get("from", {}).get("id")

    return None


async def _send_telegram_response(chat_id: int, text: str, reply_markup: dict | None = None) -> bool:
    """Send response message via Telegram Bot API.

    Returns True if sent successfully, False otherwise.
    Does not raise exceptions - logs failures instead.
    """
    try:
        await telegram_client.start()
        await telegram_client.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
        logger.info("telegram_outbound_sent chat_id=%s text_length=%d", chat_id, len(text))
        return True
    except TelegramAPIError as e:
        logger.error("telegram_outbound_failed chat_id=%s error=%s", chat_id, str(e))
        return False
    except Exception as e:
        logger.error("telegram_outbound_failed chat_id=%s error=%s", chat_id, str(e))
        return False
    finally:
        await telegram_client.close()


@router.post("/webhook")
@router.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str = Header(None),
    _verify: None = Depends(_require_webhook_secret),
    _idempotency: None = Depends(telegram_idempotency_dependency),
) -> dict[str, Any]:
    """
    Receive updates from Telegram and process them via the SupervisorAgent
    which orchestrates: DogIntake → MediaPipeline → Content → Publishing
    AND: Invoice Processing → Dolibarr.

    The SupervisorAgent handles all outbound Telegram messages (including inline keyboards)
    via its internal TelegramClient. This endpoint just processes and returns 200 OK.
    """
    try:
        update = await request.json()
    except Exception as e:
        logger.error("Failed to parse JSON: %s", e)
        raise HTTPException(status_code=400, detail="Invalid JSON")

    update_id = update.get("update_id")
    logger.info("telegram_update_received update_id=%s", update_id)

    # Idempotency is handled by telegram_idempotency_dependency using Redis
    # The update_id is available in request.state.telegram_update_id

    # Process the update with the supervisor agent
    # The supervisor handles ALL outbound Telegram communication
    result = await supervisor_agent.handle_telegram_message(update)

    # Always return 200 OK to Telegram to avoid retries
    if not result.get("success"):
        logger.warning("Update processing failed: %s", result.get("error"))
    else:
        logger.info("telegram_update_processed message=%s", result.get("message"))

    # Save idempotency result (success/failure) for retry handling
    try:
        # Get Redis from app state (set during startup)
        redis = request.app.state.redis_client
        if redis:
            await save_telegram_idempotency_result(
                request=request,
                redis=redis,
                resource_id=update_id,
                response_data=result,
                status_code=200,
                success=result.get("success", False),
            )
    except Exception as e:
        logger.warning("Failed to save idempotency result: %s", e)

    return JSONResponse(status_code=200, content=result)


@router.post("/media")
async def telegram_media_upload(
    request: Request,
    x_telegram_bot_api_secret_token: str = Header(None),
    _verify: None = Depends(_require_webhook_secret),
) -> dict[str, Any]:
    """
    Handle media uploads (photos/videos) for an active workflow.
    Expected form data: workflow_id, file (multipart), purpose (optional).
    """
    try:
        form = await request.form()
        workflow_id = form.get("workflow_id")
        file_obj = form.get("file")
        purpose = form.get("purpose", "original")

        if not workflow_id or not file_obj:
            raise HTTPException(status_code=400, detail="Missing workflow_id or file")

        file_content = await file_obj.read()
        filename = file_obj.filename or "upload.jpg"

        result = await supervisor_agent.handle_media_upload(
            workflow_id=workflow_id,
            file_content=file_content,
            filename=filename,
            purpose=purpose,
        )

        if not result.get("success"):
            logger.warning("Media upload failed: %s", result.get("error"))

        return JSONResponse(status_code=200, content=result)

    except Exception as e:
        logger.error("Media upload error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/workflow/{workflow_id}/finalize-media")
async def finalize_media_selection(
    workflow_id: str,
    x_telegram_bot_api_secret_token: str = Header(None),
    _verify: None = Depends(_require_webhook_secret),
) -> dict[str, Any]:
    """Trigger media selection and variant generation after all uploads."""
    result = await supervisor_agent.finalize_media_selection(workflow_id)

    if not result.get("success"):
        logger.warning("Finalize media failed: %s", result.get("error"))

    return JSONResponse(status_code=200, content=result)


@router.post("/workflow/{workflow_id}/approve-content")
async def approve_content(
    workflow_id: str,
    request: Request,
    x_telegram_bot_api_secret_token: str = Header(None),
    _verify: None = Depends(_require_webhook_secret),
) -> dict[str, Any]:
    """Human approval for generated content."""
    body = await request.json()
    approved = body.get("approved", True)
    feedback = body.get("feedback", "")

    result = await supervisor_agent.approve_content(workflow_id, approved, feedback)

    if not result.get("success"):
        logger.warning("Content approval failed: %s", result.get("error"))

    return JSONResponse(status_code=200, content=result)


@router.post("/workflow/{workflow_id}/approve-publish")
async def approve_publish(
    workflow_id: str,
    request: Request,
    x_telegram_bot_api_secret_token: str = Header(None),
    _verify: None = Depends(_require_webhook_secret),
) -> dict[str, Any]:
    """Human approval to publish the listing."""
    body = await request.json()
    approved = body.get("approved", True)
    feedback = body.get("feedback", "")

    result = await supervisor_agent.approve_publication(workflow_id, approved, feedback)

    if not result.get("success"):
        logger.warning("Publish approval failed: %s", result.get("error"))

    return JSONResponse(status_code=200, content=result)


@router.get("/workflow/{workflow_id}")
async def get_workflow_status(
    workflow_id: str,
    x_telegram_bot_api_secret_token: str = Header(None),
    _verify: None = Depends(_require_webhook_secret),
) -> dict[str, Any]:
    """Get current workflow status."""
    workflow = supervisor_agent.get_workflow_status(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    return JSONResponse(status_code=200, content={"success": True, "workflow": workflow})


@router.get("/workflows")
async def list_workflows(
    x_telegram_bot_api_secret_token: str = Header(None),
    _verify: None = Depends(_require_webhook_secret),
) -> dict[str, Any]:
    """List all active workflows."""
    workflows = supervisor_agent.list_active_workflows()
    return JSONResponse(status_code=200, content={"success": True, "workflows": workflows})
