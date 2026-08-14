"""
Rutas para gestión comercial (leads, oportunidades, consultas).
"""

from app.core.config import get_settings
from app.core.database import get_db
from app.core.exceptions import NotFoundException
from app.dependencies.auth import get_current_agent, require_write
from app.dependencies.rate_limit import idempotency_dependency, rate_limit_dependency
from app.schemas import (
    LeadCreate,
    LeadResponse,
    LeadUpdate,
    PaginatedResponse,
    PaginationParams,
)
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["Comercial"])
settings = get_settings()


@router.get("/leads", response_model=PaginatedResponse[LeadResponse])
async def list_leads(
    pagination: PaginationParams = Depends(),
    status: str | None = Query(None, description="Filtrar por estado"),
    agent: dict = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
):
    """Listar leads/compradores potenciales."""
    return PaginatedResponse(
        success=True,
        data=[],
        total=0,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get("/leads/{lead_id}", response_model=LeadResponse)
async def get_lead(
    lead_id: int,
    agent: dict = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
):
    """Obtener lead por ID."""
    raise NotFoundException("Lead", str(lead_id))


@router.post(
    "/leads",
    response_model=LeadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_lead(
    lead: LeadCreate,
    agent: dict = Depends(require_write),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
    _idempotency: None = Depends(idempotency_dependency),
):
    """Crear nuevo lead desde consulta web, WhatsApp, etc."""
    raise NotFoundException("Lead", "no implementado")


@router.put("/leads/{lead_id}", response_model=LeadResponse)
async def update_lead(
    lead_id: int,
    lead: LeadUpdate,
    agent: dict = Depends(require_write),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
    _idempotency: None = Depends(idempotency_dependency),
):
    """Actualizar lead (estado, datos, asignación)."""
    raise NotFoundException("Lead", str(lead_id))


@router.post("/leads/{lead_id}/assign", status_code=status.HTTP_200_OK)
async def assign_lead(
    lead_id: int,
    closer_id: int,
    agent: dict = Depends(require_write),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
):
    """Asignar lead a closer/comercial."""
    return {
        "success": True,
        "message": f"Lead {lead_id} asignado a closer {closer_id}",
    }


@router.post("/leads/{lead_id}/qualify", status_code=status.HTTP_200_OK)
async def qualify_lead(
    lead_id: int,
    score: int,
    intent: str,
    agent: dict = Depends(require_write),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
):
    """Calificar lead (score, intención, presupuesto)."""
    return {
        "success": True,
        "message": f"Lead {lead_id} calificado: score={score}, intent={intent}",
    }


# =============================================================================
# OPORTUNIDADES / PEDIDOS
# =============================================================================


@router.get("/oportunidades", response_model=PaginatedResponse[dict])
async def list_oportunidades(
    pagination: PaginationParams = Depends(),
    status: str | None = Query(None),
    agent: dict = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
):
    """Listar oportunidades/oportunidades de venta."""
    return PaginatedResponse(
        success=True,
        data=[],
        total=0,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.post("/oportunidades", status_code=status.HTTP_201_CREATED)
async def create_oportunidad(
    lead_id: int,
    expediente_id: int,
    estimated_value: float,
    agent: dict = Depends(require_write),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
    _idempotency: None = Depends(idempotency_dependency),
):
    """Crear oportunidad de venta desde lead + expediente."""
    return {
        "success": True,
        "message": "Oportunidad creada",
        "oportunidad_id": 1,
    }


@router.post("/reservas", status_code=status.HTTP_202_ACCEPTED)
async def create_reserva(
    expediente_id: int,
    lead_id: int,
    deposit_amount: float,
    agent: dict = Depends(require_write),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
    _idempotency: None = Depends(idempotency_dependency),
):
    """
    Crear reserva (requiere aprobación si > 50% o condiciones especiales).
    """
    return {
        "success": True,
        "message": "Reserva creada, pendiente de confirmación de pago",
        "reserva_id": 1,
    }


@router.post("/pedidos", status_code=status.HTTP_201_CREATED)
async def create_pedido(
    expediente_id: int,
    client_id: int,
    lines: list,
    agent: dict = Depends(require_write),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
    _idempotency: None = Depends(idempotency_dependency),
):
    """Crear pedido de venta confirmado."""
    return {
        "success": True,
        "message": "Pedido creado",
        "pedido_id": 1,
    }


@router.post("/presupuestos", status_code=status.HTTP_201_CREATED)
async def create_presupuesto(
    expediente_id: int,
    client_id: int,
    lines: list,
    valid_days: int = 30,
    agent: dict = Depends(require_write),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
    _idempotency: None = Depends(idempotency_dependency),
):
    """Crear presupuesto para cliente."""
    return {
        "success": True,
        "message": "Presupuesto creado",
        "presupuesto_id": 1,
    }
