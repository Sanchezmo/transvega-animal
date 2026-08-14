"""
Rutas para gestión de productos/servicios.
"""

from app.core.config import get_settings
from app.core.database import get_db
from app.core.exceptions import NotFoundException
from app.dependencies.auth import get_current_agent, require_write
from app.dependencies.rate_limit import idempotency_dependency, rate_limit_dependency
from app.schemas import (
    PaginatedResponse,
    PaginationParams,
    ProductCreate,
    ProductResponse,
    ProductUpdate,
)
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["Productos"])
settings = get_settings()


@router.get("", response_model=PaginatedResponse[ProductResponse])
async def list_productos(
    pagination: PaginationParams = Depends(),
    status: int | None = Query(None, description="Filtrar por estado"),
    agent: dict = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
):
    """Listar productos/servicios."""
    return PaginatedResponse(
        success=True,
        data=[],
        total=0,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get("/{producto_id}", response_model=ProductResponse)
async def get_producto(
    producto_id: int,
    agent: dict = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
):
    """Obtener producto por ID."""
    raise NotFoundException("Producto", str(producto_id))


@router.post(
    "",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_producto(
    producto: ProductCreate,
    agent: dict = Depends(require_write),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
    _idempotency: None = Depends(idempotency_dependency),
):
    """Crear nuevo producto/servicio."""
    # TODO: Crear en Dolibarr
    raise NotFoundException("Producto", "no implementado")


@router.put("/{producto_id}", response_model=ProductResponse)
async def update_producto(
    producto_id: int,
    producto: ProductUpdate,
    agent: dict = Depends(require_write),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
    _idempotency: None = Depends(idempotency_dependency),
):
    """Actualizar producto."""
    raise NotFoundException("Producto", str(producto_id))


@router.delete("/{producto_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_producto(
    producto_id: int,
    agent: dict = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
):
    """Eliminar producto (solo si no tiene facturas/pedidos)."""
    raise NotFoundException("Producto", str(producto_id))
