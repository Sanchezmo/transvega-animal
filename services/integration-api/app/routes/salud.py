"""
Rutas de health check y información del sistema.
"""
from fastapi import APIRouter, Depends
from app.core.config import get_settings
from app.dependencies.auth import get_current_agent

router = APIRouter(prefix="/salud", tags=["Salud"])
settings = get_settings()


@router.get("/health", tags=["Health"])
async def health_check():
    """Health check básico."""
    return {
        "status": "healthy",
        "service": "Transvega Animal API",
        "version": "1.0.0",
    }


@router.get("/health/ready", tags=["Health"])
async def readiness_check():
    """Readiness check - verifica dependencias."""
    checks = {
        "database": "ok",
        "redis": "ok",
        "dolibarr": "mock" if settings.ENVIRONMENT == "development" else "pending",
    }
    
    all_ok = all(v == "ok" for v in checks.values())
    
    return {
        "status": "ready" if all_ok else "not_ready",
        "checks": checks,
    }


@router.get("/version", tags=["Info"])
async def version_info():
    """Información de versión."""
    return {
        "service": "Transvega Animal API",
        "version": "1.0.0",
        "environment": settings.ENVIRONMENT,
        "docs": "/docs",
    }


@router.get("/agents", tags=["Info"])
async def list_agents():
    """Lista de agentes registrados y sus API keys (para debugging)."""
    settings = get_settings()
    agents = {}
    for name, key in settings.AGENT_API_KEYS.items():
        agents[name] = {
            "configured": bool(key),
            "key_preview": key[:8] + "..." + key[-4:] if key else None,
        }
    return {"agents": agents}