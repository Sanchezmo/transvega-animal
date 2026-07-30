"""
Rutas para gestión de terceros (clientes/proveedores).
"""
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.dependencies.auth import get_current_agent, require_write
from app.dependencies.rate_limit import rate_limit_dependency, idempotency_dependency
from app.dependencies.dolibarr import get_dolibarr_client
from app.adapters.dolibarr.client import DolibarrClient
from app.adapters.dolibarr.mappers import (
    thirdparty_to_dolibarr,
    thirdparty_update_to_dolibarr,
    dolibarr_to_thirdparty,
    dolibarr_list_to_thirdparties,
)
from app.schemas import (
    ThirdPartyCreate,
    ThirdPartyUpdate,
    ThirdPartyResponse,
    PaginatedResponse,
    PaginationParams,
)
from app.core.exceptions import NotFoundException, DolibarrException

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
    dolibarr: DolibarrClient = Depends(get_dolibarr_client),
    _rate_limit: None = Depends(rate_limit_dependency),
):
    """Listar terceros con paginación y filtros."""
    try:
        # Construir sqlfilters para Dolibarr
        filters = []
        if client is not None:
            filters.append(f"client:='{client}'")
        if supplier is not None:
            filters.append(f"supplier:='{supplier}'")
        if status is not None:
            filters.append(f"status:='{status}'")
        
        sqlfilters = ";".join(filters) if filters else None
        
        # Consultar Dolibarr
        result = await dolibarr.list_thirdparties(
            limit=pagination.limit,
            offset=pagination.offset,
            sqlfilters=sqlfilters,
        )
        
        # Convertir a nuestro schema
        terceros = dolibarr_list_to_thirdparties(result)
        
        return PaginatedResponse(
            success=True,
            data=[ThirdPartyResponse(**t) for t in terceros],
            total=len(terceros),
            limit=pagination.limit,
            offset=pagination.offset,
        )
    except DolibarrException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error consultando terceros: {str(e)}")


@router.get("/{tercero_id}", response_model=ThirdPartyResponse)
async def get_tercero(
    tercero_id: int,
    agent: dict = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
    dolibarr: DolibarrClient = Depends(get_dolibarr_client),
    _rate_limit: None = Depends(rate_limit_dependency),
):
    """Obtener tercero por ID."""
    try:
        result = await dolibarr.get_thirdparty(tercero_id)
        tercero_data = dolibarr_to_thirdparty(result)
        return ThirdPartyResponse(**tercero_data)
    except DolibarrException as e:
        if e.status_code == 404:
            raise NotFoundException("Tercero", str(tercero_id))
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error obteniendo tercero: {str(e)}")


@router.post(
    "",
    response_model=ThirdPartyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_tercero(
    tercero: ThirdPartyCreate,
    agent: dict = Depends(require_write),
    db: AsyncSession = Depends(get_db),
    dolibarr: DolibarrClient = Depends(get_dolibarr_client),
    _rate_limit: None = Depends(rate_limit_dependency),
    _idempotency: None = Depends(idempotency_dependency),
):
    """
    Crear nuevo tercero (cliente/proveedor) en Dolibarr.

    Requiere rol: invoicing, accounting, admin
    """
    # Validaciones
    if tercero.vat_number and len(tercero.vat_number) > 20:
        raise ValueError("NIF/CIF demasiado largo")

    try:
        # Convertir a formato Dolibarr
        dolibarr_data = thirdparty_to_dolibarr(tercero)
        
        # Crear en Dolibarr
        result = await dolibarr.create_thirdparty(dolibarr_data)
        
        # Convertir respuesta
        tercero_data = dolibarr_to_thirdparty(result)
        return ThirdPartyResponse(**tercero_data)
    except DolibarrException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creando tercero: {str(e)}")


@router.put("/{tercero_id}", response_model=ThirdPartyResponse)
async def update_tercero(
    tercero_id: int,
    tercero: ThirdPartyUpdate,
    agent: dict = Depends(require_write),
    db: AsyncSession = Depends(get_db),
    dolibarr: DolibarrClient = Depends(get_dolibarr_client),
    _rate_limit: None = Depends(rate_limit_dependency),
    _idempotency: None = Depends(idempotency_dependency),
):
    """Actualizar tercero en Dolibarr."""
    try:
        # Convertir a formato Dolibarr (solo campos no-None)
        dolibarr_data = thirdparty_update_to_dolibarr(tercero)
        
        if not dolibarr_data:
            raise ValueError("No hay campos para actualizar")
        
        # Actualizar en Dolibarr
        result = await dolibarr.update_thirdparty(tercero_id, dolibarr_data)
        
        # Convertir respuesta
        tercero_data = dolibarr_to_thirdparty(result)
        return ThirdPartyResponse(**tercero_data)
    except DolibarrException as e:
        if e.status_code == 404:
            raise NotFoundException("Tercero", str(tercero_id))
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error actualizando tercero: {str(e)}")


@router.delete("/{tercero_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tercero(
    tercero_id: int,
    agent: dict = Depends(get_current_agent),  # Admin only in practice
    db: AsyncSession = Depends(get_db),
    dolibarr: DolibarrClient = Depends(get_dolibarr_client),
    _rate_limit: None = Depends(rate_limit_dependency),
):
    """Eliminar tercero (solo si no tiene facturas/pedidos)."""
    try:
        await dolibarr.delete_thirdparty(tercero_id)
    except DolibarrException as e:
        if e.status_code == 404:
            raise NotFoundException("Tercero", str(tercero_id))
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error eliminando tercero: {str(e)}")