"""
Invoice Processing Integration Service
Wraps DolibarrClient for invoice-specific operations.
"""

from typing import Any

import structlog

from app.adapters.dolibarr.client import DolibarrClient
from app.core.config import get_settings

logger = structlog.get_logger()


class DocumentAttachmentError(Exception):
    """Exception raised when document attachment to Dolibarr invoice fails."""

    def __init__(self, message: str, invoice_id: int | None = None):
        super().__init__(message)
        self.invoice_id = invoice_id


class InvoiceIntegrationService:
    """Service for invoice-related Dolibarr operations."""

    def __init__(self, dolibarr_client: DolibarrClient | None = None) -> None:
        if dolibarr_client:
            self.client = dolibarr_client
        else:
            settings = get_settings()
            self.client = DolibarrClient(
                base_url=settings.DOLIBARR_API_URL,
                api_key=settings.DOLIBARR_API_KEY,
            )

    async def __aenter__(self) -> "InvoiceIntegrationService":
        await self.client.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> None:
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
                    return supplier  # type: ignore[no-any-return]
                # Also check other possible fields
                if supplier.get("vatnumber", "").upper() == tax_id.upper().replace("-", ""):
                    return supplier  # type: ignore[no-any-return]
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
                    return supplier  # type: ignore[no-any-return]
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
        lines: list[dict[str, Any]],
        taxes: list[dict[str, Any]],
        currency: str = "EUR",
        attached_file: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a supplier invoice in Dolibarr with proper VAT per line.
        Each line must have its own VAT rate (tva_tx) sent to Dolibarr.
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

            # Add lines with proper VAT per line
            for line in lines:
                vat_rate = line.get("vat_rate")
                if vat_rate is None:
                    # Try to get from taxes array
                    vat_rate = None
                    for tax in taxes:
                        if tax.get("type", "").upper() in ("IVA", "VAT"):
                            vat_rate = float(tax.get("rate", 0))
                            break

                    if vat_rate is None:
                        # NO DEFAULT - raise error to require review
                        raise ValueError(
                            f"Line '{line.get('description')}' missing vat_rate. "
                            f"No default VAT allowed - requires manual review."
                        )

                # Dolibarr expects tva_tx as the VAT rate percentage
                line_data = {
                    "product_id": line.get("product_id", 0),
                    "description": line.get("description", ""),
                    "qty": line.get("quantity", 1.0),
                    "subprice": line.get("unit_price", 0.0),
                    "total_ht": line.get("total", 0.0),
                    "tva_tx": vat_rate,  # VAT rate per line (required by Dolibarr)
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
                    logger.error("document_attachment_failed", invoice_id=invoice_id, file=attached_file, error=str(e))
                    # Attachment failed but invoice exists - return special error with invoice_id for cleanup
                    raise DocumentAttachmentError(f"Failed to attach document: {e}", invoice_id=invoice_id)

            # Return full invoice
            full_invoice = await self.client.get_supplier_invoice(invoice_id)
            return full_invoice  # type: ignore[no-any-return]

        except Exception as e:
            logger.error("create_supplier_invoice_failed", error=str(e))
            raise

    async def validate_supplier_invoice(self, invoice_id: int) -> dict[str, Any]:
        """Validate a supplier invoice (change status from draft to validated)."""
        return await self.client.validate_supplier_invoice(invoice_id)  # type: ignore[no-any-return]

    async def get_supplier_invoice(self, invoice_id: int) -> dict[str, Any]:
        """Get supplier invoice by ID."""
        return await self.client.get_supplier_invoice(invoice_id)  # type: ignore[no-any-return]

    async def create_supplier(
        self,
        name: str,
        tax_id: str,
        address: str | None = None,
        email: str | None = None,
        phone: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a new supplier in Dolibarr.
        Only creates with known/reliable data - no invented fields.
        """
        try:
            supplier_data = {
                "name": name,
                "vat_number": tax_id,
                "fournisseur": 1,
                "client": 0,
            }
            if address:
                supplier_data["address"] = address
            if email:
                supplier_data["email"] = email
            if phone:
                supplier_data["phone"] = phone

            result = await self.client.create_supplier(supplier_data)
            supplier_id = result.get("id") if isinstance(result, dict) else result

            if not supplier_id:
                raise ValueError("Failed to create supplier - no ID returned")

            # Return full supplier
            full_supplier = await self.client.get_supplier(supplier_id)
            return full_supplier  # type: ignore[no-any-return]

        except Exception as e:
            logger.error("create_supplier_failed", name=name, tax_id=tax_id, error=str(e))
            raise


async def get_invoice_integration_service() -> InvoiceIntegrationService:
    """Dependency injection for InvoiceIntegrationService."""
    return InvoiceIntegrationService()
