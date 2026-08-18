"""
Rutas para gestión de perros.
"""

from fastapi import APIRouter, Depends, Query, status

from app.core.config import get_settings
from app.core.exceptions import NotFoundException
from app.dependencies.auth import get_current_agent, require_write
from app.dependencies.rate_limit import idempotency_dependency, rate_limit_dependency
from app.schemas import (
    BreedCreate,
    BreedResponse,
    DogCreate,
    DogHealthCreate,
    DogHealthResponse,
    DogMediaCreate,
    DogMediaResponse,
    DogResponse,
    DogStatusHistoryCreate,
    DogStatusHistoryResponse,
    DogUpdate,
    LitterCreate,
    LitterResponse,
    PaginatedResponse,
    PaginationParams,
)
from app.services.dog_service import get_dog_service

router = APIRouter(tags=["Dogs"])
settings = get_settings()


# =============================================================================
# STATIC ROUTES (must come before parameterized routes like /{dog_id})
# =============================================================================


# Rutas para razas
@router.get("/breeds", response_model=PaginatedResponse[BreedResponse])
async def list_breeds(
    pagination: PaginationParams = Depends(),
    agent: dict = Depends(get_current_agent),
    _rate_limit: None = Depends(rate_limit_dependency),
    dog_service=Depends(get_dog_service),
):
    """
    Listar razas de perros.
    """
    breeds, total = await dog_service.list_breeds(pagination)
    return PaginatedResponse(
        success=True,
        data=breeds,
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.post("/breeds", response_model=BreedResponse, status_code=status.HTTP_201_CREATED)
async def create_breed(
    breed: BreedCreate,
    agent: dict = Depends(require_write),
    _rate_limit: None = Depends(rate_limit_dependency),
    _idempotency: None = Depends(idempotency_dependency),
    dog_service=Depends(get_dog_service),
):
    """
    Crear nueva raza.
    """
    created_breed = await dog_service.create_breed(breed)
    return created_breed


# Rutas para camadas
@router.get("/litters", response_model=PaginatedResponse[LitterResponse])
async def list_litters(
    pagination: PaginationParams = Depends(),
    agent: dict = Depends(get_current_agent),
    _rate_limit: None = Depends(rate_limit_dependency),
    dog_service=Depends(get_dog_service),
):
    """
    Listar camadas de perros.
    """
    litters, total = await dog_service.list_litters(pagination)
    return PaginatedResponse(
        success=True,
        data=litters,
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.post("/litters", response_model=LitterResponse, status_code=status.HTTP_201_CREATED)
async def create_litter(
    litter: LitterCreate,
    agent: dict = Depends(require_write),
    _rate_limit: None = Depends(rate_limit_dependency),
    _idempotency: None = Depends(idempotency_dependency),
    dog_service=Depends(get_dog_service),
):
    """
    Crear nueva camada.
    """
    created_litter = await dog_service.create_litter(litter)
    return created_litter


# =============================================================================
# DOG ROUTES (parameterized - must come after static routes)
# =============================================================================


@router.get("", response_model=PaginatedResponse[DogResponse])
async def list_dogs(
    pagination: PaginationParams = Depends(),
    breed_id: int | None = Query(None, description="Filtrar por raza"),
    litter_id: int | None = Query(None, description="Filtrar por camada"),
    status: str | None = Query(None, description="Filtrar por estado"),
    agent: dict = Depends(get_current_agent),
    _rate_limit: None = Depends(rate_limit_dependency),
    dog_service=Depends(get_dog_service),
):
    """
    Listar perros con paginación y filtros.
    """
    dogs, total = await dog_service.list_dogs(
        pagination=pagination,
        breed_id=breed_id,
        litter_id=litter_id,
        status=status,
    )
    return PaginatedResponse(
        success=True,
        data=dogs,
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get("/{dog_id}", response_model=DogResponse)
async def get_dog(
    dog_id: int,
    agent: dict = Depends(get_current_agent),
    _rate_limit: None = Depends(rate_limit_dependency),
    dog_service=Depends(get_dog_service),
):
    """
    Obtener un perro por ID.
    """
    dog = await dog_service.get_dog(dog_id)
    if not dog:
        raise NotFoundException("Perro", str(dog_id))
    return dog


@router.post(
    "",
    response_model=DogResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_dog(
    dog: DogCreate,
    agent: dict = Depends(require_write),
    _rate_limit: None = Depends(rate_limit_dependency),
    _idempotency: None = Depends(idempotency_dependency),
    dog_service=Depends(get_dog_service),
):
    """
    Crear nuevo perro.
    """
    created_dog = await dog_service.create_dog(
        dog_data=dog,
        created_by=1,  # TODO: extract numeric agent ID from agent identity,
    )
    return created_dog


@router.put("/{dog_id}", response_model=DogResponse)
async def update_dog(
    dog_id: int,
    dog: DogUpdate,
    agent: dict = Depends(require_write),
    _rate_limit: None = Depends(rate_limit_dependency),
    _idempotency: None = Depends(idempotency_dependency),
    dog_service=Depends(get_dog_service),
):
    """
    Actualizar perro existente.
    """
    updated_dog = await dog_service.update_dog(
        dog_id=dog_id,
        dog_data=dog,
        updated_by=1,  # TODO: extract numeric agent ID from agent identity,
    )
    return updated_dog


@router.delete("/{dog_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dog(
    dog_id: int,
    agent: dict = Depends(require_write),
    _rate_limit: None = Depends(rate_limit_dependency),
    dog_service=Depends(get_dog_service),
):
    """
    Eliminar perro (solo si está en estado draft o inactive).
    """
    await dog_service.delete_dog(dog_id)


# Rutas para media
@router.post(
    "/{dog_id}/media",
    response_model=DogMediaResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_dog_media(
    dog_id: int,
    media: DogMediaCreate,
    agent: dict = Depends(require_write),
    _rate_limit: None = Depends(rate_limit_dependency),
    _idempotency: None = Depends(idempotency_dependency),
    dog_service=Depends(get_dog_service),
):
    """
    Añadir media (foto/video) a un perro.
    """
    created_media = await dog_service.add_media(dog_id, media)
    return created_media


@router.get("/{dog_id}/media", response_model=PaginatedResponse[DogMediaResponse])
async def get_dog_media(
    dog_id: int,
    pagination: PaginationParams = Depends(),
    media_type: str | None = Query(None, pattern=r"^(photo|video)$"),
    purpose: str | None = Query(None, pattern=r"^(original|processed|social|listing)$"),
    agent: dict = Depends(get_current_agent),
    _rate_limit: None = Depends(rate_limit_dependency),
    dog_service=Depends(get_dog_service),
):
    """
    Obtener media de un perro.
    """
    media, total = await dog_service.get_dog_media(
        dog_id=dog_id,
        pagination=pagination,
        media_type=media_type,
        purpose=purpose,
    )
    return PaginatedResponse(
        success=True,
        data=media,
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


# Rutas para salud
@router.post(
    "/{dog_id}/health",
    response_model=DogHealthResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_dog_health(
    dog_id: int,
    health: DogHealthCreate,
    agent: dict = Depends(require_write),
    _rate_limit: None = Depends(rate_limit_dependency),
    _idempotency: None = Depends(idempotency_dependency),
    dog_service=Depends(get_dog_service),
):
    """
    Añadir registro de salud a un perro.
    """
    created_health = await dog_service.add_health_record(dog_id, health)
    return created_health


# Rutas para historial de estados
@router.post(
    "/{dog_id}/status",
    response_model=DogStatusHistoryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_dog_status_history(
    dog_id: int,
    status_data: DogStatusHistoryCreate,
    agent: dict = Depends(require_write),
    _rate_limit: None = Depends(rate_limit_dependency),
    _idempotency: None = Depends(idempotency_dependency),
    dog_service=Depends(get_dog_service),
):
    """
    Añadir entrada al historial de estados de un perro.
    """
    created_history = await dog_service.add_status_history(dog_id, status_data)
    return created_history
