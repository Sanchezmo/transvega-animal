"""
Publication service - CRUD operations for publications/listings using SQLAlchemy.
"""

import json
from datetime import datetime

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import NotFoundException, ValidationException
from app.models import Publication
from app.schemas import (
    PaginationParams,
    PublicationCreate,
    PublicationUpdate,
)


class PublicationService:
    """Service for publication-related database operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    def _serialize_photos(self, photos: list[str]) -> str:
        """Serialize photos list to JSON string."""
        return json.dumps(photos) if photos else "[]"

    def _deserialize_photos(self, photos_str: str) -> list[str]:
        """Deserialize photos JSON string to list."""
        if not photos_str:
            return []
        try:
            return json.loads(photos_str)
        except (json.JSONDecodeError, TypeError):
            return []

    async def create_publication(self, pub_data: PublicationCreate, created_by: int = 1) -> Publication:
        """Create a new publication draft."""
        # Verify platform is valid
        valid_platforms = ["web", "milanuncios", "facebook", "instagram", "tiktok"]
        if pub_data.platform not in valid_platforms:
            raise ValidationException(f"Plataforma inválida. Válidas: {valid_platforms}")

        # Convert photos list to JSON string
        pub_dict = pub_data.model_dump()
        pub_dict["photos"] = self._serialize_photos(pub_data.photos)

        publication = Publication(
            **pub_dict,
            status="draft",
            created_by=created_by,
            updated_by=created_by,
        )
        self.db.add(publication)
        await self.db.flush()
        await self.db.refresh(publication)
        return publication

    async def get_publication(self, pub_id: int) -> Publication | None:
        """Get publication by ID."""
        result = await self.db.execute(select(Publication).where(Publication.id == pub_id))
        return result.scalar_one_or_none()

    async def list_publications(
        self,
        pagination: PaginationParams,
        platform: str | None = None,
        status: str | None = None,
        expediente_id: int | None = None,
    ) -> tuple[list[Publication], int]:
        """List publications with filters and pagination."""
        query = select(Publication)

        if platform is not None:
            query = query.where(Publication.platform == platform)
        if status is not None:
            query = query.where(Publication.status == status)
        if expediente_id is not None:
            query = query.where(Publication.expediente_id == expediente_id)

        # Get total count
        count_query = select(func.count(Publication.id))
        if platform is not None:
            count_query = count_query.where(Publication.platform == platform)
        if status is not None:
            count_query = count_query.where(Publication.status == status)
        if expediente_id is not None:
            count_query = count_query.where(Publication.expediente_id == expediente_id)

        count_result = await self.db.execute(count_query)
        total = count_result.scalar_one()

        # Get paginated results
        result = await self.db.execute(
            query.order_by(Publication.created_at.desc()).offset(pagination.offset).limit(pagination.limit)
        )
        publications = list(result.scalars().all())
        return publications, total

    async def update_publication(self, pub_id: int, pub_data: PublicationUpdate, updated_by: int = 1) -> Publication:
        """Update an existing publication."""
        publication = await self.get_publication(pub_id)
        if not publication:
            raise NotFoundException("Publicación", str(pub_id))

        update_data = pub_data.model_dump(exclude_unset=True)
        # Serialize photos if present
        if "photos" in update_data and update_data["photos"] is not None:
            update_data["photos"] = self._serialize_photos(update_data["photos"])

        for field, value in update_data.items():
            setattr(publication, field, value)

        publication.updated_by = updated_by
        publication.updated_at = datetime.utcnow()

        await self.db.flush()
        await self.db.refresh(publication)
        return publication

    async def approve_publication(self, pub_id: int, approved_by: int = 1) -> Publication:
        """Approve a publication for publishing."""
        publication = await self.get_publication(pub_id)
        if not publication:
            raise NotFoundException("Publicación", str(pub_id))

        if publication.status not in ["draft", "pending_approval"]:
            raise ValidationException(f"Cannot approve publication in status: {publication.status}")

        publication.status = "approved"
        publication.approved_by = approved_by
        publication.approved_at = datetime.utcnow()
        publication.updated_by = approved_by
        publication.updated_at = datetime.utcnow()

        await self.db.flush()
        await self.db.refresh(publication)
        return publication

    async def reject_publication(self, pub_id: int, reason: str, rejected_by: int = 1) -> Publication:
        """Reject a publication."""
        publication = await self.get_publication(pub_id)
        if not publication:
            raise NotFoundException("Publicación", str(pub_id))

        publication.status = "rejected"
        publication.rejection_reason = reason
        publication.rejected_by = rejected_by
        publication.rejected_at = datetime.utcnow()
        publication.updated_by = rejected_by
        publication.updated_at = datetime.utcnow()

        await self.db.flush()
        await self.db.refresh(publication)
        return publication

    async def publish_publication(
        self, pub_id: int, published_by: int = 1, external_id: str | None = None, external_url: str | None = None
    ) -> Publication:
        """
        Mark publication as published with real confirmation from platform.

        REQUIRES external_id and external_url from the platform (e.g., Milanuncios).
        Without these, the publication cannot be marked as published.
        """
        publication = await self.get_publication(pub_id)
        if not publication:
            raise NotFoundException("Publicación", str(pub_id))

        if publication.status != "approved":
            raise ValidationException(
                f"Only approved publications can be published. Current status: {publication.status}"
            )

        # REQUIRE real confirmation from platform
        if not external_id or not external_url:
            raise ValidationException(
                "Cannot mark as published without real platform confirmation. "
                "external_id and external_url are required from the publishing platform."
            )

        publication.status = "published"
        publication.external_id = external_id
        publication.external_url = external_url
        publication.published_by = published_by
        publication.published_at = datetime.utcnow()
        publication.updated_by = published_by
        publication.updated_at = datetime.utcnow()

        await self.db.flush()
        await self.db.refresh(publication)
        return publication

    async def mark_publish_failed(self, pub_id: int, error: str, failed_by: int = 1) -> Publication:
        """
        Mark publication as failed after a failed publishing attempt.

        This should be called when PublishingAgent fails to publish to Milanuncios.
        """
        publication = await self.get_publication(pub_id)
        if not publication:
            raise NotFoundException("Publicación", str(pub_id))

        if publication.status != "approved":
            raise ValidationException(
                f"Can only mark approved publications as failed. Current status: {publication.status}"
            )

        publication.status = "failed"
        publication.rejection_reason = error
        publication.rejected_by = failed_by
        publication.rejected_at = datetime.utcnow()
        publication.updated_by = failed_by
        publication.updated_at = datetime.utcnow()

        await self.db.flush()
        await self.db.refresh(publication)
        return publication

    async def unpublish_publication(self, pub_id: int, reason: str, unpublished_by: int = 1) -> Publication:
        """Unpublish/retire a publication."""
        publication = await self.get_publication(pub_id)
        if not publication:
            raise NotFoundException("Publicación", str(pub_id))

        publication.status = "removed"
        publication.unpublish_reason = reason
        publication.unpublished_by = unpublished_by
        publication.unpublished_at = datetime.utcnow()
        publication.updated_by = unpublished_by
        publication.updated_at = datetime.utcnow()

        await self.db.flush()
        await self.db.refresh(publication)
        return publication

    async def renew_publication(self, pub_id: int, renewed_by: int = 1) -> Publication:
        """Renew a publication (for Milanuncios 7-day renewal)."""
        publication = await self.get_publication(pub_id)
        if not publication:
            raise NotFoundException("Publicación", str(pub_id))

        if publication.status != "published":
            raise ValidationException(
                f"Only published publications can be renewed. Current status: {publication.status}"
            )

        # For Milanuncios, renewal typically means refreshing the listing
        publication.last_renewed_at = datetime.utcnow()
        publication.renewed_by = renewed_by
        publication.updated_by = renewed_by
        publication.updated_at = datetime.utcnow()

        await self.db.flush()
        await self.db.refresh(publication)
        return publication


async def get_publication_service(
    db: AsyncSession = Depends(get_db),
) -> PublicationService:
    """Dependency to get PublicationService instance with DB session injected."""
    return PublicationService(db)
