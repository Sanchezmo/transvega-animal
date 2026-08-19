"""
Tareas Celery para facturación.
"""

import base64

import structlog
from celery import shared_task

logger = structlog.get_logger()


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
    Procesar factura de forma asíncrona.

    Args:
        task_data: {
            "file_content_b64": str,  # base64 encoded file content
            "filename": str,
            "telegram_user_id": int,
            "telegram_chat_id": int,
            "telegram_message_id": int,
            "update_id": int,
            "correlation_id": str,
        }

    Returns:
        dict with processing result
    """
    import asyncio
    import os
    import tempfile

    logger.info(
        "procesar_factura_async_started",
        task_id=self.request.id,
        correlation_id=task_data.get("correlation_id"),
    )

    try:
        # Decode file content
        file_content = base64.b64decode(task_data["file_content_b64"])
        filename = task_data["filename"]
        telegram_user_id = task_data["telegram_user_id"]
        telegram_chat_id = task_data["telegram_chat_id"]
        telegram_message_id = task_data.get("telegram_message_id", 0)
        _ = task_data.get("update_id", 0)  # unused
        correlation_id = task_data["correlation_id"]

        # Create temp file
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
        import json

        from app.core.database import get_redis_client

        async def store_result():
            redis = await get_redis_client()
            result_key = f"invoice_result:{correlation_id}"
            await redis.setex(result_key, 3600, json.dumps(result))

            # Also publish to channel for real-time notification
            await redis.publish("invoice_results", json.dumps({
                "correlation_id": correlation_id,
                "telegram_user_id": telegram_user_id,
                "telegram_chat_id": telegram_chat_id,
                "telegram_message_id": telegram_message_id,
                "result": result,
            }))

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
            import json

            from app.core.database import get_redis_client
            correlation_id = task_data.get("correlation_id")
            if correlation_id:
                async def store_error():
                    redis = await get_redis_client()
                    result_key = f"invoice_result:{correlation_id}"
                    await redis.setex(result_key, 3600, json.dumps(error_result))
                asyncio.run(store_error())
        except Exception:
            pass

        return error_result
