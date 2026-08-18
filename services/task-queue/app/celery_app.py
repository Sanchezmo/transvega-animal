"""
Configuración de Celery para el worker.
"""

# Import settings directly from the integration-api config
import sys

from celery import Celery

sys.path.insert(0, "/app")

from app.core.config import get_settings

settings = get_settings()

# Crear app Celery
celery_app = Celery(
    "transvega_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "tasks.expedientes",
        "tasks.publicaciones",
        "tasks.facturacion",
        "tasks.notificaciones",
    ],
)

# Configuración
celery_app.conf.update(
    # Serialización
    task_serializer=settings.CELERY_TASK_SERIALIZER,
    result_serializer=settings.CELERY_RESULT_SERIALIZER,
    accept_content=settings.CELERY_ACCEPT_CONTENT,
    # Zona horaria
    timezone=settings.CELERY_TIMEZONE,
    enable_utc=True,
    # Tracking
    task_track_started=settings.CELERY_TASK_TRACK_STARTED,
    task_time_limit=settings.CELERY_TASK_TIME_LIMIT,
    # Worker
    worker_prefetch_multiplier=settings.CELERY_WORKER_PREFETCH_MULTIPLIER,
    worker_concurrency=settings.CELERY_WORKER_CONCURRENCY,
    # Colas
    task_default_queue=settings.CELERY_TASK_DEFAULT_QUEUE,
    task_queues={
        "high": {"exchange": "high", "routing_key": "high"},
        "default": {"exchange": "default", "routing_key": "default"},
        "low": {"exchange": "low", "routing_key": "low"},
        "approvals": {"exchange": "approvals", "routing_key": "approvals"},
        "notifications": {"exchange": "notifications", "routing_key": "notifications"},
    },
    task_routes={
        "app.tasks.expedientes.*": {"queue": "high"},
        "app.tasks.publicaciones.*": {"queue": "default"},
        "app.tasks.facturacion.*": {"queue": "high"},
        "app.tasks.notificaciones.*": {"queue": "notifications"},
    },
    # Reintentos
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Resultados
    result_expires=3600,
    result_compression="gzip",
    # Beat schedule (tareas periódicas)
    beat_schedule={
        "verificar-expedientes-vencidos": {
            "task": "app.tasks.expedientes.verificar_expedientes_vencidos",
            "schedule": 3600.0,  # Cada hora
        },
        "limpiar-tareas-antiguas": {
            "task": "app.tasks.expedientes.limpiar_tareas_antiguas",
            "schedule": 86400.0,  # Diario
        },
        "renovar-publicaciones": {
            "task": "app.tasks.publicaciones.renovar_todas_publicaciones_activas",
            "schedule": 43200.0,  # Cada 12 horas
        },
        "verificar-publicaciones-expiradas": {
            "task": "app.tasks.publicaciones.verificar_publicaciones_expiradas",
            "schedule": 3600.0,  # Cada hora
        },
        "generar-facturas-periodicas": {
            "task": "app.tasks.facturacion.generar_facturas_periodicas",
            "schedule": 86400.0,  # Diario
        },
        "detectar-facturas-vencidas": {
            "task": "app.tasks.facturacion.detectar_facturas_vencidas",
            "schedule": 3600.0,  # Cada hora
        },
        "enviar-reporte-diario": {
            "task": "app.tasks.notificaciones.enviar_reporte_diario",
            "schedule": 86400.0,  # Diario a medianoche
            "args": (["admin@transvega-animal.es"],),
        },
        "limpiar-tareas-antiguas-cola": {
            "task": "app.tasks.expedientes.limpiar_tareas_antiguas",
            "schedule": 604800.0,  # Semanal
        },
    },
)

# Auto-discover tasks
celery_app.autodiscover_tasks()


@celery_app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Tarea de debug."""
    print(f"Request: {self.request!r}")


if __name__ == "__main__":
    celery_app.start()
