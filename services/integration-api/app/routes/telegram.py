"""Telegram webhook routes for dog intake - integrated with SupervisorAgent."""

import hmac
import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from app.agents.supervisor.agent import create_supervisor_agent
from app.core.config import settings

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
}
supervisor_agent = create_supervisor_agent(config=agent_config)


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


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str = Header(None),
    _verify: None = Depends(_require_webhook_secret),
) -> dict[str, Any]:
    """
    Receive updates from Telegram and process them via the SupervisorAgent
    which orchestrates: DogIntake → MediaPipeline → Content → Publishing.
    """
    try:
        update = await request.json()
    except Exception as e:
        logger.error("Failed to parse JSON: %s", e)
        raise HTTPException(status_code=400, detail="Invalid JSON")

    logger.info("Received update: %s", update.get("update_id"))

    # Process the update with the supervisor agent
    result = await supervisor_agent.handle_telegram_message(update)

    # Always return 200 OK to Telegram to avoid retries
    if not result.get("success"):
        logger.warning("Update processing failed: %s", result.get("error"))
    else:
        logger.info("Update processed successfully: %s", result.get("message"))

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
