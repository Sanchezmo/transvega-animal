"""
Invoice Draft Persistence Service - Almacena borradores de facturas pendientes de aprobación.
Usa PostgreSQL para persistencia que sobrevive a reinicios.
"""

import hashlib
import json
import uuid
from datetime import datetime
from typing import Any

import structlog

from app.core.database import get_db_pool

logger = structlog.get_logger()


class InvoiceDraft:
    """Representa un borrador de factura pendiente de aprobación."""

    def __init__(
        self,
        draft_id: str,
        correlation_id: str,
        telegram_user_id: int,
        telegram_chat_id: int,
        telegram_message_id: int,
        telegram_update_id: int,
        file_hash: str,
        file_path: str,
        final_path: str,
        supplier_tax_id: str,
        supplier_name: str,
        invoice_data: dict[str, Any],
        summary: dict[str, Any],
        status: str = "PENDING_APPROVAL",
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        approved_at: datetime | None = None,
        rejected_at: datetime | None = None,
        dolibarr_invoice_id: int | None = None,
    ):
        self.draft_id = draft_id
        self.correlation_id = correlation_id
        self.telegram_user_id = telegram_user_id
        self.telegram_chat_id = telegram_chat_id
        self.telegram_message_id = telegram_message_id
        self.telegram_update_id = telegram_update_id
        self.file_hash = file_hash
        self.file_path = file_path
        self.final_path = final_path
        self.supplier_tax_id = supplier_tax_id
        self.supplier_name = supplier_name
        self.invoice_data = invoice_data
        self.summary = summary
        self.status = status  # PENDING_APPROVAL, APPROVED, REJECTED,
        # CREATING_DOLIBARR, REGISTERED, REQUIRES_REVIEW, REQUIRES_CLEANUP
        self.created_at = created_at or datetime.utcnow()
        self.updated_at = updated_at or datetime.utcnow()
        self.approved_at = approved_at
        self.rejected_at = rejected_at
        self.dolibarr_invoice_id = dolibarr_invoice_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "draft_id": self.draft_id,
            "correlation_id": self.correlation_id,
            "telegram_user_id": self.telegram_user_id,
            "telegram_chat_id": self.telegram_chat_id,
            "telegram_message_id": self.telegram_message_id,
            "telegram_update_id": self.telegram_update_id,
            "file_hash": self.file_hash,
            "file_path": self.file_path,
            "final_path": self.final_path,
            "supplier_tax_id": self.supplier_tax_id,
            "supplier_name": self.supplier_name,
            "invoice_data": self.invoice_data,
            "summary": self.summary,
            "status": self.status,
            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at,
            "updated_at": self.updated_at.isoformat() if isinstance(self.updated_at, datetime) else self.updated_at,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "rejected_at": self.rejected_at.isoformat() if self.rejected_at else None,
            "dolibarr_invoice_id": self.dolibarr_invoice_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "InvoiceDraft":
        # Convert ISO strings back to datetime
        for field in ("created_at", "updated_at", "approved_at", "rejected_at"):
            if isinstance(data.get(field), str):
                data[field] = datetime.fromisoformat(data[field])
        return cls(**data)


class InvoiceDraftService:
    """Servicio para persistir y recuperar borradores de facturas."""

    def __init__(self) -> None:
        self._pool = None
        self._initialized = False

    async def _get_pool(self):
        if self._pool is None:
            self._pool = await get_db_pool()
        return self._pool

    async def initialize(self) -> None:
        """Create the invoice_drafts table if not exists."""
        if self._initialized:
            return

        pool = await self._get_pool()

        async with pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS invoice_drafts (
                    draft_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    correlation_id UUID NOT NULL,
                    telegram_user_id BIGINT NOT NULL,
                    telegram_chat_id BIGINT NOT NULL,
                    telegram_message_id BIGINT NOT NULL,
                    telegram_update_id BIGINT NOT NULL,
                    file_hash VARCHAR(64) NOT NULL,
                    file_path TEXT NOT NULL,
                    final_path TEXT NOT NULL,
                    supplier_tax_id VARCHAR(50) NOT NULL,
                    supplier_name VARCHAR(200) NOT NULL,
                    invoice_data JSONB NOT NULL,
                    summary JSONB NOT NULL,
                    status VARCHAR(30) NOT NULL DEFAULT 'PENDING_APPROVAL',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    approved_at TIMESTAMPTZ,
                    rejected_at TIMESTAMPTZ,
                    dolibarr_invoice_id INTEGER,
                    -- Constraints
                    CONSTRAINT valid_status CHECK (status IN (
                        'PENDING_APPROVAL', 'APPROVED', 'REJECTED',
                        'CREATING_DOLIBARR', 'REGISTERED', 'REQUIRES_REVIEW', 'REQUIRES_CLEANUP'
                    ))
                )
            """)

            # Indexes for common queries
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_invoice_drafts_telegram_user
                ON invoice_drafts(telegram_user_id, telegram_chat_id, status)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_invoice_drafts_update_id
                ON invoice_drafts(telegram_update_id)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_invoice_drafts_file_hash
                ON invoice_drafts(file_hash)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_invoice_drafts_status
                ON invoice_drafts(status, created_at)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_invoice_drafts_correlation
                ON invoice_drafts(correlation_id)
            """)

        self._initialized = True
        logger.info("invoice_draft_service_initialized")

    async def create_draft(
        self,
        correlation_id: str,
        telegram_user_id: int,
        telegram_chat_id: int,
        telegram_message_id: int,
        telegram_update_id: int,
        file_content: bytes,
        file_path: str,
        final_path: str,
        supplier_tax_id: str,
        supplier_name: str,
        invoice_data: dict[str, Any],
        summary: dict[str, Any],
    ) -> InvoiceDraft:
        """Create a new invoice draft."""
        await self.initialize()
        pool = await self._get_pool()

        file_hash = hashlib.sha256(file_content).hexdigest()
        draft_id = str(uuid.uuid4())

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO invoice_drafts (
                    draft_id, correlation_id, telegram_user_id, telegram_chat_id,
                    telegram_message_id, telegram_update_id, file_hash, file_path,
                    final_path, supplier_tax_id, supplier_name, invoice_data, summary
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                RETURNING *
            """,
                uuid.UUID(draft_id),
                uuid.UUID(correlation_id),
                telegram_user_id,
                telegram_chat_id,
                telegram_message_id,
                telegram_update_id,
                file_hash,
                file_path,
                final_path,
                supplier_tax_id,
                supplier_name,
                json.dumps(invoice_data),
                json.dumps(summary),
            )

        draft = InvoiceDraft(
            draft_id=str(row["draft_id"]),
            correlation_id=str(row["correlation_id"]),
            telegram_user_id=row["telegram_user_id"],
            telegram_chat_id=row["telegram_chat_id"],
            telegram_message_id=row["telegram_message_id"],
            telegram_update_id=row["telegram_update_id"],
            file_hash=row["file_hash"],
            file_path=row["file_path"],
            final_path=row["final_path"],
            supplier_tax_id=row["supplier_tax_id"],
            supplier_name=row["supplier_name"],
            invoice_data=json.loads(row["invoice_data"]),
            summary=json.loads(row["summary"]),
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

        logger.info("invoice_draft_created", draft_id=draft_id, supplier_tax_id=supplier_tax_id)
        return draft

    async def get_draft(self, draft_id: str) -> InvoiceDraft | None:
        """Get a draft by ID."""
        await self.initialize()
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM invoice_drafts WHERE draft_id = $1", uuid.UUID(draft_id))
            if row:
                return self._row_to_draft(row)
            return None

    async def get_draft_by_update_id(self, update_id: int) -> InvoiceDraft | None:
        """Get a draft by Telegram update_id (for idempotency)."""
        await self.initialize()
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM invoice_drafts WHERE telegram_update_id = $1", update_id)
            if row:
                return self._row_to_draft(row)
            return None

    async def get_draft_by_file_hash(self, file_hash: str) -> InvoiceDraft | None:
        """Get a draft by file hash (for duplicate detection)."""
        await self.initialize()
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM invoice_drafts WHERE file_hash = $1 ORDER BY created_at DESC LIMIT 1", file_hash
            )
            if row:
                return self._row_to_draft(row)
            return None

    async def get_pending_drafts(
        self,
        telegram_user_id: int | None = None,
        telegram_chat_id: int | None = None,
    ) -> list[InvoiceDraft]:
        """Get all pending approval drafts, optionally filtered by user/chat."""
        await self.initialize()
        pool = await self._get_pool()

        query = "SELECT * FROM invoice_drafts WHERE status = 'PENDING_APPROVAL'"
        params: list[Any] = []
        param_num = 1

        if telegram_user_id:
            query += f" AND telegram_user_id = ${param_num}"
            params.append(telegram_user_id)
            param_num += 1

        if telegram_chat_id:
            query += f" AND telegram_chat_id = ${param_num}"
            params.append(telegram_chat_id)
            param_num += 1

        query += " ORDER BY created_at DESC"

        async with pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [self._row_to_draft(row) for row in rows]

    async def update_draft_status(
        self,
        draft_id: str,
        status: str,
        dolibarr_invoice_id: int | None = None,
    ) -> InvoiceDraft | None:
        """Update draft status."""
        await self.initialize()
        pool = await self._get_pool()

        valid_statuses = {
            "PENDING_APPROVAL",
            "APPROVED",
            "REJECTED",
            "CREATING_DOLIBARR",
            "REGISTERED",
            "REQUIRES_REVIEW",
            "REQUIRES_CLEANUP",
        }
        if status not in valid_statuses:
            raise ValueError(f"Invalid status: {status}")

        update_fields = ["status = $2", "updated_at = NOW()"]
        params: list[Any] = [uuid.UUID(draft_id), status]
        param_num = 3

        if status == "APPROVED":
            update_fields.append(f"approved_at = ${param_num}")
            params.append(datetime.utcnow())
            param_num += 1
        elif status == "REJECTED":
            update_fields.append(f"rejected_at = ${param_num}")
            params.append(datetime.utcnow())
            param_num += 1

        if dolibarr_invoice_id is not None:
            update_fields.append(f"dolibarr_invoice_id = ${param_num}")
            params.append(dolibarr_invoice_id)
            param_num += 1

        query = f"""
            UPDATE invoice_drafts
            SET {", ".join(update_fields)}
            WHERE draft_id = $1
            RETURNING *
        """

        async with pool.acquire() as conn:
            row = await conn.fetchrow(query, *params)
            if row:
                return self._row_to_draft(row)
            return None

    async def update_invoice_data(
        self, draft_id: str, invoice_data: dict[str, Any], summary: dict[str, Any]
    ) -> InvoiceDraft | None:
        """Update invoice data (for corrections)."""
        await self.initialize()
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE invoice_drafts
                SET invoice_data = $2, summary = $3, updated_at = NOW()
                WHERE draft_id = $1
                RETURNING *
            """,
                uuid.UUID(draft_id),
                json.dumps(invoice_data),
                json.dumps(summary),
            )

            if row:
                return self._row_to_draft(row)
            return None

    async def mark_requires_review(self, draft_id: str, reason: str) -> InvoiceDraft | None:
        """Mark draft as requiring review with reason in invoice_data."""
        await self.initialize()
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            # Get current invoice_data
            row = await conn.fetchrow(
                "SELECT invoice_data FROM invoice_drafts WHERE draft_id = $1", uuid.UUID(draft_id)
            )
            if not row:
                return None

            invoice_data = json.loads(row["invoice_data"])
            invoice_data["_review_reason"] = reason

            row = await conn.fetchrow(
                """
                UPDATE invoice_drafts
                SET status = 'REQUIRES_REVIEW', invoice_data = $2, updated_at = NOW()
                WHERE draft_id = $1
                RETURNING *
            """,
                uuid.UUID(draft_id),
                json.dumps(invoice_data),
            )

            if row:
                return self._row_to_draft(row)
            return None

    def _row_to_draft(self, row: dict[str, Any]) -> InvoiceDraft:
        return InvoiceDraft(
            draft_id=str(row["draft_id"]),
            correlation_id=str(row["correlation_id"]),
            telegram_user_id=row["telegram_user_id"],
            telegram_chat_id=row["telegram_chat_id"],
            telegram_message_id=row["telegram_message_id"],
            telegram_update_id=row["telegram_update_id"],
            file_hash=row["file_hash"],
            file_path=row["file_path"],
            final_path=row["final_path"],
            supplier_tax_id=row["supplier_tax_id"],
            supplier_name=row["supplier_name"],
            invoice_data=json.loads(row["invoice_data"]),
            summary=json.loads(row["summary"]),
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            approved_at=row["approved_at"],
            rejected_at=row["rejected_at"],
            dolibarr_invoice_id=row["dolibarr_invoice_id"],
        )


# Global instance
invoice_draft_service = InvoiceDraftService()


async def get_invoice_draft_service() -> InvoiceDraftService:
    """Dependency injection for InvoiceDraftService."""
    return invoice_draft_service
