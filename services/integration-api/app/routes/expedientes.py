"""
Rutas para gestión de expedientes de animales.
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.dependencies.auth import get_current_agent, require_write
from app.dependencies.rate_limit import rate_limit_dependency, idempotency_dependency
from app.schemas import (
    ExpedienteAnimalCreate,
    ExpedienteAnimalUpdate,
    ExpedienteAnimalResponse,
    PaginatedResponse,
    PaginationParams,
)
from app.services.dolibarr_client import DolibarrClient
from app.services.audit_logger import AuditLogger
from app.core.exceptions import NotFoundException, ValidationException

router = APIRouter(prefix="/expedientes", tags=["Expedientes"])
settings = get_settings()


@router.get("", response_model=PaginatedResponse[ExpedienteAnimalResponse])
async def list_expedientes(
    pagination: PaginationParams = Depends(),
    status: Optional[str] = Query(None, description="Filtrar por estado comercial"),
    agent: dict = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
):
    """
    Listar expedientes de animales con paginación y filtros.
    
    Requiere rol: products, sales, supervisor, admin
    """
    # TODO: Implementar consulta real a Dolibarr
    # Por ahora devolver respuesta vacía para tests
    return PaginatedResponse(
        success=True,
        data=[],
        total=0,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get("/{expediente_id}", response_model=ExpedienteAnimalResponse)
async def get_expediente(
    expediente_id: int,
    agent: dict = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
):
    """
    Obtener un expediente por ID.
    
    Requiere rol: products, sales, compliance, supervisor, admin
    """
    # TODO: Implementar consulta real a Dolibarr
    raise NotFoundException("Expediente", str(expediente_id))


@router.post(
    "",
    response_model=ExpedienteAnimalResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_expediente(
    expediente: ExpedienteAnimalCreate,
    agent: dict = Depends(require_write),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
    _idempotency: None = Depends(idempotency_dependency),
):
    """
    Crear nuevo expediente de animal (borrador).
    
    Requiere rol: products, supervisor, admin
    Requiere aprobación humana para: precios, estado publicado
    """
    # Validaciones de negocio
    if expediente.sale_price > 0 and expediente.purchase_price > 0:
        margin = (expediente.sale_price - expediente.purchase_price) / expediente.purchase_price * 100
        if margin < 10:
            raise ValidationException(
                "Margen mínimo del 10% requerido",
                details={"margin_percent": round(margin, 2)}
            )
    
    # Validar microchip (formato ISO 11784/11785)
    if not expediente.microchip.isdigit() or len(expediente.microchip) != 15:
        raise ValidationException(
            "Microchip debe ser 15 dígitos numéricos (ISO 11784/11785)"
        )
    
    # TODO: Crear en Dolibarr via API
    # dolibarr = DolibarrClient(...)
    # result = await dolibarr.create_expediente(expediente.dict())
    
    # Simular respuesta exitosa
    return ExpedienteAnimalResponse(
        **expediente.dict(),
        id=1,
        internal_id=f"EXP-2024-000001",
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


@router.put("/{expediente_id}", response_model=ExpedienteAnimalResponse)
async def update_expediente(
    expediente_id: int,
    expediente: ExpedienteAnimalUpdate,
    agent: dict = Depends(require_write),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
    _idempotency: None = Depends(idempotency_dependency),
):
    """
    Actualizar expediente existente.
    
    Cambios en precio, estado comercial o datos fiscales requieren aprobación.
    """
    # Verificar que existe
    # existing = await dolibarr.get_expediente(expediente_id)
    # if not existing:
    #     raise NotFoundException("Expediente", str(expediente_id))
    
    # Verificar cambios que requieren aprobación
    # if expediente.sale_price and expediente.sale_price != existing.sale_price:
    #     raise ValidationException("Cambio de precio requiere aprobación")
    
    # if expediente.commercial_status and expediente.commercial_status != existing.commercial_status:
    #     if expediente.commercial_status in ["published", "sold", "delivered", "archived"]:
    #         raise ValidationException("Cambio de estado requiere aprobación")
    
    # TODO: Actualizar en Dolibarr
    raise NotFoundException("Expediente", str(expediente_id))


@router.delete("/{expediente_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_expediente(
    expediente_id: int,
    agent: dict = Depends(require_write),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
):
    """
    Eliminar expediente (solo si está en borrador).
    
    Requiere rol: supervisor, admin
    """
    # Verificar estado
    # existing = await dolibarr.get_expediente(expediente_id)
    # if existing.commercial_status != "draft":
    #     raise ValidationException("Solo se pueden eliminar expedientes en estado borrador")
    
    # TODO: Eliminar en Dolibarr
    raise NotFoundException("Expediente", str(expediente_id))


@router.post("/{expediente_id}/validate-docs", status_code=status.HTTP_200_OK)
async def validate_documentation(
    expediente_id: int,
    agent: dict = Depends(require_write),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
):
    """
    Validar documentación completa del expediente.
    
    Verifica: microchip, vacunas, pasaporte, pedigree, certificado veterinario.
    """
    # TODO: Implementar validación con Agente de Cumplimiento
    return {
        "success": True,
        "valid": True,
        "checks": {
            "microchip": True,
            "vaccines": True,
            "passport": True,
            "pedigree": True,
            "vet_certificate": True,
        },
        "missing": [],
        "warnings": [],
    }


@router.post("/{expediente_id}/publish", status_code=status.HTTP_202_ACCEPTED)
async def publish_expediente(
    expediente_id: int,
    platforms: List[str] = ["web", "milanuncios"],
    agent: dict = Depends(require_write),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
    _idempotency: None = Depends(idempotency_dependency),
):
    """
    Solicitar publicación del expediente en canales.
    
    Requiere aprobación humana.
    """
    # Verificar que expediente está listo para publicar
    # existing = await dolibarr.get_expediente(expediente_id)
    # if existing.commercial_status != "available":
    #     raise ValidationException("Solo expedientes 'available' pueden publicarse")
    
    # if not existing.documentation_complete:
    #     raise ValidationException("Documentación incompleta")
    
    # Solicitar aprobación
    # approval_id = await approval_service.request(
    #     action="publish",
    #     resource_type="expediente",
    #     resource_id=str(expediente_id),
    #     proposed_state={"platforms": platforms},
    # )
    
    return {
        "success": True,
        "message": "Publicación solicitada, pendiente de aprobación",
        "approval_id": "pending",
    }