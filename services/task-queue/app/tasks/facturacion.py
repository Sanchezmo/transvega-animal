"""
Tareas Celery para facturación.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import tempfile
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import redis.asyncio
    import asyncpg

import structlog
from celery import shared_task

logger = structlog.get_logger()


def _compute_file_hash(file_content: bytes) -> str:
    """Compute SHA256 hash of file content for idempotency."""
    return hashlib.sha256(file_content).hexdigest()


async def _check_idempotency_redis(
    correlation_id: str,
    file_hash: str | None = None,
    redis: redis.asyncio.Redis | None = None,
) -> tuple[bool, str | None]:
    """
    Check if invoice was already processed using Redis idempotency keys.

    Args:
        correlation_id: Unique correlation ID for the invoice processing
        file_hash: Optional SHA256 hash of file content for file-based idempotency
        redis: Optional Redis client (for testing). If not provided, gets from app.

    Returns:
        (should_skip, existing_result_json)
        - should_skip: True if processing should be skipped (already processed)
        - existing_result_json: Cached result if available, None otherwise
    """
    try:
        if redis is None:
            from app.core.database import get_redis_client
            redis = await get_redis_client()

        # Check correlation_id result cache (1 hour TTL)
        result_key = f"invoice_result:{correlation_id}"
        cached_result = await redis.get(result_key)
        if cached_result:
            logger.info("idempotency_hit_correlation_id", correlation_id=correlation_id)
            return True, cached_result

        # Check file_hash idempotency key (2 hours TTL, matches supervisor agent)
        if file_hash:
            file_key = f"invoice:file:{file_hash}"
            acquired = await redis.set(file_key, "processed", nx=True, ex=7200)
            if not acquired:
                logger.info("idempotency_hit_file_hash", file_hash=file_hash[:16] + "...")
                # Try to get cached result for this file
                cached_result = await redis.get(f"invoice_result:file:{file_hash}")
                return True, cached_result
            # Store file_hash -> correlation_id mapping for future lookups
            await redis.setex(f"invoice_result:file:{file_hash}", 7200, correlation_id)

        return False, None
    except Exception as e:
        logger.warning("idempotency_check_failed", error=str(e))
        # Non-blocking - continue processing if Redis check fails
        return False, None


async def _check_draft_status(
    correlation_id: str,
    pool: asyncpg.Pool | None = None,
) -> str | None:
    """
    Check invoice draft status in PostgreSQL.

    Args:
        correlation_id: Unique correlation ID for the invoice processing
        pool: Optional database pool (for testing). If not provided, gets from app.

    Returns status if draft exists, None if not found.
    Statuses that should skip processing:
    - PENDING_APPROVAL: already processed, awaiting human approval
    - APPROVED: approved, being registered in Dolibarr
    - REGISTERED: successfully registered in Dolibarr
    - REJECTED: cancelled by user
    - REQUIRES_REVIEW: needs review but already processed
    - REQUIRES_CLEANUP: Dolibarr invoice created but attachment failed
    - PENDING_SUPPLIER: supplier not found, awaiting decision
    """
    try:
        if pool is None:
            from app.core.database import get_db_pool
            pool = await get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT status FROM invoice_drafts WHERE correlation_id = $1",
                correlation_id
            )
            if row:
                return str(row["status"])
    except Exception as e:
        logger.warning("draft_status_check_failed", correlation_id=correlation_id, error=str(e))
    return None


SKIP_STATUSES = {
    "PENDING_APPROVAL",
    "APPROVED",
    "REGISTERED",
    "REJECTED",
    "REQUIRES_REVIEW",
    "REQUIRES_CLEANUP",
    "PENDING_SUPPLIER",
}


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def crear_factura_borrador(self, factura_data: dict):
    """
    Crear factura en borrador en Dolibarr.

    factura_data debe contener:
    - thirdparty_id
    - date
    - lines: lista de líneas
    - payment_term_id, cond_reglement_id, mode_reglement_id (opcional)
    """
    logger.info("creando_factura_borrador", factura_data=factura_data)

    try:
        # TODO: Implementar creación via Dolibarr API
        # 1. Validar datos
        # 2. Calcular totales
        # 3. Crear en Dolibarr
        # 4. Retornar ID y referencia

        # Calcular totales
        lines = factura_data.get("lines", [])
        total_ht = Decimal("0")
        total_tva = Decimal("0")

        for line in lines:
            qty = Decimal(str(line.get("qty", 1)))
            unit_price = Decimal(str(line.get("unit_price", 0)))
            discount = Decimal(str(line.get("discount_percent", 0)))
            vat_rate = Decimal(str(line.get("vat_rate", 21)))

            line_ht = qty * unit_price * (Decimal("1") - discount / Decimal("100"))
            line_tva = line_ht * (vat_rate / Decimal("100"))

            total_ht += line_ht
            total_tva += line_tva

        total_ht + total_tva

        logger.info(
            "factura_calculada",
            total_ht=float(total_ht),
            total_tva=float(total_tva),
            total_ttc=float(total_ht + total_tva),
        )

        return {
            "success": True,
            "factura_id": 1,
            "ref": f"FAC-{date.today().year}-000001",
            "total_ht": float(total_ht),
            "total_tva": float(total_tva),
            "total_ttc": float(total_ht + total_tva),
        }

    except Exception as exc:
        logger.error("error_creando_factura", error=str(exc))
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def validar_factura(self, factura_id: int):
    """
    Validar factura (pasar de borrador a validada).

    Requiere aprobación humana previa.
    """
    logger.info("validando_factura", factura_id=factura_id)

    try:
        # Verificar estado
        # existing = await dolibarr.get_invoice(factura_id)
        # if existing["status"] != 0:
        #     raise ValueError("Solo facturas en borrador pueden validarse")

        # Validar líneas
        # if not existing["lines"]:
        #     raise ValueError("Factura sin líneas no puede validarse")

        # TODO: Validar via Dolibarr API
        # result = await dolibarr.validate_invoice(factura_id)

        logger.info("factura_validada", factura_id=factura_id)

        return {
            "success": True,
            "factura_id": factura_id,
            "status": "validated",
        }

    except Exception as exc:
        logger.error("error_validando_factura", factura_id=factura_id, error=str(exc))
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def anular_factura(self, factura_id: int, motivo: str):
    """
    Anular factura (requiere aprobación).
    """
    logger.info("anulando_factura", factura_id=factura_id, motivo=motivo)

    try:
        # TODO: Implementar anulación via Dolibarr API
        return {"success": True, "factura_id": factura_id}
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def crear_factura_rectificativa(self, factura_original_id: int, motivo: str, nuevas_lineas: list):
    """
    Crear factura rectificativa.
    """
    logger.info("creando_rectificativa", factura_original_id=factura_original_id)

    try:
        # TODO: Implementar
        return {"success": True, "rectificativa_id": 1}
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def registrar_cobro(self, factura_id: int, importe: float, fecha_pago: str, metodo_pago: str, referencia: str = None):
    """
    Registrar cobro de factura.
    """
    logger.info("registrando_cobro", factura_id=factura_id, importe=importe)

    try:
        # TODO: Implementar registro de cobro
        return {
            "success": True,
            "pago_id": 1,
            "factura_id": factura_id,
        }
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task
def generar_facturas_periodicas():
    """Generar facturas periódicas (suscripciones, cuotas, etc.)."""
    logger.info("generando_facturas_periodicas")
    return {"success": True, "generadas": 0}


@shared_task
def detectar_facturas_vencidas():
    """Detectar facturas impagadas vencidas."""
    logger.info("detectando_facturas_vencidas")
    return {"success": True, "vencidas": 0}


# =============================================================================
# Async Invoice Processing Task
# =============================================================================

from datetime import date
from decimal import Decimal


@shared_task(bind=True, max_retries=0, time_limit=720, soft_time_limit=660)
def procesar_factura_async(self, task_data: dict):
    """
    Procesar factura de forma asíncrona con idempotencia.

    Args:
        task_data: {
            "file_content_b64": str,  # base64 encoded file content
            "filename": str,
            "telegram_user_id": int,
            "telegram_chat_id": int,
            "telegram_message_id": int,
            "update_id": int,
            "correlation_id": str,
            "file_unique_id": str,  # OPTIONAL: Telegram file_unique_id for stronger idempotency
        }

    Returns:
        dict with processing result

    Idempotency guarantees:
    - Same correlation_id → returns cached result (ACK + exit, NO Qwen)
    - Same file_unique_id → returns cached result (ACK + exit, NO Qwen)
    - Draft status in {PENDING_APPROVAL, APPROVED, REGISTERED, REJECTED,
      REQUIRES_REVIEW, REQUIRES_CLEANUP, PENDING_SUPPLIER}
      → ACK + exit, NO Qwen
    - Only processes if: no cached result AND draft status is
      CREATING_DOLIBARR or not found
    """
    import asyncio

    correlation_id: str = task_data.get("correlation_id", "")
    file_content_b64: str | None = task_data.get("file_content_b64")
    filename: str = task_data.get("filename", "invoice.pdf")
    telegram_user_id: int = task_data.get("telegram_user_id", 0)
    telegram_chat_id: int = task_data.get("telegram_chat_id", 0)
    telegram_message_id: int = task_data.get("telegram_message_id", 0)
    file_unique_id: str | None = task_data.get("file_unique_id")  # Optional, from Telegram

    logger.info(
        "procesar_factura_async_started",
        task_id=self.request.id,
        correlation_id=correlation_id,
        file_unique_id=file_unique_id[:20] + "..." if file_unique_id else None,
    )

    # ============================================================
    # IDEMPOTENCY CHECK 1: Redis correlation_id cache
    # ============================================================
    async def run_idempotency_checks():
        # Check Redis cache first (fastest)
        file_content = base64.b64decode(file_content_b64) if file_content_b64 else b""
        file_hash = _compute_file_hash(file_content) if file_content else None

        should_skip, cached_result = await _check_idempotency_redis(correlation_id, file_hash)
        if should_skip and cached_result:
            logger.info("idempotency_skip_cached_result", correlation_id=correlation_id)
            return json.loads(cached_result), True  # result, skipped

        # ============================================================
        # IDEMPOTENCY CHECK 2: Draft status in PostgreSQL
        # ============================================================
        draft_status = await _check_draft_status(correlation_id)
        if draft_status and draft_status in SKIP_STATUSES:
            logger.info("idempotency_skip_draft_status", correlation_id=correlation_id, status=draft_status)
            # Return appropriate "already processed" response
            return {
                "success": True,
                "idempotent_skip": True,
                "skip_reason": f"draft_status_{draft_status.lower()}",
                "message": f"Factura ya procesada (estado: {draft_status}). No se vuelve a ejecutar Qwen.",
                "draft_status": draft_status,
            }, True

        return None, False  # No cached result, not skipped

    # Run idempotency checks
    cached_result, skipped = asyncio.run(run_idempotency_checks())
    if skipped:
        return cached_result

    # ============================================================
    # PROCESS INVOICE (only reached if not skipped)
    # ============================================================
    try:
        file_content = base64.b64decode(file_content_b64) if file_content_b64 else b""

        # Create temp file for agent (which expects file path)
        with tempfile.NamedTemporaryFile(suffix=os.path.splitext(filename)[1], delete=False) as tmp:
            tmp.write(file_content)
            temp_file_path = tmp.name

        # Import here to avoid circular imports
        from agents.invoice_processing.agent import create_invoice_processing_agent
        from app.core.config import get_settings

        settings = get_settings()
        config = {
            "OLLAMA_ENDPOINT": settings.OLLAMA_ENDPOINT,
            "OLLAMA_MODEL": settings.OLLAMA_MODEL,
            "NVIDIA_API_KEY": settings.NVIDIA_API_KEY,
            "NVIDIA_BASE_URL": settings.NVIDIA_BASE_URL,
            "INVOICE_STORAGE_ROOT": "/data/invoices",
            "OCR_DPI": 150,
            "OCR_MAX_PAGES": 5,
            "OCR_MAX_FILE_MB": 10,
            "OCR_TIMEOUT": 120,
            "OLLAMA_INVOICE_TIMEOUT": 600,
        }

        # Run async processing
        async def run_processing():
            agent = create_invoice_processing_agent(config)
            await agent.start()
            try:
                result = await agent.process_invoice(file_content, filename)
                return result
            finally:
                await agent.stop()

        result = asyncio.run(run_processing())

        # Clean up temp file
        if os.path.exists(temp_file_path):
            os.unlink(temp_file_path)

        logger.info("procesar_factura_async_completed",
                    task_id=self.request.id,
                    correlation_id=correlation_id,
                    success=result.get("success"))

        # Store result in Redis for retrieval
        # This will be picked up by the supervisor to send Telegram update
        async def store_result():
            try:
                from app.core.database import get_redis_client
                redis = await get_redis_client()
                result_key = f"invoice_result:{correlation_id}"
                result_json = json.dumps(result)
                await redis.setex(result_key, 3600, result_json)

                # Also cache by file_hash for file_unique_id idempotency
                file_hash = _compute_file_hash(file_content)
                await redis.setex(f"invoice_result:file:{file_hash}", 7200, result_json)

                # Also publish to channel for real-time notification
                await redis.publish("invoice_results", json.dumps({
                    "correlation_id": correlation_id,
                    "telegram_user_id": telegram_user_id,
                    "telegram_chat_id": telegram_chat_id,
                    "telegram_message_id": telegram_message_id,
                    "result": result,
                }))
            except Exception as e:
                logger.warning("store_result_failed", correlation_id=correlation_id, error=str(e))

        asyncio.run(store_result())

        return result

    except Exception as exc:
        logger.error("procesar_factura_async_failed", task_id=self.request.id, error=str(exc))

        # Store error result
        error_result = {
            "success": False,
            "error": "processing_failed",
            "message": f"Error procesando factura: {str(exc)}",
            "requires_review": True,
        }

        try:
            from app.core.database import get_redis_client
            if correlation_id:
                async def store_error():
                    redis = await get_redis_client()
                    result_key = f"invoice_result:{correlation_id}"
                    await redis.setex(result_key, 3600, json.dumps(error_result))
                asyncio.run(store_error())
        except Exception:
            pass

        return error_result
