"""
Tareas Celery para notificaciones.
"""
from celery import shared_task
from datetime import datetime
from typing import List, Optional
import structlog

logger = structlog.get_logger()


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def enviar_notificacion_aprobacion(self, aprobacion_id: str, accion: str, 
                                   destinatarios: List[str], datos: dict):
    """
    Enviar notificación de solicitud de aprobación.
    
    Canales: Email, Telegram, Slack, WhatsApp Business API
    """
    logger.info("enviando_notificacion_aprobacion", aprobacion_id=aprobacion_id, accion=accion)
    
    try:
        # TODO: Implementar envío real
        # 1. Preparar mensaje según canal
        # 2. Enviar via API correspondiente
        # 3. Registrar estado de entrega
        
        mensaje = f"""
🔔 Nueva solicitud de aprobación: {accion}

ID: {aprobacion_id}
Acción: {accion}
Detalles: {datos.get('reason', 'Sin detalles')}
Expira: {datos.get('expires_at', 'No especificada')}

Revisar en: https://hermes.transvega-animal.es/aprobaciones/{aprobacion_id}
        """
        
        resultados = {}
        for canal in ["email", "telegram"]:
            # TODO: Implementar envío real
            resultados[canal] = "enviado"
        
        logger.info(
            "notificacion_enviada",
            aprobacion_id=aprobacion_id,
            canales=list(resultados.keys()),
        )
        
        return {
            "success": True,
            "aprobacion_id": aprobacion_id,
            "canales_enviados": list(resultados.keys()),
        }
        
    except Exception as exc:
        logger.error(
            "error_enviando_notificacion_aprobacion",
            aprobacion_id=aprobacion_id,
            error=str(exc),
        )
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def notificar_resultado_aprobacion(self, aprobacion_id: str, aprobada: bool, 
                                   solicitante_id: str, comentario: str = None):
    """
    Notificar resultado de aprobación al solicitante.
    """
    logger.info("notificando_resultado_aprobacion", aprobacion_id=aprobacion_id, aprobada=aprobada)
    
    try:
        estado = "APROBADA ✅" if aprobada else "RECHAZADA ❌"
        
        mensaje = f"""
📋 Resultado de tu solicitud de aprobación

ID: {aprobacion_id}
Estado: {estado}
Comentario: {comentario or 'Sin comentarios adicionales'}
        """
        
        # TODO: Enviar notificación
        return {"success": True, "aprobacion_id": aprobacion_id}
        
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def notificar_cambio_estado_expediente(self, expediente_id: int, estado_anterior: str, 
                                       estado_nuevo: str, destinatarios: List[str]):
    """
    Notificar cambio de estado de expediente.
    """
    logger.info("notificando_cambio_estado", expediente_id=expediente_id, 
                estado_anterior=estado_anterior, estado_nuevo=estado_nuevo)
    
    try:
        mensaje = f"""
🔄 Cambio de estado en expediente

Expediente: {expediente_id}
Estado anterior: {estado_anterior}
Estado nuevo: {estado_nuevo}
Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}
        """
        
        # TODO: Enviar notificación
        return {"success": True, "expediente_id": expediente_id}
        
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def notificar_factura_vencida(self, factura_id: int, dias_vencida: int, 
                              cliente_email: str, importe: float):
    """
    Notificar factura vencida al cliente y a administración.
    """
    logger.info("notificando_factura_vencida", factura_id=factura_id, dias_vencida=dias_vencida)
    
    try:
        mensaje = f"""
⚠️ Factura vencida

Factura: {factura_id}
Días vencida: {dias_vencida}
Importe: {importe}€
Cliente: {cliente_email}

Por favor, regularice el pago a la mayor brevedad.
        """
        
        # TODO: Enviar email + notificación interna
        return {"success": True, "factura_id": factura_id}
        
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def notificar_entrega_programada(self, expediente_id: int, fecha_entrega: str, 
                                 transportista: str, tracking_url: str,
                                 destinatarios: List[str]):
    """
    Notificar entrega programada.
    """
    logger.info("notificando_entrega_programada", expediente_id=expediente_id)
    
    try:
        mensaje = f"""
🚚 Entrega programada

Expediente: {expediente_id}
Fecha prevista: {fecha_entrega}
Transportista: {transportista}
Tracking: {tracking_url}
        """
        
        # TODO: Enviar notificación
        return {"success": True, "expediente_id": expediente_id}
        
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def enviar_reporte_diario(self, destinatarios: List[str]):
    """
    Enviar reporte diario de operaciones.
    """
    from datetime import date
    
    logger.info("enviando_reporte_diario", fecha=date.today().isoformat())
    
    try:
        # TODO: Generar reporte con métricas del día
        reporte = f"""
📊 Reporte Diario - {date.today().strftime('%d/%m/%Y')}

📈 Ventas: 0
📦 Expedientes entregados: 0
📋 Nuevos leads: 0
💰 Facturación: 0.00€
⚠️ Alertas: 0
        """
        
        # TODO: Enviar email
        return {"success": True, "fecha": date.today().isoformat()}
        
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def notificar_alerta_sistema(self, nivel: str, mensaje: str, 
                             servicio: str, destinatarios: List[str]):
    """
    Notificar alerta del sistema (crítica, advertencia, info).
    """
    iconos = {
        "critical": "🔴 CRÍTICO",
        "warning": "🟡 ADVERTENCIA",
        "info": "🔵 INFO",
    }
    
    logger.info("enviando_alerta_sistema", nivel=nivel, servicio=servicio)
    
    try:
        icono = iconos.get(nivel, "🔔")
        
        mensaje_completo = f"""
{icono} Alerta del Sistema

Servicio: {servicio}
Nivel: {nivel.upper()}
Mensaje: {mensaje}
Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
        """
        
        # TODO: Enviar por canal prioritario (Telegram, SMS, llamada)
        return {"success": True, "nivel": nivel}
        
    except Exception as exc:
        raise self.retry(exc=exc)