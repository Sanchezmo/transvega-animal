"""Telegram webhook routes for dog intake."""
import logging
from typing import Any, Dict

from fastapi import APIRouter, Header, HTTPException, Request, Status
from fastapi.responses import JSONResponse

from app.agents.dog_intake.agent import DogIntakeAgent
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telegram", tags=["telegram"])

# Initialize the agent with the same config used elsewhere
# In a real setup, we might get the config from a dependency injection container.
# For simplicity, we create a minimal config dict.
agent_config = {
    "INTERNAL_API_URL": settings.INTERNAL_API_URL if hasattr(settings, "INTERNAL_API_URL") else "http://localhost:8000",
}
intake_agent = DogIntakeAgent(config=agent_config)


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str = Header(None),
) -> Dict[str, Any]:
    """
    Receive updates from Telegram and process them via the dog intake agent.
    """
    # Optional: verify secret token if set in settings
    if hasattr(settings, "TELEGRAM_WEBHOOK_SECRET") and settings.TELEGRAM_WEBHOOK_SECRET:
        if x_telegram_bot_api_secret_token != settings.TELEGRAM_WEBHOOK_SECRET:
            logger.warning("Invalid webhook secret token")
            raise HTTPException(status_code=403, detail="Invalid secret token")

    try:
        update = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse JSON: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON")

    logger.info(f"Received update: {update.get('update_id')}")

    # Process the update with the intake agent
    result = await intake_agent.handle_telegram_update(update)

    # Always return 200 OK to Telegram to avoid retries
    # But we can include the result in the body for logging
    if not result.get("success"):
        logger.warning(f"Update processing failed: {result.get('error')}")
    else:
        logger.info(f"Update processed successfully: {result.get('message')}")

    return JSONResponse(status_code=200, content=result)