"""
Tareas Celery para facturación.
"""

from datetime import date
from decimal import Decimal

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
