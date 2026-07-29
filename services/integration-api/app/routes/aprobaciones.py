"""
Rutas para gestión de aprobaciones humanas.
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.core.config import get_settings
from app.core.database import get_db
from app.dependencies.auth import get_current_agent, require_write, require_admin
from app.dependencies.rate_limit import rate_limit_dependency, idempotency_dependency
from app.schemas import (
    ApprovalRequestCreate,
    ApprovalDecision,
    ApprovalResponse,
    PaginatedResponse,
    PaginationParams,
)
from app.core.exceptions import NotFoundException

router = APIRouter(prefix="/aprobaciones", tags=["Aprobaciones"])
settings = get_settings()


@router.get("", response_model=PaginatedResponse[dict])
async def list_aprobaciones(
    pagination: PaginationParams = Depends(),
    status: Optional[str] = Query(None, description="Filtrar por estado"),
    agent_id: Optional[str] = Query(None, description="Filtrar por agente solicitante"),
    resource_type: Optional[str] = Query(None, description="Filtrar por tipo de recurso"),
    agent: dict = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
):
    """Listar solicitudes de aprobación pendientes/históricas."""
    # Los admins ven todas, los agentes solo las suyas
    # if "admin" not in agent.get("roles", []):
    #     agent_id = agent["agent_id"]
    
    return PaginatedResponse(
        success=True,
        data=[],
        total=0,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get("/pendientes", response_model=PaginatedResponse[dict])
async def list_aprobaciones_pendientes(
    pagination: PaginationParams = Depends(),
    agent: dict = Depends(require_admin),  # Solo admins/supervisores ven pendientes globales
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
):
    """Listar aprobaciones pendientes de decisión (para panel de supervisores)."""
    return PaginatedResponse(
        success=True,
        data=[],
        total=0,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get("/mis-pendientes", response_model=PaginatedResponse[dict])
async def list_mis_aprobaciones_pendientes(
    pagination: PaginationParams = Depends(),
    agent: dict = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
):
    """Listar aprobaciones pendientes que yo solicité."""
    return PaginatedResponse(
        success=True,
        data=[],
        total=0,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get("/{aprobacion_id}", response_model=dict)
async def get_aprobacion(
    aprobacion_id: UUID,
    agent: dict = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
):
    """Obtener detalle de una solicitud de aprobación."""
    from app.core.exceptions import NotFoundException
    raise NotFoundException("Aprobación", str(aprobacion_id))


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
)
async def create_aprobacion(
    aprobacion: dict,  # ApprovalRequestCreate
    agent: dict = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
    _idempotency: None = Depends(idempotency_dependency),
):
    """
    Crear solicitud de aprobación.
    
    Acciones que requieren aprobación:
    - Publicar anuncios
    - Cambiar precios
    - Aplicar descuentos
    - Confirmar reservas
    - Validar facturas
    - Emitir rectificativas
    - Anular facturas
    - Presentar impuestos
    - Realizar pagos
    - Modificar plan contable
    - Modificar tipos impositivos
    - Modificar datos fiscales
    - Lanzar campañas pagadas
    - Actualizar producción
    - Borrar datos
    - Exportar grandes volúmenes
    """
    # Validar acción permitida
    allowed_actions = [
        "publish", "price_change", "discount", "confirm_reservation",
        "validate_invoice", "rectify_invoice", "cancel_invoice",
        "present_taxes", "make_payment", "modify_chart_accounts",
        "modify_tax_rates", "modify_fiscal_data", "launch_paid_campaign",
        "update_production", "delete_data", "bulk_export",
    ]
    
    # TODO: Validar acción
    # if accion not in allowed_actions:
    #     raise ValidationException(f"Acción no permitida: {accion}")
    
    return {
        "success": True,
        "message": "Solicitud de aprobación creada",
        "aprobacion_id": "uuid-generado",
        "status": "pending",
    }


@router.post("/{aprobacion_id}/approve", status_code=status.HTTP_200_OK)
async def approve_aprobacion(
    aprobacion_id: UUID,
    decision: dict,  # ApprovalDecision
    agent: dict = Depends(require_admin),  # Solo admins/supervisores pueden aprobar
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
    _idempotency: None = Depends(idempotency_dependency),
):
    """
    Aprobar solicitud.
    
    Solo administradores/supervisores pueden aprobar.
    Requiere comentario si se rechaza.
    """
    # approved = decision.get("approved", True)
    # comment = decision.get("comment")
    
    # if not approved and not comment:
    #     raise ValidationException("Comentario requerido al rechazar")
    
    # TODO: Ejecutar acción aprobada
    # if aprobacion.action_type == "validate_invoice":
    #     await dolibarr.validate_invoice(aprobacion.resource_id)
    # elif aprobacion.action_type == "publish":
    #     await publisher_agent.publish(aprobacion.resource_id, aprobacion.proposed_state)
    
    return {
        "success": True,
        "message": "Solicitud aprobada y acción ejecutada",
        "aprobacion_id": str(aprobacion_id),
    }


@router.post("/{aprobacion_id}/reject", status_code=status.HTTP_200_OK)
async def reject_aprobacion(
    aprobacion_id: UUID,
    decision: dict,  # ApprovalDecision (con approved=False)
    agent: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
    _idempotency: None = Depends(idempotency_dependency),
):
    """Rechazar solicitud de aprobación."""
    # comment = decision.get("comment")
    # if not comment:
    #     raise ValidationException("Comentario requerido al rechazar")
    
    # TODO: Rechazar y notificar
    return {
        "success": True,
        "message": "Solicitud rechazada",
        "aprobacion_id": str(aprobacion_id),
    }


@router.post("/{aprobacion_id}/cancel", status_code=status.HTTP_200_OK)
async def cancel_aprobacion(
    aprobacion_id: UUID,
    agent: dict = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
):
    """Cancelar solicitud propia (solo si está pendiente)."""
    return {
        "success": True,
        "message": "Solicitud cancelada",
        "aprobacion_id": str(aprobacion_id),
    }


@router.get("/stats/summary", response_model=dict)
async def get_aprobaciones_stats(
    agent: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
):
    """Estadísticas de aprobaciones para dashboard."""
    return {
        "success": True,
        "data": {
            "pending": 0,
            "approved_today": 0,
            "rejected_today": 0,
            "avg_resolution_time_hours": 0,
            "by_action": {},
            "by_agent": {},
        }
    }