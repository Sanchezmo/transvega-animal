"""Invoice Processing Agent
Handles extraction, validation, and registration of supplier invoices.
"""

import asyncio
import hashlib
import mimetypes
import os
import shutil
from typing import Any

import structlog

# We'll import the ModelRouter and privacy router later
from app.core.model_router import create_model_router

# Assuming privacy router exists; if not, we'll define a simple stub
try:
    from app.core.privacy_router import PrivacyScope, privacy_router
except ImportError:
    # Fallback stub
    from enum import Enum

    class _PrivacyScope(Enum):
        LOCAL_ONLY = "LOCAL_ONLY"
        CLOUD_ALLOWED = "CLOUD_ALLOWED"

    PrivacyScope = _PrivacyScope

    async def privacy_router(content: str, filename: str = "") -> PrivacyScope:
        # Simple stub: treat everything as LOCAL_ONLY for safety
        return PrivacyScope.LOCAL_ONLY


logger = structlog.get_logger()

# Pydantic model for invoice (simple)
try:
    from pydantic import BaseModel, Field, validator
except ImportError:
    # If pydantic not installed, we'll skip validation for now; but we assume it's present.
    pass


class InvoiceLine(BaseModel):
    description: str
    quantity: float = 1.0
    unit_price: float
    total: float
    vat_rate: float | None = None

    @validator("total")
    @classmethod
    def total_matches(cls, v: float, values: dict[str, Any]) -> float:
        qty = values.get("quantity")
        price = values.get("unit_price")
        if qty is not None and price is not None:
            expected = qty * price
            if abs(v - expected) > 0.01:
                raise ValueError(f"Total {v} does not match quantity * unit_price ({expected})")
        return v


class SupplierInfo(BaseModel):
    name: str
    tax_id: str  # CIF/NIF


class InvoiceData(BaseModel):
    supplier: SupplierInfo
    invoice: dict[str, Any] = Field(..., description="Invoice metadata")
    lines: list[InvoiceLine]
    taxes: list[dict[str, Any]] = Field(default_factory=list)
    subtotal: float
    tax_total: float
    total: float
    currency: str = "EUR"

    @validator("total")
    @classmethod
    def total_matches_sum(cls, v: float, values: dict[str, Any]) -> float:
        subtotal = values.get("subtotal", 0.0)
        tax_total = values.get("tax_total", 0.0)
        if abs(v - (subtotal + tax_total)) > 0.01:
            raise ValueError(f"Total {v} does not match subtotal + tax_total ({subtotal + tax_total})")
        return v


class InvoiceProcessingAgent:
    """
    Agent that processes supplier invoices (PDF or image) through:
    1. Privacy check (must be LOCAL_ONLY)
    2. Text extraction (direct PDF text or OCR via Ollama vision)
    3. Structured extraction via Ollama (local LLM) to JSON
    4. Validation with Pydantic
    5. Deterministic checks (sums, VAT, duplicate)
    6. Lookup supplier in Dolibarr via InvoiceIntegrationService
    7. Return result for human approval
    8. On approval, create invoice in Dolibarr
    """

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.agent_id = "invoice_processing"
        self.agent_name = "Invoice Processing Agent"

        # Initialize ModelRouter
        ollama_endpoint = config.get("OLLAMA_ENDPOINT", "http://ollama:11434")
        ollama_model = config.get("OLLAMA_MODEL", "llama3.1:8b")
        ollama_vision_model = config.get("OLLAMA_VISION_MODEL", "llava:7b")
        nvidia_api_key = config.get("NVIDIA_API_KEY", "")
        nvidia_base_url = config.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
        self.router = create_model_router(
            ollama_endpoint=ollama_endpoint,
            ollama_model=ollama_model,
            ollama_vision_model=ollama_vision_model,
            nvidia_api_key=nvidia_api_key,
            nvidia_base_url=nvidia_base_url,
        )

        # Storage roots - separate directories for each stage
        self.invoice_storage_root = config.get("INVOICE_STORAGE_ROOT", "/data/invoices")
        self.pending_dir = os.path.join(self.invoice_storage_root, "pending")
        self.processed_dir = os.path.join(self.invoice_storage_root, "processed")
        self.rejected_dir = os.path.join(self.invoice_storage_root, "rejected")

        # Create all directories
        for d in [self.invoice_storage_root, self.pending_dir, self.processed_dir, self.rejected_dir]:
            os.makedirs(d, exist_ok=True)

        # OCR configuration (CPU-optimized defaults)
        self.ocr_dpi = config.get("OCR_DPI", 150)
        self.ocr_max_pages = config.get("OCR_MAX_PAGES", 5)
        self.ocr_max_file_mb = config.get("OCR_MAX_FILE_MB", 10)
        self.ocr_timeout = config.get("OCR_TIMEOUT", 120)

        self.capabilities = [
            "process_invoice",
        ]
        self.restrictions = [
            "privacy_scope_aware",
            "no_cloud_fallback_for_private",
        ]
        self.logger = logger.bind(agent="invoice_processing")

    async def start(self) -> None:
        """Initialize the agent."""
        self.logger.info("invoice_processing_agent_started")

    async def stop(self) -> None:
        """Close the router connections."""
        await self.router.aclose()
        self.logger.info("invoice_processing_agent_stopped")

    def _get_supplier_folder(self, tax_id: str) -> str:
        """Get sanitized supplier folder name from tax_id."""
        return tax_id.replace("/", "_").replace("\\", "_")

    def _get_pending_path(self, tax_id: str, filename: str) -> str:
        """Get the pending storage path for a supplier's invoice."""
        supplier_folder = self._get_supplier_folder(tax_id)
        supplier_path = os.path.join(self.pending_dir, supplier_folder)
        os.makedirs(supplier_path, exist_ok=True)
        # Avoid overwriting: add hash if needed
        file_hash = hashlib.sha256(filename.encode()).hexdigest()[:8]
        base, ext = os.path.splitext(filename)
        stored_filename = f"{base}_{file_hash}{ext}" if not base.endswith(file_hash) else filename
        return os.path.join(supplier_path, stored_filename)

    def _get_processed_path(self, tax_id: str, filename: str) -> str:
        """Get the processed storage path for a supplier's invoice."""
        supplier_folder = self._get_supplier_folder(tax_id)
        supplier_path = os.path.join(self.processed_dir, supplier_folder)
        os.makedirs(supplier_path, exist_ok=True)
        base, ext = os.path.splitext(filename)
        return os.path.join(supplier_path, f"{base}{ext}")

    def _get_rejected_path(self, tax_id: str, filename: str) -> str:
        """Get the rejected storage path for a supplier's invoice."""
        supplier_folder = self._get_supplier_folder(tax_id)
        supplier_path = os.path.join(self.rejected_dir, supplier_folder)
        os.makedirs(supplier_path, exist_ok=True)
        base, ext = os.path.splitext(filename)
        return os.path.join(supplier_path, f"{base}{ext}")

    async def _store_file(self, file_content: bytes, filename: str, supplier_folder: str) -> str:
        """
        Store the original file content to the specified supplier folder.
        Used to save the invoice directly to pending storage before OCR processing.
        Returns the stored file path.
        """
        supplier_path = os.path.join(self.invoice_storage_root, supplier_folder)
        os.makedirs(supplier_path, exist_ok=True)
        # Avoid overwriting: add hash if needed
        file_hash = hashlib.sha256(file_content).hexdigest()[:8]
        base, ext = os.path.splitext(filename)
        stored_filename = f"{base}_{file_hash}{ext}" if not base.endswith(file_hash) else filename
        file_path = os.path.join(supplier_path, stored_filename)
        with open(file_path, "wb") as f:
            f.write(file_content)
        return file_path

    async def _extract_text_from_pdf(self, file_path: str) -> str:
        """Try to extract text layer; if fails, return empty string."""
        try:
            import fitz  # pymupdf

            doc = fitz.open(file_path)
            text = ""
            for page in doc:
                text += page.get_text()
            doc.close()
            return text.strip()
        except Exception as e:
            self.logger.warning("pdf_text_extraction_failed", error=str(e))
            return ""

    async def _render_pdf_pages_to_images(self, file_path: str) -> list[bytes]:
        """
        Render PDF pages to PNG images for OCR.
        Returns list of image bytes (one per page).
        Respects OCR limits: max pages, DPI, file size.
        """
        import fitz  # pymupdf

        images = []

        try:
            doc = fitz.open(file_path)

            # Check page limit
            page_count = min(len(doc), self.ocr_max_pages)
            if len(doc) > self.ocr_max_pages:
                self.logger.warning("pdf_exceeds_max_pages", total_pages=len(doc), max_pages=self.ocr_max_pages)

            # Check file size
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
            if file_size_mb > self.ocr_max_file_mb:
                self.logger.warning("pdf_exceeds_max_size", size_mb=file_size_mb, max_mb=self.ocr_max_file_mb)
                # We'll still process but log warning

            for page_num in range(page_count):
                page = doc[page_num]
                # Render at configured DPI
                mat = fitz.Matrix(self.ocr_dpi / 72.0, self.ocr_dpi / 72.0)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                img_bytes = pix.tobytes("png")
                images.append(img_bytes)

                # Log image dimensions for debugging
                self.logger.debug(
                    "pdf_page_rendered",
                    page=page_num + 1,
                    width=pix.width,
                    height=pix.height,
                    size_kb=len(img_bytes) / 1024,
                )

            doc.close()
            return images

        except Exception as e:
            self.logger.error("pdf_render_failed", error=str(e))
            return []

    async def _ocr_via_ollama(self, image_path_or_bytes: str | None = None, image_bytes: bytes | None = None) -> str:
        """
        Use Ollama vision model to extract text from image.
        Accepts either image_path (str) or image_bytes (bytes).
        """
        try:
            # If image_bytes provided directly, write to temp file
            if image_bytes is not None:
                import tempfile

                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                    tmp.write(image_bytes)
                    tmp_path = tmp.name
                image_path = tmp_path
            elif image_path_or_bytes is not None:
                image_path = image_path_or_bytes
            else:
                return ""

            result = await self.router.vision(
                privacy_scope="LOCAL_ONLY",
                image_path=image_path,
                prompt="Extract all text from this image. Return only the raw text, no extra commentary.",
            )

            # Clean up temp file if we created one
            if image_bytes is not None and image_path:
                try:
                    os.unlink(image_path)
                except OSError:
                    pass

            return str(result.get("text", "")).strip()
        except Exception as e:
            self.logger.error("ollama_ocr_failed", error=str(e))
            return ""

    async def _extract_structured_data(self, raw_text: str) -> dict[str, Any]:
        """Send raw text to Ollama (local) to produce structured JSON per InvoiceData schema."""
        prompt = f"""
Extract the supplier invoice information from the following text and return a JSON object matching this schema:
{{
  "supplier": {{ "name": "", "tax_id": "" }},
  "invoice": {{ "number": "", "date": "" }},
  "lines": [ {{ "description": "", "quantity": 0, "unit_price": 0.0, "total": 0.0 }}, ... ],
  "taxes": [ {{ "type": "", "rate": 0.0, "amount": 0.0 }}, ... ],
  "subtotal": 0.0,
  "tax_total": 0.0,
  "total": 0.0,
  "currency": "EUR"
}}
Text:
\"\"\"{raw_text}\"\"\"
Return ONLY the JSON, no extra text.
"""
        try:
            result = await self.router.generate(
                privacy_scope="LOCAL_ONLY",
                prompt=prompt,
                temperature=0.1,
                max_tokens=1024,
            )
            json_str = result.get("text", "").strip()
            # Try to find JSON substring
            import json

            # Find first { and last }
            start = json_str.find("{")
            end = json_str.rfind("}")
            if start != -1 and end != -1 and end > start:
                json_str = json_str[start : end + 1]
            data = json.loads(json_str)
            return dict(data)
        except Exception as e:
            self.logger.error("structured_extraction_failed", error=str(e))
            raise

    async def _validate_with_pydantic(self, data: dict[str, Any]) -> InvoiceData:
        """Validate extracted data against InvoiceData model."""
        return InvoiceData(**data)

    async def _deterministic_checks(self, invoice: InvoiceData) -> list[str]:
        """Perform deterministic validations; return list of error messages."""
        errors = []
        # Check line totals sum to subtotal
        line_sum = sum(line.total for line in invoice.lines)
        if abs(line_sum - invoice.subtotal) > 0.01:
            errors.append(f"Line totals sum {line_sum} does not match subtotal {invoice.subtotal}")
        # Check subtotal + taxes = total
        tax_sum = sum(t.get("amount", 0.0) for t in invoice.taxes)
        if abs((invoice.subtotal + tax_sum) - invoice.total) > 0.01:
            errors.append(f"Subtotal + taxes ({invoice.subtotal + tax_sum}) does not match total {invoice.total}")
        # Check currency
        if invoice.currency.upper() != "EUR":
            errors.append(f"Currency {invoice.currency} not supported (expected EUR)")
        # Check date format (simple)
        inv = invoice.invoice
        date_str = inv.get("date", "")
        # Expect YYYY-MM-DD or DD/MM/YYYY etc. We'll just check not empty.
        if not date_str:
            errors.append("Invoice date missing")
        return errors

    async def _lookup_supplier(self, tax_id: str) -> dict[str, Any] | None:
        """Call InvoiceIntegrationService to find supplier by tax_id."""
        try:
            from app.services.invoice_integration_service import InvoiceIntegrationService

            service = InvoiceIntegrationService()
            async with service as s:
                result = await s.get_supplier_by_tax_id(tax_id)
            return result if result is not None else None
        except Exception as e:
            self.logger.warning("dolibarr_supplier_lookup_failed", error=str(e))
            return None

    async def _check_duplicate(self, supplier_tax_id: str, invoice_number: str) -> bool:
        """Check if invoice already exists in Dolibarr."""
        try:
            from app.services.invoice_integration_service import InvoiceIntegrationService

            service = InvoiceIntegrationService()
            async with service as s:
                result: bool = await s.invoice_exists(supplier_tax_id, invoice_number)
                return result
        except Exception as e:
            self.logger.warning("duplicate_check_failed", error=str(e))
            # Fail closed: assume duplicate to avoid creating duplicate
            return True

    async def process_invoice(self, file_content: bytes, filename: str, uploaded_by: int = 0) -> dict[str, Any]:
        """
        Main entry point: process an invoice file.
        Returns a dict with success, extracted data, validation errors, and next steps.

        Flow:
        1. Store original file to pending storage (persists after approval)
        2. Create temp copy for OCR/extraction
        3. Extract text (PDF text layer or OCR)
        4. Extract structured data via Ollama
        5. Validate with Pydantic
        6. Deterministic checks
        7. Lookup supplier in Dolibarr
        8. Check duplicate
        9. CLEANUP temp file
        10. Return pending file path for approval
        """
        self.logger.info("processing_invoice", filename=filename, size=len(file_content))

        # Step 0: Check file size limit BEFORE storing
        file_size_mb = len(file_content) / (1024 * 1024)
        if file_size_mb > self.ocr_max_file_mb:
            self.logger.warning(
                "file_exceeds_max_size_rejected", filename=filename, size_mb=file_size_mb, max_mb=self.ocr_max_file_mb
            )
            return {
                "success": False,
                "error": f"File size ({file_size_mb:.1f} MB) exceeds maximum allowed ({self.ocr_max_file_mb} MB)",
                "file_size_mb": file_size_mb,
                "max_file_mb": self.ocr_max_file_mb,
            }

        # Step 0: Determine privacy scope (should be LOCAL_ONLY for invoices)
        privacy_scope = "LOCAL_ONLY"

        # Step 1: Store original file to pending storage FIRST (persists after approval)
        supplier_tax_id = None
        invoice_number = None
        pending_file_path = None

        # We need to extract supplier_tax_id from the invoice, but we don't have it yet.
        # So we'll store to a temporary pending location first, then move to supplier-specific folder after validation.
        # For now, store to a generic pending folder.
        import tempfile

        temp_file_path = None
        raw_text = ""

        try:
            # Create a temp file for OCR processing
            with tempfile.NamedTemporaryFile(suffix=os.path.splitext(filename)[1], delete=False) as tmp:
                tmp.write(file_content)
                temp_file_path = tmp.name

            # Step 2: Extract text with timeout
            mime_type, _ = mimetypes.guess_type(filename)
            if mime_type == "application/pdf" or filename.lower().endswith(".pdf"):
                # First try to extract text layer
                raw_text = await self._extract_text_from_pdf(temp_file_path)
                if not raw_text or len(raw_text.strip()) < 50:
                    # No text layer or very little text - likely scanned PDF
                    # Render pages to images and OCR each
                    self.logger.info("pdf_no_text_layer_rendering_for_ocr", file_path=temp_file_path)
                    page_images = await self._render_pdf_pages_to_images(temp_file_path)
                    if page_images:
                        ocr_texts = []
                        for i, img_bytes in enumerate(page_images):
                            self.logger.debug("ocr_page", page=i + 1, total=len(page_images))
                            # Apply timeout to OCR
                            try:
                                page_text = await asyncio.wait_for(
                                    self._ocr_via_ollama(image_bytes=img_bytes), timeout=self.ocr_timeout
                                )
                                if page_text:
                                    ocr_texts.append(f"--- Page {i + 1} ---\n{page_text}")
                            except TimeoutError:
                                self.logger.warning("ocr_page_timeout", page=i + 1, timeout=self.ocr_timeout)
                                continue
                        raw_text = "\n\n".join(ocr_texts)
            else:
                # Assume image - apply timeout
                try:
                    raw_text = await asyncio.wait_for(self._ocr_via_ollama(temp_file_path), timeout=self.ocr_timeout)
                except TimeoutError:
                    self.logger.warning("ocr_timeout", filename=filename, timeout=self.ocr_timeout)
                    raw_text = ""

            if not raw_text:
                return {"success": False, "error": "Failed to extract text from file"}

            # Step 3: Extract structured data via Ollama
            try:
                extracted = await self._extract_structured_data(raw_text)
            except Exception:
                return {"success": False, "error": "structured_extraction_failed", "requires_review": True}

            # Step 4: Validate with Pydantic
            try:
                invoice = await self._validate_with_pydantic(extracted)
            except Exception:
                return {"success": False, "error": "pydantic_validation_failed", "requires_review": True}

            # Step 5: Deterministic checks
            check_errors = await self._deterministic_checks(invoice)
            if check_errors:
                return {
                    "success": False,
                    "error": "deterministic_checks_failed",
                    "details": check_errors,
                    "requires_review": True,
                }

            # Step 6: Lookup supplier in Dolibarr
            supplier_tax_id = invoice.supplier.tax_id
            supplier_info = await self._lookup_supplier(supplier_tax_id)
            if not supplier_info:
                return {
                    "success": False,
                    "error": "supplier_not_found",
                    "tax_id": supplier_tax_id,
                    "requires_review": True,
                }

            # Step 7: Check duplicate
            invoice_number = invoice.invoice.get("number", "")
            is_dup = await self._check_duplicate(supplier_tax_id, invoice_number)
            if is_dup:
                return {
                    "success": False,
                    "error": "duplicate_invoice_found",
                    "invoice_number": invoice_number,
                    "requires_review": True,
                }

            # Step 8: Store original file to pending storage using supplier-specific folder
            # Now we have supplier_tax_id, store the original file to pending
            supplier_folder = os.path.join("pending", supplier_tax_id.replace("/", "_").replace("\\", "_"))
            pending_file_path = await self._store_file(
                file_content=file_content,
                filename=filename,
                supplier_folder=supplier_folder,
            )
            self.logger.info(
                "invoice_stored_to_pending", pending_path=pending_file_path, supplier_tax_id=supplier_tax_id
            )

        finally:
            # Step 9: Always cleanup temp file (after we've stored to pending)
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except Exception as e:
                    self.logger.warning("temp_file_cleanup_failed", path=temp_file_path, error=str(e))

        # Step 10: Return success with pending file path for approval
        final_path = self._get_processed_path(supplier_tax_id, filename)

        return {
            "success": True,
            "message": "Invoice processed successfully, awaiting approval",
            "privacy_scope": privacy_scope,
            "file_path": pending_file_path,
            "final_path": final_path,
            "supplier": supplier_info,
            "invoice": invoice.dict(),
            "requires_approval": True,
            # Provide a summary for Telegram
            "summary": {
                "supplier_name": invoice.supplier.name,
                "supplier_tax_id": invoice.supplier.tax_id,
                "invoice_number": invoice.invoice.get("number"),
                "invoice_date": invoice.invoice.get("date"),
                "subtotal": invoice.subtotal,
                "tax_total": invoice.tax_total,
                "total": invoice.total,
                "currency": invoice.currency,
                "line_count": len(invoice.lines),
            },
        }

    async def approve_invoice(
        self, pending_file_path: str, final_path: str, invoice_data: dict[str, Any], uploaded_by: int = 0
    ) -> dict[str, Any]:
        """
        Call after human approval: create invoice in Dolibarr via integration
        service, then move file from pending to processed.
        Order: Dolibarr FIRST, then file move.
        """
        # Verify pending file exists
        if not os.path.exists(pending_file_path):
            self.logger.error("pending_file_not_found", path=pending_file_path)
            return {"success": False, "error": "pending_file_not_found", "requires_review": True}

        # Step 1: FIRST create invoice in Dolibarr
        try:
            from app.services.invoice_integration_service import InvoiceIntegrationService

            service = InvoiceIntegrationService()
            async with service as s:
                result = await s.create_supplier_invoice(
                    supplier_tax_id=invoice_data["supplier"]["tax_id"],
                    invoice_number=invoice_data["invoice"]["number"],
                    invoice_date=invoice_data["invoice"]["date"],
                    lines=invoice_data["lines"],
                    taxes=invoice_data["taxes"],
                    currency=invoice_data.get("currency", "EUR"),
                    attached_file=pending_file_path,  # Use pending file for attachment
                )
            dolibarr_invoice_id = result.get("id")
            self.logger.info("dolibarr_invoice_created", invoice_id=dolibarr_invoice_id)
        except Exception as e:
            self.logger.error("dolibarr_invoice_create_failed", error=str(e))
            # Keep file in pending - don't move it
            return {"success": False, "error": "dolibarr_invoice_create_failed", "requires_review": True}

        # Step 2: Only after Dolibarr succeeds, move file from pending to processed
        try:
            os.makedirs(os.path.dirname(final_path), exist_ok=True)
            shutil.move(pending_file_path, final_path)
            self.logger.info("invoice_moved_pending_to_processed", pending=pending_file_path, final=final_path)
        except Exception as e:
            self.logger.error("file_move_failed", error=str(e))
            # File move failed but Dolibarr succeeded - log error but return success for Dolibarr
            return {
                "success": False,
                "error": "file_move_failed_after_dolibarr_success",
                "dolibarr_invoice_id": dolibarr_invoice_id,
                "requires_review": True,
            }

        return {"success": True, "message": "Invoice created in Dolibarr", "dolibarr_invoice_id": dolibarr_invoice_id}

    async def reject_invoice(self, pending_file_path: str, reason: str) -> dict[str, Any]:
        """
        Call after human rejection: move file from pending to rejected.
        """
        if not os.path.exists(pending_file_path):
            self.logger.error("pending_file_not_found", path=pending_file_path)
            return {"success": False, "error": "pending_file_not_found", "requires_review": True}

        try:
            # Extract tax_id from path to determine rejected location
            # Path format: /data/invoices/pending/{tax_id}/{filename}
            rel_path = os.path.relpath(pending_file_path, self.pending_dir)
            tax_id = rel_path.split(os.sep)[0]
            filename = os.path.basename(pending_file_path)
            rejected_path = self._get_rejected_path(tax_id, filename)

            os.makedirs(os.path.dirname(rejected_path), exist_ok=True)
            shutil.move(pending_file_path, rejected_path)
            self.logger.info(
                "invoice_moved_pending_to_rejected", pending=pending_file_path, rejected=rejected_path, reason=reason
            )
            return {
                "success": True,
                "message": "Invoice rejected and archived",
                "rejected_path": rejected_path,
            }
        except Exception as e:
            self.logger.error("file_reject_failed", error=str(e))
            return {"success": False, "error": "file_reject_failed", "requires_review": True}


def create_invoice_processing_agent(config: dict[str, Any]) -> InvoiceProcessingAgent:
    return InvoiceProcessingAgent(config)
