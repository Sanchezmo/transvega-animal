"""Invoice Processing Agent
Handles extraction, validation, and registration of supplier invoices.
"""

import asyncio
import hashlib
import mimetypes
import os
import shutil
import time
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
    from pydantic import BaseModel, Field, field_validator, model_validator
except ImportError:
    # If pydantic not installed, we'll skip validation for now; but we assume it's present.
    pass


class InvoiceLine(BaseModel):
    description: str
    quantity: float = 1.0
    unit_price: float
    net_amount: float | None = None  # Net amount (quantity * unit_price - discount)
    tax_amount: float | None = None  # Tax amount for this line
    gross_amount: float | None = None  # Gross amount (net + tax)
    total: float  # Legacy: net amount if vat_rate not provided, otherwise gross
    vat_rate: float | None = None
    discount: float | None = None  # Discount amount or percentage

    @model_validator(mode="after")
    def compute_amounts(self) -> "InvoiceLine":
        """Compute net/tax/gross amounts with flexible validation for backward compatibility."""
        # If net_amount is not provided, compute from quantity * unit_price - discount
        if self.net_amount is None:
            discount_amount = 0.0
            if self.discount is not None:
                if self.discount <= 1.0 and self.discount > 0:
                    # Percentage discount
                    discount_amount = self.quantity * self.unit_price * self.discount
                else:
                    # Absolute discount amount
                    discount_amount = self.discount
            else:
                discount_amount = 0.0

            self.net_amount = round(self.quantity * self.unit_price - discount_amount, 2)

        # If tax_amount is not provided but vat_rate is available, compute tax
        if self.tax_amount is None and self.vat_rate is not None and self.vat_rate > 0:
            self.tax_amount = round(self.net_amount * self.vat_rate / 100, 2)

        # If gross_amount is not provided, compute from net + tax
        if self.gross_amount is None:
            tax_amt = self.tax_amount if self.tax_amount is not None else 0.0
            self.gross_amount = round(self.net_amount + tax_amt, 2)

        # Determine what "total" represents based on available fields
        # If total matches net_amount (legacy format), use it as net
        # If total differs from net_amount, treat it as gross amount
        expected_net = self.net_amount
        if abs(self.total - expected_net) <= 0.01:
            # total is net amount (legacy format)
            self.gross_amount = self.net_amount + (self.tax_amount or 0)
        else:
            # total is gross amount
            self.gross_amount = self.total
            # Recompute net if we have vat_rate
            if self.vat_rate is not None and self.vat_rate > 0 and self.net_amount is None:
                self.net_amount = round(self.total / (1 + self.vat_rate / 100), 2)
                self.tax_amount = round(self.total - self.net_amount, 2)

        return self

    @field_validator("total")
    @classmethod
    def total_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("Total must be non-negative")
        return v

    @field_validator("net_amount", "tax_amount", "gross_amount")
    @classmethod
    def amounts_non_negative(cls, v: float | None) -> float | None:
        if v is not None and v < 0:
            raise ValueError("Amounts must be non-negative")
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

    @model_validator(mode="after")
    def validate_totals(self) -> "InvoiceData":
        # Check line totals sum to subtotal (use net_amount if available, else total as net)
        line_sum = sum(line.net_amount if line.net_amount is not None else line.total for line in self.lines)
        if abs(line_sum - self.subtotal) > 0.01:
            raise ValueError(f"Line totals sum {line_sum} does not match subtotal {self.subtotal}")

        # Check subtotal + taxes = total
        tax_sum = sum(t.get("amount", 0.0) for t in self.taxes)
        if abs((self.subtotal + tax_sum) - self.total) > 0.01:
            raise ValueError(f"Subtotal + taxes ({self.subtotal + tax_sum}) does not match total {self.total}")

        # Check currency
        if self.currency.upper() != "EUR":
            raise ValueError(f"Currency {self.currency} not supported (expected EUR)")

        return self


# JSON Schema for native structured output
INVOICE_JSON_SCHEMA = InvoiceData.model_json_schema()


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

        # Initialize ModelRouter with single multimodal model
        ollama_endpoint = config.get("OLLAMA_ENDPOINT", "http://ollama:11434")
        ollama_model = config.get("OLLAMA_MODEL", "transvega-local")
        nvidia_api_key = config.get("NVIDIA_API_KEY", "")
        nvidia_base_url = config.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
        # Invoice-specific timeout (default 600s = 10 minutes)
        ollama_invoice_timeout = config.get("OLLAMA_INVOICE_TIMEOUT", 600.0)
        self.router = create_model_router(
            ollama_endpoint=ollama_endpoint,
            ollama_model=ollama_model,
            ollama_vision_model=ollama_model,  # Same model for vision (multimodal)
            nvidia_api_key=nvidia_api_key,
            nvidia_base_url=nvidia_base_url,
            ollama_default_timeout=ollama_invoice_timeout,
        )
        self.ollama_model = ollama_model
        self.ollama_endpoint = ollama_endpoint
        self.ollama_invoice_timeout = ollama_invoice_timeout

        # Storage roots - separate directories for each stage
        self.invoice_storage_root = config.get("INVOICE_STORAGE_ROOT", "/data/invoices")
        # If running as non-root, use a temp directory
        if not os.access(os.path.dirname(self.invoice_storage_root), os.W_OK):
            import tempfile

            self.invoice_storage_root = os.path.join(tempfile.gettempdir(), "transvega_invoices")

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

    async def _check_ollama_models_ready(self) -> bool:
        """Check if required Ollama model is available."""
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{self.ollama_endpoint}/api/tags")
                if resp.status_code != 200:
                    return False
                data = resp.json()
                models = {m.get("name") for m in data.get("models", [])}
                required = {self.ollama_model}
                return required.issubset(models)
        except Exception as e:
            self.logger.warning("ollama_model_check_failed", error=str(e))
            return False

    async def _wait_for_models_ready(self, max_wait: int = 300) -> bool:
        """Wait for Ollama models to be ready, with timeout."""
        import asyncio

        for _ in range(max_wait):
            if await self._check_ollama_models_ready():
                return True
            await asyncio.sleep(1)
        return False

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
                request_timeout=self.ollama_invoice_timeout,
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
        """Send raw text to Ollama (local) to produce structured JSON per InvoiceData schema.

        Uses native structured output with JSON Schema, think=false, and generous token budget.
        """
        prompt = f"""
Extract the supplier invoice information from the following text and return a JSON object matching the schema.
Text:
\"\"\"{raw_text}\"\"\"
Return ONLY the JSON, no extra text.
"""
        start_time = time.perf_counter()
        try:
            # Use native structured output with JSON Schema
            # Ollama parameters: format (JSON Schema), think=false, num_predict (max tokens)
            result = await self.router.generate(
                privacy_scope="LOCAL_ONLY",
                prompt=prompt,
                temperature=0.1,
                num_predict=2048,
                think=False,
                format=INVOICE_JSON_SCHEMA,
                request_timeout=self.ollama_invoice_timeout,
            )
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            json_str = result.get("text", "").strip()
            raw_response = result.get("raw", {})

            # Extract Ollama metrics if available
            total_duration = raw_response.get("total_duration")
            load_duration = raw_response.get("load_duration")
            prompt_eval_count = raw_response.get("prompt_eval_count")
            prompt_eval_duration = raw_response.get("prompt_eval_duration")
            eval_count = raw_response.get("eval_count")
            eval_duration = raw_response.get("eval_duration")

            # Log diagnostic information (safe - no PII)
            self.logger.info(
                "structured_extraction_completed",
                elapsed_ms=elapsed_ms,
                response_length=len(json_str),
                model=self.ollama_model,
                input_type="text",
                processing_strategy="native_structured_output",
                native_text_chars=len(raw_text),
                requested_max_tokens=2048,
                actual_generated_tokens=eval_count,
                total_duration_ns=total_duration,
                load_duration_ns=load_duration,
                prompt_eval_count=prompt_eval_count,
                prompt_eval_duration_ns=prompt_eval_duration,
                eval_duration_ns=eval_duration,
                # Calculate tokens per second if available
                prompt_tokens_per_second=(
                    (prompt_eval_count / (prompt_eval_duration / 1e9))
                    if prompt_eval_duration and prompt_eval_duration > 0 else None
                ),
                generation_tokens_per_second=(
                    (eval_count / (eval_duration / 1e9))
                    if eval_duration and eval_duration > 0 else None
                ),
            )

            # Parse JSON (Ollama should return valid JSON with format=JSON Schema)
            import json
            data = json.loads(json_str)
            return dict(data)

        except TimeoutError as e:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            self.logger.error(
                "structured_extraction_timeout",
                exception_type="asyncio.TimeoutError",
                safe_exception_message=str(e),
                elapsed_ms=elapsed_ms,
                model=self.ollama_model,
                input_type="text",
                processing_strategy="native_structured_output",
                native_text_chars=len(raw_text),
                requested_max_tokens=2048,
            )
            raise

        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            # Log detailed diagnostic information
            self.logger.error(
                "structured_extraction_failed",
                exception_type=type(e).__name__,
                safe_exception_message=str(e),
                elapsed_ms=elapsed_ms,
                model=self.ollama_model,
                input_type="text",
                processing_strategy="native_structured_output",
                native_text_chars=len(raw_text),
                requested_max_tokens=2048,
            )
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

    def _normalize_tax_data(self, extracted: dict[str, Any]) -> dict[str, Any]:
        """
        Normalize tax data before validation.

        Ensures that:
        1. If tax items have rate but no amount, compute amount from line-level data
        2. If line-level vat_rate exists but taxes array is empty/missing, create tax entries from lines
        3. Ensure tax items have 'amount' and 'rate' fields for validation
        4. Validate tax_total consistency with computed tax amounts

        This runs BEFORE Pydantic validation to normalize the data structure.
        """
        from collections import defaultdict

        # --- Step 1: Compute tax amounts from line items (group by vat_rate) ---
        tax_by_rate: dict[float, float] = defaultdict(float)  # rate -> total tax amount
        base_by_rate: dict[float, float] = defaultdict(float)  # rate -> total tax base

        if "lines" in extracted:
            for line in extracted.get("lines", []):
                # Compute net amount for this line (quantity * unit_price - discount)
                qty = line.get("quantity", 1.0)
                unit_price = line.get("unit_price", 0.0)
                discount = line.get("discount", 0.0)
                vat_rate = line.get("vat_rate")

                net_amount = qty * unit_price
                if discount is not None:
                    if discount <= 1.0 and discount > 0:
                        # Percentage discount
                        net_amount -= net_amount * discount
                    else:
                        # Absolute discount amount
                        net_amount -= discount

                if vat_rate is not None and vat_rate > 0:
                    tax_amount = round(net_amount * vat_rate / 100, 2)
                    tax_by_rate[vat_rate] += tax_amount
                    base_by_rate[vat_rate] += net_amount

        # --- Step 2: Normalize invoice-level taxes array ---
        taxes_list: list[dict[str, Any]] = extracted.get("taxes") or []
        has_taxes_array = len(taxes_list) > 0

        if has_taxes_array:
            normalized_taxes = []
            for tax in taxes_list:
                if not isinstance(tax, dict):
                    continue

                rate = tax.get("rate") or tax.get("tax_rate") or tax.get("vat_rate")
                if rate is not None:
                    rate = float(rate)

                # If tax has rate but no amount, try to compute from line data
                if rate is not None and rate > 0 and ("amount" not in tax or tax["amount"] is None):
                    # Prefer base from tax item, then from aggregated line data
                    base = tax.get("base") or tax.get("base_amount") or tax.get("net_amount")
                    if base is None and rate in base_by_rate:
                        base = base_by_rate[rate]

                    if base is not None:
                        tax["amount"] = round(base * rate / 100, 2)
                    elif rate in tax_by_rate:
                        # Fallback: use aggregated tax amount from lines
                        tax["amount"] = tax_by_rate[rate]
                    elif extracted.get("tax_total", 0) > 0 and len(taxes_list) == 1:
                        # Single tax item and we have tax_total: use it
                        tax["amount"] = extracted["tax_total"]

                # Ensure amount field exists (default to 0.0 if still missing)
                if "amount" not in tax or tax["amount"] is None:
                    tax["amount"] = tax.get("tax_amount", tax.get("cuota", 0.0))

                # Ensure rate field exists
                if "rate" not in tax:
                    tax["rate"] = rate if rate is not None else 0.0

                normalized_taxes.append(tax)

            extracted["taxes"] = normalized_taxes

        # --- Step 3: If taxes array is empty/missing but we have line-level tax data, create from lines ---
        elif "lines" in extracted and tax_by_rate:
            # Build taxes array from line data
            extracted["taxes"] = [
                {"rate": rate, "base": base_by_rate[rate], "amount": amount}
                for rate, amount in tax_by_rate.items()
            ]

        # --- Step 4: If still no taxes array but tax_total exists, create from tax_total ---
        elif extracted.get("tax_total", 0) > 0:
            # Try to infer rate from lines if possible
            inferred_rate = 0.0
            if "lines" in extracted:
                rates = {line.get("vat_rate") for line in extracted["lines"] if line.get("vat_rate")}
                if len(rates) == 1:
                    inferred_rate = float(rates.pop())

            extracted["taxes"] = [{"rate": inferred_rate, "amount": extracted["tax_total"]}]

        # --- Step 5: Ensure tax_total field is consistent with taxes array ---
        if "taxes" in extracted and isinstance(extracted["taxes"], list):
            computed_tax_total = sum(t.get("amount", 0.0) for t in extracted["taxes"])
            # Only update tax_total if it was missing or zero, or if it matches closely
            tax_total_missing = "tax_total" not in extracted
            tax_total_zero = extracted.get("tax_total", 0) == 0
            tax_total_matches = abs(extracted.get("tax_total", 0) - computed_tax_total) < 0.02
            if tax_total_missing or tax_total_zero or tax_total_matches:
                extracted["tax_total"] = round(computed_tax_total, 2)

        return extracted

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
        1. Check Ollama models are ready
        2. Store original file to pending storage (persists after approval)
        3. Create temp copy for OCR/extraction
        4. Extract text (PDF text layer or OCR)
        5. Extract structured data via Ollama
        6. Validate with Pydantic
        7. Deterministic checks
        8. Lookup supplier in Dolibarr
        9. Check duplicate
        10. CLEANUP temp file
        11. Return pending file path for approval
        """
        self.logger.info("processing_invoice", filename=filename, size=len(file_content))

        # Check Ollama models are ready before processing
        if not await self._check_ollama_models_ready():
            self.logger.warning(
                "ollama_model_not_ready_waiting", required_model=self.ollama_model
            )
            if not await self._wait_for_models_ready(max_wait=120):
                return {
                    "success": False,
                    "error": "ollama_model_not_ready",
                    "message": "Ollama model not available after waiting",
                    "required_model": self.ollama_model,
                    "requires_review": True,
                }

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
        has_native_text = False
        native_text_chars = 0
        inference_count = 0

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
                if raw_text and len(raw_text.strip()) >= 50:
                    has_native_text = True
                    native_text_chars = len(raw_text)
                    self.logger.info("pdf_native_text_extracted", chars=native_text_chars)
                else:
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
                                    inference_count += 1
                            except TimeoutError:
                                self.logger.warning("ocr_page_timeout", page=i + 1, timeout=self.ocr_timeout)
                                continue
                        raw_text = "\n\n".join(ocr_texts)
            else:
                # Assume image - apply timeout
                try:
                    raw_text = await asyncio.wait_for(self._ocr_via_ollama(temp_file_path), timeout=self.ocr_timeout)
                    inference_count += 1
                except TimeoutError:
                    self.logger.warning("ocr_timeout", filename=filename, timeout=self.ocr_timeout)
                    raw_text = ""

            if not raw_text:
                return {"success": False, "error": "Failed to extract text from file"}

            # Step 3: Extract structured data via Ollama
            try:
                extracted = await self._extract_structured_data(raw_text)
                inference_count += 1
            except TimeoutError:
                return {
                    "success": False,
                    "error": "invoice_processing_timeout",
                    "message": "El procesamiento de la factura ha superado el tiempo máximo permitido.",
                    "requires_review": False,  # This is a timeout, not a validation issue
                }
            except Exception:
                return {"success": False, "error": "structured_extraction_failed", "requires_review": True}

            # Step 3.5: Normalize tax data before validation
            extracted = self._normalize_tax_data(extracted)

            # Step 4: Validate with Pydantic
            try:
                invoice = await self._validate_with_pydantic(extracted)
            except Exception as e:
                # Validation errors should be NEEDS_REVIEW, not FAILED
                self.logger.warning("pydantic_validation_failed", error=str(e))
                return {
                    "success": False,
                    "error": "pydantic_validation_failed",
                    "message": "La factura se ha interpretado pero algunos datos no son válidos.",
                    "requires_review": True,
                    "needs_review": True,
                }

            # Step 5: Deterministic checks
            check_errors = await self._deterministic_checks(invoice)
            if check_errors:
                return {
                    "success": False,
                    "error": "deterministic_checks_failed",
                    "details": check_errors,
                    "message": "La factura se ha interpretado pero las validaciones contables no cuadran.",
                    "requires_review": True,
                    "needs_review": True,
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
            # Diagnostics for monitoring
            "diagnostics": {
                "has_native_text": has_native_text,
                "native_text_chars": native_text_chars,
                "inference_count": inference_count,
                "input_type": "pdf" if filename.lower().endswith(".pdf") else "image",
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
            from app.services.invoice_integration_service import DocumentAttachmentError, InvoiceIntegrationService

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
        except DocumentAttachmentError as e:
            self.logger.error("document_attachment_failed", invoice_id=e.invoice_id, error=str(e))
            # Attachment failed but invoice exists in Dolibarr - return invoice_id for cleanup
            return {
                "success": False,
                "error": "document_attachment_failed",
                "dolibarr_invoice_id": e.invoice_id,
                "requires_cleanup": True,
            }
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
