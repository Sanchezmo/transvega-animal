"""
Rutas para gestión de terceros (clientes/proveedores).
"""
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.dependencies.auth import get_current_agent, require_write
from app.dependencies.rate_limit import rate_limit_dependency, idempotency_dependency
from app.schemas import (
    ThirdPartyCreate,
    ThirdPartyUpdate,
    ThirdPartyResponse,
    PaginatedResponse,
    PaginationParams,
)
from app.core.exceptions import NotFoundException

router = APIRouter(prefix="/terceros", tags=["Terceros"])
settings = get_settings()


@router.get("", response_model=PaginatedResponse[ThirdPartyResponse])
async def list_terceros(
    pagination: PaginationParams = Depends(),
    client: Optional[int] = Query(None, description="Filtrar por tipo cliente (1/0)"),
    supplier: Optional[int] = Query(None, description="Filtrar por tipo proveedor (1/0)"),
    status: Optional[int] = Query(None, description="Filtrar por estado"),
    agent: dict = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
):
    """Listar terceros con paginación y filtros."""
    # TODO: Consultar Dolibarr
    return PaginatedResponse(
        success=True,
        data=[],
        total=0,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get("/{tercero_id}", response_model=ThirdPartyResponse)
async def get_tercero(
    tercero_id: int,
    agent: dict = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
):
    """Obtener tercero por ID."""
    # TODO: Consultar Dolibarr
    raise NotFoundException("Tercero", str(tercero_id))


@router.post(
    "",
    response_model=ThirdPartyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_tercero(
    tercero: ThirdPartyCreate,
    agent: dict = Depends(require_write),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
    _idempotency: None = Depends(idempotency_dependency),
):
    """
    Crear nuevo tercero (cliente/proveedor).

    Requiere rol: invoicing, accounting, admin
    No valida automáticamente - requiere aprobación humana.
    """
    # Validaciones
    if tercero.vat_number and len(tercero.vat_number) > 20:
        raise ValueError("NIF/CIF demasiado largo")

    # TODO: Crear en Dolibarr
    # Simular respuesta exitosa
    return ThirdPartyResponse(
        **tercero.dict(),
        id=1,
        ref="TERT-2024-000001",
        datec=datetime.now(),
        datem=datetime.now(),
    )


@router.put("/{tercero_id}", response_model=ThirdPartyResponse)
async def update_tercero(
    tercero_id: int,
    tercero: ThirdPartyCreate,
    agent: dict = Depends(require_write),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
    _idempotency: None = Depends(idempotency_dependency),
):
    """Actualizar tercero."""
    raise NotFoundException("Tercero", str(tercero_id))


@router.delete("/{tercero_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tercero(
    tercero_id: int,
    agent: dict = Depends(get_current_agent),  # Admin only in practice
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
):
    """Eliminar tercero (solo si no tiene facturas/pedidos)."""
    raise NotFoundException("Tercero", str(tercero_id))