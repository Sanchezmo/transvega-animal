"""
Dog service - CRUD operations for dogs and related entities using SQLAlchemy.
"""

from datetime import datetime

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.exceptions import NotFoundException, ValidationException
from app.models import Breed, Dog, DogHealth, DogMedia, DogStatusHistory, Litter
from app.schemas import (
    BreedCreate,
    DogCreate,
    DogHealthCreate,
    DogMediaCreate,
    DogStatusHistoryCreate,
    DogUpdate,
    LitterCreate,
    PaginationParams,
)


class DogService:
    """Service for dog-related database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # =========================================================================
    # BREED OPERATIONS
    # =========================================================================

    async def create_breed(self, breed_data: BreedCreate) -> Breed:
        """Create a new breed."""
        breed = Breed(**breed_data.model_dump())
        self.db.add(breed)
        await self.db.flush()
        await self.db.refresh(breed)
        return breed

    async def get_breed(self, breed_id: int) -> Breed | None:
        """Get breed by ID."""
        result = await self.db.execute(select(Breed).where(Breed.id == breed_id))
        return result.scalar_one_or_none()

    async def list_breeds(self, pagination: PaginationParams) -> tuple[list[Breed], int]:
        """List breeds with pagination."""
        count_result = await self.db.execute(select(func.count(Breed.id)))
        total = count_result.scalar_one()

        result = await self.db.execute(
            select(Breed).order_by(Breed.name).offset(pagination.offset).limit(pagination.limit)
        )
        breeds = list(result.scalars().all())
        return breeds, total

    # =========================================================================
    # LITTER OPERATIONS
    # =========================================================================

    async def create_litter(self, litter_data: LitterCreate) -> Litter:
        """Create a new litter."""
        breed = await self.get_breed(litter_data.breed_id)
        if not breed:
            raise NotFoundException("Raza", str(litter_data.breed_id))

        mother_result = await self.db.execute(select(Dog).where(Dog.id == litter_data.mother_id))
        mother = mother_result.scalar_one_or_none()
        if not mother:
            raise NotFoundException("Madre", str(litter_data.mother_id))

        if litter_data.father_id:
            father_result = await self.db.execute(select(Dog).where(Dog.id == litter_data.father_id))
            father = father_result.scalar_one_or_none()
            if not father:
                raise NotFoundException("Padre", str(litter_data.father_id))

        litter = Litter(**litter_data.model_dump())
        self.db.add(litter)
        await self.db.flush()
        await self.db.refresh(litter)
        return litter

    async def get_litter(self, litter_id: int) -> Litter | None:
        """Get litter by ID with relationships."""
        result = await self.db.execute(
            select(Litter)
            .options(
                selectinload(Litter.breed),
                selectinload(Litter.mother),
                selectinload(Litter.father),
            )
            .where(Litter.id == litter_id)
        )
        return result.scalar_one_or_none()

    async def list_litters(self, pagination: PaginationParams) -> tuple[list[Litter], int]:
        """List litters with pagination."""
        count_result = await self.db.execute(select(func.count(Litter.id)))
        total = count_result.scalar_one()

        result = await self.db.execute(
            select(Litter)
            .options(selectinload(Litter.breed))
            .order_by(Litter.birth_date.desc())
            .offset(pagination.offset)
            .limit(pagination.limit)
        )
        litters = list(result.scalars().all())
        return litters, total

    # =========================================================================
    # DOG OPERATIONS
    # =========================================================================

    async def create_dog(self, dog_data: DogCreate, created_by: int = 1) -> Dog:
        """Create a new dog."""
        breed = await self.get_breed(dog_data.breed_id)
        if not breed:
            raise NotFoundException("Raza", str(dog_data.breed_id))

        if dog_data.litter_id:
            litter = await self.get_litter(dog_data.litter_id)
            if not litter:
                raise NotFoundException("Camada", str(dog_data.litter_id))

        existing = await self.db.execute(select(Dog).where(Dog.microchip == dog_data.microchip))
        if existing.scalar_one_or_none():
            raise ValidationException(f"Microchip {dog_data.microchip} ya registrado")

        year = datetime.now().year
        count_result = await self.db.execute(select(func.count(Dog.id)).where(Dog.internal_id.like(f"DOG-{year}-%")))
        seq = count_result.scalar_one() + 1
        internal_id = f"DOG-{year}-{seq:06d}"

        dog = Dog(
            **dog_data.model_dump(),
            internal_id=internal_id,
            created_by=created_by,
            updated_by=created_by,
        )
        self.db.add(dog)
        await self.db.flush()

        status_history = DogStatusHistory(
            dog_id=dog.id,
            status=dog.status,
            changed_by=created_by,
            change_reason="Creación inicial",
        )
        self.db.add(status_history)
        await self.db.flush()
        await self.db.refresh(dog)
        return dog

    async def get_dog(self, dog_id: int) -> Dog | None:
        """Get dog by ID with relationships."""
        result = await self.db.execute(
            select(Dog)
            .options(
                selectinload(Dog.breed),
                selectinload(Dog.litter),
                selectinload(Dog.media),
                selectinload(Dog.health_records),
                selectinload(Dog.status_history),
            )
            .where(Dog.id == dog_id)
        )
        return result.scalar_one_or_none()

    async def get_dog_by_internal_id(self, internal_id: str) -> Dog | None:
        """Get dog by internal ID."""
        result = await self.db.execute(select(Dog).where(Dog.internal_id == internal_id))
        return result.scalar_one_or_none()

    async def list_dogs(
        self,
        pagination: PaginationParams,
        breed_id: int | None = None,
        litter_id: int | None = None,
        status: str | None = None,
    ) -> tuple[list[Dog], int]:
        """List dogs with filters and pagination."""
        query = select(Dog).options(selectinload(Dog.breed))

        if breed_id is not None:
            query = query.where(Dog.breed_id == breed_id)
        if litter_id is not None:
            query = query.where(Dog.litter_id == litter_id)
        if status is not None:
            query = query.where(Dog.status == status)

        count_query = select(func.count(Dog.id))
        if breed_id is not None:
            count_query = count_query.where(Dog.breed_id == breed_id)
        if litter_id is not None:
            count_query = count_query.where(Dog.litter_id == litter_id)
        if status is not None:
            count_query = count_query.where(Dog.status == status)

        count_result = await self.db.execute(count_query)
        total = count_result.scalar_one()

        result = await self.db.execute(
            query.order_by(Dog.created_at.desc()).offset(pagination.offset).limit(pagination.limit)
        )
        dogs = list(result.scalars().all())
        return dogs, total

    async def update_dog(self, dog_id: int, dog_data: DogUpdate, updated_by: int = 1) -> Dog:
        """Update an existing dog."""
        dog = await self.get_dog(dog_id)
        if not dog:
            raise NotFoundException("Perro", str(dog_id))

        old_status = dog.status

        update_data = dog_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(dog, field, value)

        dog.updated_by = updated_by
        dog.updated_at = datetime.utcnow()

        if "status" in update_data and update_data["status"] != old_status:
            status_history = DogStatusHistory(
                dog_id=dog.id,
                status=update_data["status"],
                changed_by=updated_by,
                change_reason="Actualización de estado via API",
            )
            self.db.add(status_history)

        await self.db.flush()
        await self.db.refresh(dog)
        return dog

    async def delete_dog(self, dog_id: int) -> None:
        """Delete a dog (only if draft or inactive)."""
        dog = await self.get_dog(dog_id)
        if not dog:
            raise NotFoundException("Perro", str(dog_id))

        if dog.status not in ["draft", "inactive"]:
            raise ValidationException(f"No se puede eliminar perro en estado {dog.status}. Solo draft o inactive.")

        await self.db.delete(dog)
        await self.db.flush()

    # =========================================================================
    # MEDIA OPERATIONS
    # =========================================================================

    async def add_media(self, dog_id: int, media_data: DogMediaCreate) -> DogMedia:
        """Add media to a dog."""
        dog = await self.get_dog(dog_id)
        if not dog:
            raise NotFoundException("Perro", str(dog_id))

        # Exclude dog_id from model_dump since we're setting it explicitly
        media_dict = media_data.model_dump(exclude={"dog_id"})
        media = DogMedia(
            **media_dict,
            dog_id=dog_id,
        )
        self.db.add(media)
        await self.db.flush()
        await self.db.refresh(media)
        return media

    async def get_dog_media(
        self,
        dog_id: int,
        pagination: PaginationParams,
        media_type: str | None = None,
        purpose: str | None = None,
    ) -> tuple[list[DogMedia], int]:
        """Get media for a dog with filters."""
        query = select(DogMedia).where(DogMedia.dog_id == dog_id)

        if media_type:
            query = query.where(DogMedia.media_type == media_type)
        if purpose:
            query = query.where(DogMedia.purpose == purpose)

        count_query = select(func.count(DogMedia.id)).where(DogMedia.dog_id == dog_id)
        if media_type:
            count_query = count_query.where(DogMedia.media_type == media_type)
        if purpose:
            count_query = count_query.where(DogMedia.purpose == purpose)

        count_result = await self.db.execute(count_query)
        total = count_result.scalar_one()

        result = await self.db.execute(
            query.order_by(DogMedia.created_at.desc()).offset(pagination.offset).limit(pagination.limit)
        )
        media = list(result.scalars().all())
        return media, total

    # =========================================================================
    # HEALTH OPERATIONS
    # =========================================================================

    async def add_health_record(self, dog_id: int, health_data: DogHealthCreate) -> DogHealth:
        """Add health record to a dog."""
        dog = await self.get_dog(dog_id)
        if not dog:
            raise NotFoundException("Perro", str(dog_id))

        health = DogHealth(
            **health_data.model_dump(),
            dog_id=dog_id,
        )
        self.db.add(health)
        await self.db.flush()
        await self.db.refresh(health)
        return health

    # =========================================================================
    # STATUS HISTORY OPERATIONS
    # =========================================================================

    async def add_status_history(self, dog_id: int, status_data: DogStatusHistoryCreate) -> DogStatusHistory:
        """Add status history entry for a dog."""
        dog = await self.get_dog(dog_id)
        if not dog:
            raise NotFoundException("Perro", str(dog_id))

        history = DogStatusHistory(
            **status_data.model_dump(),
            dog_id=dog_id,
        )
        self.db.add(history)

        dog.status = status_data.status
        dog.updated_at = datetime.utcnow()

        await self.db.flush()
        await self.db.refresh(history)
        return history


async def get_dog_service(db: AsyncSession = Depends(get_db)) -> DogService:
    """Dependency to get DogService instance with DB session injected."""
    return DogService(db)
