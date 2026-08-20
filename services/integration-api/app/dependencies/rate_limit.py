"""
Dependencias de rate limiting e idempotencia.
"""

import json
import time

import structlog
from fastapi import Depends, HTTPException, Request, status
from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.database import get_redis
from app.core.exceptions import IdempotencyException, RateLimitException

settings = get_settings()
logger = structlog.get_logger()


async def rate_limit_dependency(
    request: Request,
    redis: Redis = Depends(get_redis),
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
    redis: Redis = Depends(get_redis),
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


async def telegram_idempotency_dependency(
    request: Request,
    redis: Redis = Depends(get_redis),
):
    """
    Validación de idempotencia para Telegram webhook updates.

    Usa el update_id de Telegram como clave de idempotencia.
    Clave en Redis: telegram:update:<update_id>
    TTL configurable via TELEGRAM_UPDATE_IDEMPOTENCY_TTL_HOURS (default 24h).

    Behavior:
    - Atomic SET NX: only first request wins
    - "processing" state blocks retries (prevents Telegram retry loops)
    - Only "failed" state allows retry after TTL
    """
    # Extract update_id from request body
    body = await request.body()
    try:
        import json as json_lib

        update = json_lib.loads(body)
    except Exception:
        # If JSON parsing fails, allow the request to continue (endpoint will handle 400)
        return

    update_id = update.get("update_id")
    if not update_id:
        return

    idempotency_key = f"telegram:update:{update_id}"
    cache_key = f"idempotency:{idempotency_key}"
    ttl_hours = getattr(settings, "TELEGRAM_UPDATE_IDEMPOTENCY_TTL_HOURS", 24)
    ttl_seconds = ttl_hours * 3600

    # ATOMIC check-and-set using SET NX
    # Only proceed if key doesn't exist (first request wins)
    acquired = await redis.set(
        cache_key,
        json_lib.dumps({"status": "processing"}),
        nx=True,
        ex=ttl_seconds,
    )

    if not acquired:
        # Key already exists - check its status
        existing = await redis.get(cache_key)
        if existing:
            try:
                data = json_lib.loads(existing)
                status = data.get("status")
                if status == "completed":
                    # Already successfully processed - block with 200 OK (idempotent)
                    logger.info(
                        "telegram_update_duplicate_suppressed",
                        update_id=update_id,
                        status=status,
                    )
                    raise IdempotencyException(
                        key=idempotency_key,
                        existing_id=update_id,
                    )
                elif status == "failed":
                    # Previous attempt failed - allow ONE retry by deleting the key
                    # This implements a single-retry policy for failed attempts
                    logger.info(
                        "telegram_update_retry_allowed",
                        update_id=update_id,
                        previous_status=status,
                    )
                    await redis.delete(cache_key)
                    # Fall through to acquire the lock
                    acquired = await redis.set(
                        cache_key,
                        json_lib.dumps({"status": "processing"}),
                        nx=True,
                        ex=ttl_seconds,
                    )
                    if not acquired:
                        # Race condition - another request got the retry
                        logger.info(
                            "telegram_update_retry_race",
                            update_id=update_id,
                        )
                        raise IdempotencyException(
                            key=idempotency_key,
                            existing_id=update_id,
                        )
                else:
                    # Status is "processing" - BLOCK retry (prevents Telegram retry loops)
                    logger.info(
                        "telegram_update_retry_blocked",
                        update_id=update_id,
                        status=status,
                    )
                    raise IdempotencyException(
                        key=idempotency_key,
                        existing_id=update_id,
                    )
            except IdempotencyException:
                raise
            except Exception:
                # If JSON parsing fails, treat as processing
                logger.warning(
                    "telegram_update_idempotency_parse_failed",
                    update_id=update_id,
                )
                raise IdempotencyException(
                    key=idempotency_key,
                    existing_id=update_id,
                )

    # Store the parsed update in request.state so the endpoint can use it
    # without re-reading the consumed body stream
    request.state.telegram_update = update
    request.state.telegram_update_id = update_id
    request.state.telegram_idempotency_key = f"telegram:update:{update_id}"
    request.state.telegram_idempotency_cache_key = f"idempotency:telegram:update:{update_id}"
    request._body = body


async def save_telegram_idempotency_result(
    request: Request,
    redis: Redis,
    resource_id: str,
    response_data: dict,
    status_code: int = 200,
    success: bool = True,
):
    """Guardar resultado de operación idempotente de Telegram."""
    if hasattr(request.state, "telegram_idempotency_cache_key") and request.state.telegram_idempotency_cache_key:
        ttl_hours = getattr(settings, "TELEGRAM_UPDATE_IDEMPOTENCY_TTL_HOURS", 24)
        ttl_seconds = ttl_hours * 3600
        import json as json_lib

        await redis.setex(
            request.state.telegram_idempotency_cache_key,
            ttl_seconds,
            json_lib.dumps(
                {
                    "status": "completed" if success else "failed",
                    "resource_id": resource_id,
                    "response": response_data,
                    "status_code": status_code,
                    "completed_at": time.time(),
                }
            ),
        )


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
            json.dumps(
                {
                    "status": "completed",
                    "resource_id": resource_id,
                    "response": response_data,
                    "status_code": status_code,
                    "completed_at": time.time(),
                }
            ),
        )
