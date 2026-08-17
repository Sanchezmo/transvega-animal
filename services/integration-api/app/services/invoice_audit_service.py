"""
Invoice Audit Service - Registra eventos técnicos de procesamiento de facturas en PostgreSQL.
"""

import hashlib
import uuid
from typing import Any
from uuid import UUID

import structlog

from app.core.database import get_db_pool
from app.services.audit_logger import AuditLogger

logger = structlog.get_logger()


class InvoiceAuditService:
    """Servicio para auditoría técnica de eventos de facturas."""

    # Event types for invoice processing
    INVOICE_EVENTS = {
        "received": "invoice.received",
        "downloaded": "invoice.downloaded",
        "parsed": "invoice.parsed",
        "validation_failed": "invoice.validation_failed",
        "pending_approval": "invoice.pending_approval",
        "corrected": "invoice.corrected",
        "approved": "invoice.approved",
        "supplier_created": "invoice.supplier_created",
        "dolibarr_header_created": "invoice.dolibarr_header_created",
        "dolibarr_lines_created": "invoice.dolibarr_lines_created",
        "document_attached": "invoice.document_attached",
        "registered": "invoice.registered",
        "failed": "invoice.failed",
        "rejected": "invoice.rejected",
        "duplicate": "invoice.duplicate",
        "requires_cleanup": "invoice.requires_cleanup",
    }

    def __init__(self) -> None:
        self._pool = None
        self._audit_logger: AuditLogger | None = None

    async def _get_pool(self):
        if self._pool is None:
            self._pool = await get_db_pool()
        return self._pool

    async def _get_audit_logger(self) -> AuditLogger:
        if self._audit_logger is None:
            pool = await self._get_pool()
            self._audit_logger = AuditLogger(pool)
        return self._audit_logger

    def _generate_correlation_id(self) -> UUID:
        return uuid.uuid4()

    def _hash_file_content(self, file_content: bytes) -> str:
        return hashlib.sha256(file_content).hexdigest()

    async def log_event(
        self,
        *,
        event: str,
        correlation_id: UUID | str | None = None,
        telegram_user_id: int | None = None,
        telegram_chat_id: int | None = None,
        telegram_message_id: int | None = None,
        telegram_update_id: int | None = None,
        file_hash: str | None = None,
        draft_id: str | None = None,
        status: str | None = None,
        dolibarr_invoice_id: int | None = None,
        dolibarr_invoice_ref: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        duration_ms: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Log an invoice processing event to the audit log.

        Args:
            event: Event type (one of INVOICE_EVENTS values)
            correlation_id: Correlation ID for tracing
            telegram_user_id: Telegram user ID
            telegram_chat_id: Telegram chat ID
            telegram_message_id: Telegram message ID
            telegram_update_id: Telegram update ID
            file_hash: SHA256 hash of the invoice file
            draft_id: Invoice draft ID
            status: Current status
            dolibarr_invoice_id: Dolibarr invoice ID
            dolibarr_invoice_ref: Dolibarr invoice reference
            error_code: Error code if failed
            error_message: Error message if failed
            duration_ms: Duration of operation in milliseconds
            metadata: Additional metadata
        """
        try:
            audit_logger = await self._get_audit_logger()

            corr_id = UUID(correlation_id) if correlation_id else self._generate_correlation_id()

            # Build request_id from telegram info
            request_id = uuid.uuid4()
            if telegram_update_id:
                request_id = uuid.uuid5(uuid.NAMESPACE_DNS, f"tg-{telegram_update_id}")

            # Prepare metadata
            meta = metadata or {}
            if telegram_user_id:
                meta["telegram_user_id"] = telegram_user_id
            if telegram_chat_id:
                meta["telegram_chat_id"] = telegram_chat_id
            if telegram_message_id:
                meta["telegram_message_id"] = telegram_message_id
            if telegram_update_id:
                meta["telegram_update_id"] = telegram_update_id
            if file_hash:
                meta["file_hash"] = file_hash
            if draft_id:
                meta["draft_id"] = draft_id
            if dolibarr_invoice_id:
                meta["dolibarr_invoice_id"] = dolibarr_invoice_id
            if dolibarr_invoice_ref:
                meta["dolibarr_invoice_ref"] = dolibarr_invoice_ref
            if status:
                meta["status"] = status

            # Use the audit logger
            await audit_logger.log(
                request_id=request_id,
                correlation_id=corr_id,
                agent_id="invoice_processing",
                agent_name="InvoiceProcessingAgent",
                agent_roles=["invoice_processing"],
                method="INTERNAL",
                path=f"/invoice/{event}",
                query_params={},
                request_body=meta if meta else None,
                resource_type="supplier_invoice",
                resource_id=str(dolibarr_invoice_id) if dolibarr_invoice_id else draft_id,
                action=event,
                previous_state=None,
                new_state={"status": status} if status else None,
                status_code=200 if not error_code else 500,
                success=error_code is None,
                error_code=error_code,
                error_message=error_message,
                error_details=None,
                duration_ms=duration_ms or 0,
                idempotency_key=str(telegram_update_id) if telegram_update_id else None,
                idempotent=bool(telegram_update_id),
            )

            logger.debug("invoice_audit_logged", event=event, correlation_id=str(corr_id))

        except Exception as e:
            # Don't fail the main operation due to audit logging failure
            logger.error("invoice_audit_log_failed", event=event, error=str(e))

    # Convenience methods for each event type
    async def log_received(
        self,
        correlation_id: UUID | str,
        telegram_user_id: int,
        telegram_chat_id: int,
        telegram_message_id: int,
        telegram_update_id: int,
        file_hash: str,
        file_size: int,
        mime_type: str,
    ) -> None:
        await self.log_event(
            event=self.INVOICE_EVENTS["received"],
            correlation_id=correlation_id,
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_chat_id,
            telegram_message_id=telegram_message_id,
            telegram_update_id=telegram_update_id,
            file_hash=file_hash,
            status="RECEIVED",
            metadata={"file_size": file_size, "mime_type": mime_type},
        )

    async def log_downloaded(
        self,
        correlation_id: UUID | str,
        telegram_update_id: int,
        file_hash: str,
        duration_ms: float,
    ) -> None:
        await self.log_event(
            event=self.INVOICE_EVENTS["downloaded"],
            correlation_id=correlation_id,
            telegram_update_id=telegram_update_id,
            file_hash=file_hash,
            status="DOWNLOADED",
            duration_ms=duration_ms,
        )

    async def log_parsed(
        self,
        correlation_id: UUID | str,
        telegram_update_id: int,
        file_hash: str,
        supplier_tax_id: str,
        invoice_number: str,
        duration_ms: float,
    ) -> None:
        await self.log_event(
            event=self.INVOICE_EVENTS["parsed"],
            correlation_id=correlation_id,
            telegram_update_id=telegram_update_id,
            file_hash=file_hash,
            status="PARSED",
            metadata={"supplier_tax_id": supplier_tax_id, "invoice_number": invoice_number},
            duration_ms=duration_ms,
        )

    async def log_validation_failed(
        self,
        correlation_id: UUID | str,
        telegram_update_id: int,
        file_hash: str,
        errors: list[str],
        draft_id: str | None = None,
    ) -> None:
        await self.log_event(
            event=self.INVOICE_EVENTS["validation_failed"],
            correlation_id=correlation_id,
            telegram_update_id=telegram_update_id,
            file_hash=file_hash,
            draft_id=draft_id,
            status="VALIDATION_FAILED",
            error_code="VALIDATION_ERROR",
            error_message="; ".join(errors),
        )

    async def log_pending_approval(
        self,
        correlation_id: UUID | str,
        telegram_update_id: int,
        file_hash: str,
        draft_id: str,
        supplier_tax_id: str,
        invoice_number: str,
    ) -> None:
        await self.log_event(
            event=self.INVOICE_EVENTS["pending_approval"],
            correlation_id=correlation_id,
            telegram_update_id=telegram_update_id,
            file_hash=file_hash,
            draft_id=draft_id,
            status="PENDING_APPROVAL",
            metadata={"supplier_tax_id": supplier_tax_id, "invoice_number": invoice_number},
        )

    async def log_corrected(
        self,
        correlation_id: UUID | str,
        telegram_update_id: int,
        file_hash: str,
        draft_id: str,
        corrections: dict[str, Any],
    ) -> None:
        await self.log_event(
            event=self.INVOICE_EVENTS["corrected"],
            correlation_id=correlation_id,
            telegram_update_id=telegram_update_id,
            file_hash=file_hash,
            draft_id=draft_id,
            status="CORRECTED",
            metadata={"corrections": corrections},
        )

    async def log_approved(
        self,
        correlation_id: UUID | str,
        telegram_update_id: int,
        file_hash: str,
        draft_id: str,
    ) -> None:
        await self.log_event(
            event=self.INVOICE_EVENTS["approved"],
            correlation_id=correlation_id,
            telegram_update_id=telegram_update_id,
            file_hash=file_hash,
            draft_id=draft_id,
            status="APPROVED",
        )

    async def log_supplier_created(
        self,
        correlation_id: UUID | str,
        telegram_update_id: int,
        supplier_tax_id: str,
        supplier_name: str,
        dolibarr_supplier_id: int,
    ) -> None:
        await self.log_event(
            event=self.INVOICE_EVENTS["supplier_created"],
            correlation_id=correlation_id,
            telegram_update_id=telegram_update_id,
            status="SUPPLIER_CREATED",
            metadata={
                "supplier_tax_id": supplier_tax_id,
                "supplier_name": supplier_name,
                "dolibarr_supplier_id": dolibarr_supplier_id,
            },
        )

    async def log_dolibarr_header_created(
        self,
        correlation_id: UUID | str,
        telegram_update_id: int,
        file_hash: str,
        draft_id: str,
        dolibarr_invoice_id: int,
        dolibarr_invoice_ref: str,
    ) -> None:
        await self.log_event(
            event=self.INVOICE_EVENTS["dolibarr_header_created"],
            correlation_id=correlation_id,
            telegram_update_id=telegram_update_id,
            file_hash=file_hash,
            draft_id=draft_id,
            status="DOLIBARR_HEADER_CREATED",
            dolibarr_invoice_id=dolibarr_invoice_id,
            dolibarr_invoice_ref=dolibarr_invoice_ref,
        )

    async def log_dolibarr_lines_created(
        self,
        correlation_id: UUID | str,
        telegram_update_id: int,
        file_hash: str,
        draft_id: str,
        dolibarr_invoice_id: int,
        line_count: int,
    ) -> None:
        await self.log_event(
            event=self.INVOICE_EVENTS["dolibarr_lines_created"],
            correlation_id=correlation_id,
            telegram_update_id=telegram_update_id,
            file_hash=file_hash,
            draft_id=draft_id,
            status="DOLIBARR_LINES_CREATED",
            dolibarr_invoice_id=dolibarr_invoice_id,
            metadata={"line_count": line_count},
        )

    async def log_document_attached(
        self,
        correlation_id: UUID | str,
        telegram_update_id: int,
        file_hash: str,
        draft_id: str,
        dolibarr_invoice_id: int,
        success: bool,
    ) -> None:
        await self.log_event(
            event=self.INVOICE_EVENTS["document_attached"],
            correlation_id=correlation_id,
            telegram_update_id=telegram_update_id,
            file_hash=file_hash,
            draft_id=draft_id,
            status="DOCUMENT_ATTACHED" if success else "DOCUMENT_ATTACH_FAILED",
            dolibarr_invoice_id=dolibarr_invoice_id,
            success=success,
            error_code="ATTACHMENT_FAILED" if not success else None,
            error_message="Failed to attach document to Dolibarr invoice" if not success else None,
        )

    async def log_registered(
        self,
        correlation_id: UUID | str,
        telegram_update_id: int,
        file_hash: str,
        draft_id: str,
        dolibarr_invoice_id: int,
        dolibarr_invoice_ref: str,
        duration_ms: float,
    ) -> None:
        await self.log_event(
            event=self.INVOICE_EVENTS["registered"],
            correlation_id=correlation_id,
            telegram_update_id=telegram_update_id,
            file_hash=file_hash,
            draft_id=draft_id,
            status="REGISTERED",
            dolibarr_invoice_id=dolibarr_invoice_id,
            dolibarr_invoice_ref=dolibarr_invoice_ref,
            duration_ms=duration_ms,
        )

    async def log_failed(
        self,
        correlation_id: UUID | str,
        telegram_update_id: int,
        file_hash: str,
        draft_id: str | None,
        error_code: str,
        error_message: str,
        status: str = "FAILED",
    ) -> None:
        await self.log_event(
            event=self.INVOICE_EVENTS["failed"],
            correlation_id=correlation_id,
            telegram_update_id=telegram_update_id,
            file_hash=file_hash,
            draft_id=draft_id,
            status=status,
            error_code=error_code,
            error_message=error_message,
        )

    async def log_rejected(
        self,
        correlation_id: UUID | str,
        telegram_update_id: int,
        file_hash: str,
        draft_id: str,
        reason: str,
    ) -> None:
        await self.log_event(
            event=self.INVOICE_EVENTS["rejected"],
            correlation_id=correlation_id,
            telegram_update_id=telegram_update_id,
            file_hash=file_hash,
            draft_id=draft_id,
            status="REJECTED",
            metadata={"rejection_reason": reason},
        )

    async def log_duplicate(
        self,
        correlation_id: UUID | str,
        telegram_update_id: int,
        file_hash: str,
        supplier_tax_id: str,
        invoice_number: str,
    ) -> None:
        await self.log_event(
            event=self.INVOICE_EVENTS["duplicate"],
            correlation_id=correlation_id,
            telegram_update_id=telegram_update_id,
            file_hash=file_hash,
            status="DUPLICATE",
            error_code="DUPLICATE_INVOICE",
            error_message=f"Duplicate invoice {invoice_number} for supplier {supplier_tax_id}",
            metadata={"supplier_tax_id": supplier_tax_id, "invoice_number": invoice_number},
        )

    async def log_requires_cleanup(
        self,
        correlation_id: UUID | str,
        telegram_update_id: int,
        file_hash: str,
        draft_id: str,
        dolibarr_invoice_id: int | None,
        reason: str,
    ) -> None:
        await self.log_event(
            event=self.INVOICE_EVENTS["requires_cleanup"],
            correlation_id=correlation_id,
            telegram_update_id=telegram_update_id,
            file_hash=file_hash,
            draft_id=draft_id,
            status="REQUIRES_CLEANUP",
            dolibarr_invoice_id=dolibarr_invoice_id,
            error_code="PARTIAL_FAILURE",
            error_message=reason,
        )


# Global instance
invoice_audit_service = InvoiceAuditService()


async def get_invoice_audit_service() -> InvoiceAuditService:
    """Dependency injection for InvoiceAuditService."""
    return invoice_audit_service
