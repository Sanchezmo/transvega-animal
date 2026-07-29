"""
Dependencias de rate limiting e idempotencia.
"""
from typing import Optional
from fastapi import Depends, HTTPException, Request, status
from redis.asyncio import Redis
import hashlib
import json
import time

from app.core.config import get_settings
from app.core.database import get_redis
from app.core.exceptions import RateLimitException, IdempotencyException


settings = get_settings()


async def get_redis_client() -> Redis:
    """Obtener cliente Redis."""
    return await get_redis()


async def rate_limit_dependency(
    request: Request,
    redis: Redis = Depends(get_redis_client),
):
    """
    Rate limiting por IP + Agent.
    Límite configurable por ventana de tiempo.
    """
    settings = get_settings()
    
    # Identificar cliente (IP + Agent si disponible)
    client_ip = request.client.host if request.client else "unknown"
    agent_header = request.headers.get("X-Agent-ID", "anonymous")
    client_key = f"ratelimit:{agent_header}:{client_ip}"
    
    current = await redis.incr(client_key)
    
    if current == 1:
        await redis.expire(client_key, settings.RATE_LIMIT_WINDOW_SECONDS)
    
    if current > settings.RATE_LIMIT_REQUESTS:
        ttl = await redis.ttl(client_key)
        raise RateLimitException(
            limit=settings.RATE_LIMIT_REQUESTS,
            window=settings.RATE_LIMIT_WINDOW_SECONDS,
            retry_after=ttl if ttl > 0 else settings.RATE_LIMIT_WINDOW_SECONDS,
        )
    
    # Headers informativos
    request.state.rate_limit_remaining = settings.RATE_LIMIT_REQUESTS - current
    request.state.rate_limit_reset = int(time.time()) + settings.RATE_LIMIT_WINDOW_SECONDS


async def idempotency_dependency(
    request: Request,
    redis: Redis = Depends(get_redis_client),
):
    """
    Validación de idempotencia para operaciones mutables.
    
    Requiere header: Idempotency-Key: <uuid>
    Guarda resultado por 24h para evitar duplicados.
    """
    idempotency_key = request.headers.get("Idempotency-Key")
    
    # Solo aplicar en métodos mutables
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        if not idempotency_key:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Header Idempotency-Key requerido para operaciones mutables",
            )
        
        # Verificar si ya existe
        cache_key = f"idempotency:{idempotency_key}"
        existing = await redis.get(cache_key)
        
        if existing:
            data = json.loads(existing)
            raise IdempotencyException(
                key=idempotency_key,
                existing_id=data.get("resource_id", "unknown"),
            )
        
        # Guardar placeholder (se actualizará con resultado real)
        await redis.setex(
            cache_key,
            settings.IDEMPOTENCY_TTL_HOURS * 3600,
            json.dumps({"status": "processing", "started_at": time.time()}),
        )
        
        request.state.idempotency_key = idempotency_key
        request.state.idempotency_cache_key = cache_key
    else:
        request.state.idempotency_key = None
        request.state.idempotency_cache_key = None


async def save_idempotency_result(
    request: Request,
    redis: Redis,
    resource_id: str,
    response_data: dict,
    status_code: int = 200,
):
    """Guardar resultado de operación idempotente."""
    if hasattr(request.state, "idempotency_cache_key") and request.state.idempotency_cache_key:
        await redis.setex(
            request.state.idempotency_cache_key,
            settings.IDEMPOTENCY_TTL_HOURS * 3600,
            json.dumps({
                "status": "completed",
                "resource_id": resource_id,
                "response": response_data,
                "status_code": status_code,
                "completed_at": time.time(),
            }),
        )