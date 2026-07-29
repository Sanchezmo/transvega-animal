"""
Rutas para gestión de publicaciones/anuncios.
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.core.config import get_settings
from app.core.database import get_db
from app.dependencies.auth import get_current_agent, require_write
from app.dependencies.rate_limit import rate_limit_dependency, idempotency_dependency
from app.schemas import (
    PublicationCreate,
    PublicationUpdate,
    PublicationResponse,
    PaginatedResponse,
    PaginationParams,
)
from app.core.exceptions import NotFoundException, ValidationException

router = APIRouter(prefix="/publicaciones", tags=["Publicaciones"])
settings = get_settings()


@router.get("", response_model=PaginatedResponse[PublicationResponse])
async def list_publicaciones(
    pagination: PaginationParams = Depends(),
    platform: Optional[str] = Query(None, description="Filtrar por plataforma"),
    status: Optional[str] = Query(None, description="Filtrar por estado"),
    expediente_id: Optional[int] = Query(None, description="Filtrar por expediente"),
    agent: dict = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
):
    """Listar publicaciones/anuncios."""
    return PaginatedResponse(
        success=True,
        data=[],
        total=0,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get("/{publicacion_id}", response_model=PublicationResponse)
async def get_publicacion(
    publicacion_id: int,
    agent: dict = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
):
    """Obtener publicación por ID."""
    raise NotFoundException("Publicación", str(publicacion_id))


@router.post(
    "",
    response_model=PublicationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_publicacion(
    publicacion: PublicationCreate,
    agent: dict = Depends(require_write),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
    _idempotency: None = Depends(idempotency_dependency),
):
    """
    Crear borrador de publicación.
    
    Requiere aprobación humana para publicar.
    """
    # Validar que el expediente existe y está disponible
    # expediente = await dolibarr.get_expediente(publicacion.expediente_id)
    # if expediente.commercial_status != "available":
    #     raise ValidationException("Solo expedientes 'available' pueden publicarse")
    
    # if not expediente.documentation_complete:
    #     raise ValidationException("Documentación incompleta")
    
    # Validar plataforma
    valid_platforms = ["web", "milanuncios", "facebook", "instagram", "tiktok"]
    if publicacion.platform not in valid_platforms:
        raise ValidationException(f"Plataforma inválida. Válidas: {valid_platforms}")
    
    # TODO: Crear en BD local + solicitar aprobación
    raise NotFoundException("Publicación", "no implementado")


@router.put("/{publicacion_id}", response_model=PublicationResponse)
async def update_publicacion(
    publicacion_id: int,
    publicacion: PublicationUpdate,
    agent: dict = Depends(require_write),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
    _idempotency: None = Depends(idempotency_dependency),
):
    """Actualizar publicación."""
    raise NotFoundException("Publicación", str(publicacion_id))


@router.post("/{publicacion_id}/approve", status_code=status.HTTP_202_ACCEPTED)
async def approve_publicacion(
    publicacion_id: int,
    agent: dict = Depends(require_write),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
):
    """Aprobar publicación para publicación real."""
    # TODO: Implementar flujo de aprobación
    return {
        "success": True,
        "message": "Publicación aprobada, pendiente de publicación real",
    }


@router.post("/{publicacion_id}/reject", status_code=status.HTTP_202_ACCEPTED)
async def reject_publicacion(
    publicacion_id: int,
    reason: str,
    agent: dict = Depends(require_write),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
):
    """Rechazar publicación."""
    return {
        "success": True,
        "message": "Publicación rechazada",
    }


@router.post("/{publicacion_id}/publish", status_code=status.HTTP_202_ACCEPTED)
async def publish_publicacion(
    publicacion_id: int,
    agent: dict = Depends(require_write),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
    _idempotency: None = Depends(idempotency_dependency),
):
    """
    Publicar en plataforma externa (Milanuncios, etc.).
    
    Requiere: aprobación previa, expediente válido, documentación completa.
    """
    # Verificar estado: approved
    # Verificar expediente: available + docs complete
    # Ejecutar publicación via publisher agent
    
    raise NotFoundException("Publicación", "no implementado")


@router.post("/{publicacion_id}/unpublish", status_code=status.HTTP_202_ACCEPTED)
async def unpublish_publicacion(
    publicacion_id: int,
    reason: str = "Vendido / Retirado",
    agent: dict = Depends(require_write),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
):
    """Retirar publicación (expediente vendido, error, etc.)."""
    return {
        "success": True,
        "message": "Publicación retirada",
    }


@router.post("/{publicacion_id}/renew", status_code=status.HTTP_202_ACCEPTED)
async def renew_publicacion(
    publicacion_id: int,
    agent: dict = Depends(require_write),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
):
    """Renovar publicación (Milanuncios renueva cada 7 días)."""
    return {
        "success": True,
        "message": "Publicación renovada",
    }