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


class SupplierLookupError(Exception):
    """Exception raised when supplier lookup fails due to integration error (not not found)."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class SupplierNotFoundError(Exception):
    """Exception raised when supplier is genuinely not found (404/empty result)."""
    pass


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

    async def _find_supplier_by_tax_id(self, tax_id: str) -> dict[str, Any] | None:
        """
        Find a supplier by normalized tax_id (CIF/NIF) using paginated search.
        Returns the thirdparty if found (whether supplier or not), None if not found.
        Raises SupplierLookupError on integration errors.
        """
        if not tax_id:
            return None

        try:
            # Use paginated search to find thirdparty by tax_id
            party = await self.client.find_thirdparty_by_tax_id(tax_id)
            return party
        except Exception as e:
            # Distinguish integration errors from not found
            # DolibarrException with 404/empty would be not found, others are integration errors
            logger.error("supplier_lookup_failed", tax_id_present=bool(tax_id), error=str(e))
            # Re-raise as SupplierLookupError for integration errors
            raise SupplierLookupError(f"Failed to lookup supplier: {e}") from e

    async def find_supplier_or_thirdparty(self, tax_id: str) -> tuple[dict[str, Any] | None, bool]:
        """
        Find supplier/thirdparty by tax_id.
        Returns (party, is_supplier) tuple.
        - party: the thirdparty dict if found, None if not found
        - is_supplier: True if party exists and is marked as supplier (fournisseur=1)
        Raises SupplierLookupError on integration errors.
        """
        party = await self._find_supplier_by_tax_id(tax_id)
        if party is None:
            return None, False

        is_supplier = party.get("fournisseur") == 1 or party.get("supplier") == 1
        return party, is_supplier

    async def get_supplier_by_tax_id(self, tax_id: str) -> dict[str, Any] | None:
        """
        Find a supplier by tax_id (CIF/NIF).
        Returns the supplier if found and is a supplier (fournisseur=1).
        """
        logger.info("supplier_lookup_started", tax_id_present=bool(tax_id))
        supplier = await self._find_supplier_by_tax_id(tax_id)
        if supplier:
            logger.info("supplier_found", supplier_id=supplier.get("id"))
        else:
            logger.info("supplier_not_found", tax_id_present=bool(tax_id))
        return supplier

    async def _ensure_supplier(self, tax_id: str, name: str, address: str | None = None,
                               email: str | None = None, phone: str | None = None) -> dict[str, Any]:
        """
        Ensure a supplier exists in Dolibarr.
        - If exists as supplier, return it
        - If exists as client/other, enable as supplier (preserving client status)
        - If not exists, create new supplier
        Raises SupplierLookupError on integration errors.
        """
        # Find supplier/thirdparty using paginated search
        party, is_supplier = await self.find_supplier_or_thirdparty(tax_id)

        if party and is_supplier:
            logger.info("supplier_already_exists", supplier_id=party.get("id"))
            return party

        if party and not is_supplier:
            # Exists but not a supplier - enable it, preserving client status
            logger.info("supplier_enable_started", thirdparty_id=party.get("id"))
            await self.client.update_thirdparty(party["id"], {
                "fournisseur": 1,
                "client": party.get("client", 1),  # Keep client status if it was a client
            })
            logger.info("supplier_enable_completed", thirdparty_id=party["id"])
            return await self.client.get_thirdparty(party["id"])

        # Not found - create new supplier
        logger.info("supplier_create_started", name=name, tax_id_present=bool(tax_id))
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

        logger.info("supplier_create_completed", supplier_id=supplier_id)
        return await self.client.get_supplier(supplier_id)

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
        Returns True if duplicate found, False if not found.
        Raises SupplierLookupError on integration errors (don't fail closed).
        """
        # First find supplier - this will raise SupplierLookupError on integration errors
        supplier = await self.get_supplier_by_tax_id(supplier_tax_id)
        if not supplier:
            # Supplier not found - not a duplicate
            return False

        supplier_id = supplier.get("id")
        if not supplier_id:
            return False

        try:
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
                tax_id_present=bool(supplier_tax_id),
                invoice_number=invoice_number,
                error=str(e),
            )
            # Integration error - don't fail closed, raise to prevent accidental creation
            raise SupplierLookupError(f"Failed to check duplicate invoice: {e}") from e

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
        logger.info("supplier_invoice_create_started", supplier_tax_id=supplier_tax_id, invoice_number=invoice_number)

        try:
            # Find or create supplier
            supplier = await self._ensure_supplier(supplier_tax_id, invoice_number)
            supplier_id = supplier.get("id")

            # Check duplicate
            if await self.invoice_exists(supplier_tax_id, invoice_number):
                raise ValueError(f"Supplier invoice {invoice_number} already exists for this supplier")

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
                    logger.info("supplier_invoice_attachment_uploaded", invoice_id=invoice_id)
                except Exception as e:
                    logger.error("document_attachment_failed", invoice_id=invoice_id, file=attached_file, error=str(e))
                    # Attachment failed but invoice exists - return special error with invoice_id for cleanup
                    raise DocumentAttachmentError(f"Failed to attach document: {e}", invoice_id=invoice_id)

            # Return full invoice
            full_invoice = await self.client.get_supplier_invoice(invoice_id)
            logger.info("supplier_invoice_created", invoice_id=invoice_id, supplier_id=supplier_id)
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
        return await self._ensure_supplier(tax_id, name, address, email, phone)


async def get_invoice_integration_service() -> InvoiceIntegrationService:
    """Dependency injection for InvoiceIntegrationService."""
    return InvoiceIntegrationService()
