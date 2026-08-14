"""
Rutas para gestión de publicaciones/anuncios.
"""

from fastapi import APIRouter, Depends, Query, status

from app.core.config import get_settings
from app.core.exceptions import NotFoundException, ValidationException
from app.dependencies.auth import get_current_agent, require_write
from app.dependencies.rate_limit import idempotency_dependency, rate_limit_dependency
from app.schemas import (
    PaginatedResponse,
    PaginationParams,
    PublicationCreate,
    PublicationResponse,
    PublicationUpdate,
)
from app.services.publication_service import PublicationService, get_publication_service

router = APIRouter(tags=["Publicaciones"])
settings = get_settings()


@router.get("", response_model=PaginatedResponse[PublicationResponse])
async def list_publicaciones(
    pagination: PaginationParams = Depends(),
    platform: str | None = Query(None, description="Filtrar por plataforma"),
    status: str | None = Query(None, description="Filtrar por estado"),
    expediente_id: int | None = Query(None, description="Filtrar por expediente"),
    agent: dict = Depends(get_current_agent),
    _rate_limit: None = Depends(rate_limit_dependency),
    pub_service: PublicationService = Depends(get_publication_service),
):
    """Listar publicaciones/anuncios."""
    pubs, total = await pub_service.list_publications(
        pagination=pagination,
        platform=platform,
        status=status,
        expediente_id=expediente_id,
    )
    return PaginatedResponse(
        success=True,
        data=pubs,
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get("/{publicacion_id}", response_model=PublicationResponse)
async def get_publicacion(
    publicacion_id: int,
    agent: dict = Depends(get_current_agent),
    _rate_limit: None = Depends(rate_limit_dependency),
    pub_service: PublicationService = Depends(get_publication_service),
):
    """Obtener publicación por ID."""
    pub = await pub_service.get_publication(publicacion_id)
    if not pub:
        raise NotFoundException("Publicación", str(publicacion_id))
    return pub


@router.post(
    "",
    response_model=PublicationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_publicacion(
    publicacion: PublicationCreate,
    agent: dict = Depends(require_write),
    _rate_limit: None = Depends(rate_limit_dependency),
    _idempotency: None = Depends(idempotency_dependency),
    pub_service: PublicationService = Depends(get_publication_service),
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

    created_pub = await pub_service.create_publication(
        pub_data=publicacion,
        created_by=agent.get("agent_id", 1),
    )
    return created_pub


@router.put("/{publicacion_id}", response_model=PublicationResponse)
async def update_publicacion(
    publicacion_id: int,
    publicacion: PublicationUpdate,
    agent: dict = Depends(require_write),
    _rate_limit: None = Depends(rate_limit_dependency),
    _idempotency: None = Depends(idempotency_dependency),
    pub_service: PublicationService = Depends(get_publication_service),
):
    """Actualizar publicación."""
    updated_pub = await pub_service.update_publication(
        pub_id=publicacion_id,
        pub_data=publicacion,
        updated_by=agent.get("agent_id", 1),
    )
    return updated_pub


@router.post("/{publicacion_id}/approve", status_code=status.HTTP_202_ACCEPTED)
async def approve_publicacion(
    publicacion_id: int,
    agent: dict = Depends(require_write),
    _rate_limit: None = Depends(rate_limit_dependency),
    pub_service: PublicationService = Depends(get_publication_service),
):
    """Aprobar publicación para publicación real."""
    approved_pub = await pub_service.approve_publication(
        pub_id=publicacion_id,
        approved_by=agent.get("agent_id", 1),
    )
    return {
        "success": True,
        "message": "Publicación aprobada, pendiente de publicación real",
        "publication": approved_pub,
    }


@router.post("/{publicacion_id}/reject", status_code=status.HTTP_202_ACCEPTED)
async def reject_publicacion(
    publicacion_id: int,
    reason: str,
    agent: dict = Depends(require_write),
    _rate_limit: None = Depends(rate_limit_dependency),
    pub_service: PublicationService = Depends(get_publication_service),
):
    """Rechazar publicación."""
    rejected_pub = await pub_service.reject_publication(
        pub_id=publicacion_id,
        reason=reason,
        rejected_by=agent.get("agent_id", 1),
    )
    return {
        "success": True,
        "message": "Publicación rechazada",
        "publication": rejected_pub,
    }


@router.post("/{publicacion_id}/publish", status_code=status.HTTP_202_ACCEPTED)
async def publish_publicacion(
    publicacion_id: int,
    external_id: str | None = None,
    external_url: str | None = None,
    agent: dict = Depends(require_write),
    _rate_limit: None = Depends(rate_limit_dependency),
    _idempotency: None = Depends(idempotency_dependency),
    pub_service: PublicationService = Depends(get_publication_service),
):
    """
    Publicar en plataforma externa (Milanuncios, etc.).

    Requiere: aprobación previa, expediente válido, documentación completa.

    IMPORTANTE: Requiere external_id y external_url de la confirmación real de la plataforma.
    Sin estos campos, no se puede marcar como publicada.
    """
    published_pub = await pub_service.publish_publication(
        pub_id=publicacion_id,
        published_by=agent.get("agent_id", 1),
        external_id=external_id,
        external_url=external_url,
    )
    return {
        "success": True,
        "message": "Publicación confirmada como publicada en la plataforma",
        "publication": published_pub,
    }


@router.post("/{publicacion_id}/publish-failed", status_code=status.HTTP_202_ACCEPTED)
async def publish_failed_publicacion(
    publicacion_id: int,
    error: str,
    agent: dict = Depends(require_write),
    _rate_limit: None = Depends(rate_limit_dependency),
    pub_service: PublicationService = Depends(get_publication_service),
):
    """
    Marcar publicación como fallida tras intento de publicación.

    Se llama cuando el PublishingAgent falla al publicar en Milanuncios.
    """
    failed_pub = await pub_service.mark_publish_failed(
        pub_id=publicacion_id,
        error=error,
        failed_by=agent.get("agent_id", 1),
    )
    return {
        "success": True,
        "message": "Publicación marcada como fallida",
        "publication": failed_pub,
    }


@router.post("/{publicacion_id}/unpublish", status_code=status.HTTP_202_ACCEPTED)
async def unpublish_publicacion(
    publicacion_id: int,
    reason: str = "Vendido / Retirado",
    agent: dict = Depends(require_write),
    _rate_limit: None = Depends(rate_limit_dependency),
    pub_service: PublicationService = Depends(get_publication_service),
):
    """Retirar publicación (expediente vendido, error, etc.)."""
    unpublished_pub = await pub_service.unpublish_publication(
        pub_id=publicacion_id,
        reason=reason,
        unpublished_by=agent.get("agent_id", 1),
    )
    return {
        "success": True,
        "message": "Publicación retirada",
        "publication": unpublished_pub,
    }


@router.post("/{publicacion_id}/renew", status_code=status.HTTP_202_ACCEPTED)
async def renew_publicacion(
    publicacion_id: int,
    agent: dict = Depends(require_write),
    _rate_limit: None = Depends(rate_limit_dependency),
    pub_service: PublicationService = Depends(get_publication_service),
):
    """Renovar publicación (Milanuncios renueva cada 7 días)."""
    renewed_pub = await pub_service.renew_publication(
        pub_id=publicacion_id,
        renewed_by=agent.get("agent_id", 1),
    )
    return {
        "success": True,
        "message": "Publicación renovada",
        "publication": renewed_pub,
    }
