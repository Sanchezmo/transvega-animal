"""
Invoice Processing Integration Service
Wraps DolibarrClient for invoice-specific operations.
"""

from typing import Any

import structlog

from app.adapters.dolibarr.client import DolibarrClient
from app.core.config import get_settings

logger = structlog.get_logger()


class InvoiceIntegrationService:
    """Service for invoice-related Dolibarr operations."""

    def __init__(self, dolibarr_client: DolibarrClient = None):
        if dolibarr_client:
            self.client = dolibarr_client
        else:
            settings = get_settings()
            self.client = DolibarrClient(
                base_url=settings.DOLIBARR_API_URL,
                api_key=settings.DOLIBARR_API_KEY,
            )

    async def __aenter__(self):
        await self.client.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.__aexit__(exc_type, exc_val, exc_tb)

    async def get_supplier_by_tax_id(self, tax_id: str) -> dict[str, Any] | None:
        """
        Find a supplier by tax_id (CIF/NIF).
        Searches through all suppliers and matches the vat_number field.
        """
        try:
            suppliers = await self.client.list_suppliers(limit=500)
            for supplier in suppliers:
                if supplier.get("vat_number", "").upper() == tax_id.upper().replace("-", ""):
                    return supplier
                # Also check other possible fields
                if supplier.get("vatnumber", "").upper() == tax_id.upper().replace("-", ""):
                    return supplier
            return None
        except Exception as e:
            logger.error("get_supplier_by_tax_id_failed", tax_id=tax_id, error=str(e))
            return None

    async def get_supplier_by_name(self, name: str) -> dict[str, Any] | None:
        """Find supplier by name (fuzzy match)."""
        try:
            suppliers = await self.client.list_suppliers(limit=500)
            name_lower = name.lower()
            for supplier in suppliers:
                if name_lower in supplier.get("name", "").lower():
                    return supplier
            return None
        except Exception as e:
            logger.error("get_supplier_by_name_failed", name=name, error=str(e))
            return None

    async def invoice_exists(self, supplier_tax_id: str, invoice_number: str) -> bool:
        """
        Check if a supplier invoice already exists.
        """
        try:
            # First find supplier
            supplier = await self.get_supplier_by_tax_id(supplier_tax_id)
            if not supplier:
                return False

            supplier_id = supplier.get("id")
            if not supplier_id:
                return False

            # List supplier invoices and check for duplicate number
            invoices = await self.client.list_supplier_invoices(thirdparty_id=supplier_id, limit=500)
            for invoice in invoices:
                if invoice.get("ref", "").upper() == invoice_number.upper():
                    return True
                if invoice.get("ref_supplier", "").upper() == invoice_number.upper():
                    return True
            return False
        except Exception as e:
            logger.error(
                "invoice_exists_check_failed",
                tax_id=supplier_tax_id,
                invoice_number=invoice_number,
                error=str(e),
            )
            # Fail closed: assume duplicate to avoid creating duplicate
            return True

    async def create_supplier_invoice(
        self,
        supplier_tax_id: str,
        invoice_number: str,
        invoice_date: str,
        lines: list[dict],
        taxes: list[dict],
        currency: str = "EUR",
        attached_file: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a supplier invoice in Dolibarr.
        """
        try:
            # Find supplier
            supplier = await self.get_supplier_by_tax_id(supplier_tax_id)
            if not supplier:
                raise ValueError(f"Supplier with tax_id {supplier_tax_id} not found in Dolibarr")

            supplier_id = supplier.get("id")

            # Prepare invoice data
            invoice_data = {
                "socid": supplier_id,
                "ref": invoice_number,
                "ref_supplier": invoice_number,
                "date": invoice_date,
                "currency": currency,
                "status": 0,  # Draft
            }

            # Create invoice
            result = await self.client.create_supplier_invoice(invoice_data)
            invoice_id = result.get("id") if isinstance(result, dict) else result

            if not invoice_id:
                raise ValueError("Failed to create invoice - no ID returned")

            # Add lines
            for line in lines:
                line_data = {
                    "product_id": line.get("product_id", 0),
                    "description": line.get("description", ""),
                    "qty": line.get("quantity", 1.0),
                    "subprice": line.get("unit_price", 0.0),
                    "total_ht": line.get("total", 0.0),
                    "vat_src_code": line.get("vat_code", ""),
                }
                await self.client.add_supplier_invoice_line(invoice_id, line_data)

            # Upload attached file if provided
            if attached_file:
                try:
                    with open(attached_file, "rb") as f:
                        file_data = f.read()
                    filename = attached_file.split("/")[-1]
                    await self.client.upload_document("supplierinvoices", invoice_id, file_data, filename)
                except Exception as e:
                    logger.warning("file_upload_failed", file=attached_file, error=str(e))

            # Return full invoice
            full_invoice = await self.client.get_supplier_invoice(invoice_id)
            return full_invoice

        except Exception as e:
            logger.error("create_supplier_invoice_failed", error=str(e))
            raise

    async def validate_supplier_invoice(self, invoice_id: int) -> dict[str, Any]:
        """Validate a supplier invoice (change status from draft to validated)."""
        return await self.client.validate_supplier_invoice(invoice_id)

    async def get_supplier_invoice(self, invoice_id: int) -> dict[str, Any]:
        """Get supplier invoice by ID."""
        return await self.client.get_supplier_invoice(invoice_id)


async def get_invoice_integration_service() -> InvoiceIntegrationService:
    """Dependency injection for InvoiceIntegrationService."""
    return InvoiceIntegrationService()
