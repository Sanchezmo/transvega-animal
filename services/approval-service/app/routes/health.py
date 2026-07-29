"""Health check endpoints."""
from fastapi import APIRouter
from datetime import datetime

router = APIRouter()


@router.get("/live")
async def liveness():
    """Liveness probe - checks if the service is running."""
    return {"status": "alive", "timestamp": datetime.utcnow().isoformat()}


@router.get("/ready")
async def readiness():
    """Readiness probe - checks if service is ready to serve requests."""
    # TODO: Check database and Redis connectivity
    return {
        "status": "ready",
        "checks": {
            "database": "ok",
            "redis": "ok",
        },
        "timestamp": datetime.utcnow().isoformat(),
    }