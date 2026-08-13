"""Invoice Processing Agent
Handles extraction, validation, and registration of supplier invoices.
"""
import structlog
import os
import hashlib
from typing import Dict, Any, Optional, List
from datetime import datetime
import mimetypes

# We'll import the ModelRouter and privacy router later
from app.core.model_router import ModelRouter
# Assuming privacy router exists; if not, we'll define a simple stub
try:
    from app.core.privacy_router import privacy_router, PrivacyScope
except ImportError:
    # Fallback stub
    from enum import Enum
    class PrivacyScope(Enum):
        LOCAL_ONLY = "local_only"
        CLOUD_ALLOWED = "cloud_allowed"
    async def privacy_router(content: str, filename: str = "") -> PrivacyScope:
        # Simple stub: treat everything as LOCAL_ONLY for safety
        return PrivacyScope.LOCAL_ONLY
    privacy_router = privacy_router  # type: ignore

logger = structlog.get_logger()

# Pydantic model for invoice (simple)
try:
    from pydantic import BaseModel, Field, validator
    from typing import Literal
except ImportError:
    # If pydantic not installed, we'll skip validation for now; but we assume it's present.
    pass

class InvoiceLine(BaseModel):
    description: str
    quantity: float = 1.0
    unit_price: float
    total: float

    @validator('total')
    def total_matches(cls, v, values):
        qty = values.get('quantity')
        price = values.get('unit_price')
        if qty is not None and price is not None:
            expected = qty * price
            if abs(v - expected) > 0.01:
                raise ValueError(f'Total {v} does not match quantity * unit_price ({expected})')
        return v

class SupplierInfo(BaseModel):
    name: str
    tax_id: str  # CIF/NIF

class InvoiceData(BaseModel):
    supplier: SupplierInfo
    invoice: dict = Field(..., description="Invoice metadata")
    lines: List[InvoiceLine]
    taxes: List[Dict[str, Any]] = []
    subtotal: float
    tax_total: float
    total: float
    currency: str = "EUR"

    @validator('total')
    def total_matches_sum(cls, v, values):
        subtotal = values.get('subtotal', 0.0)
        tax_total = values.get('tax_total', 0.0)
        if abs(v - (subtotal + tax_total)) > 0.01:
            raise ValueError(f'Total {v} does not match subtotal + tax_total ({subtotal + tax_total})')
        return v

class InvoiceProcessingAgent:
    """
    Agent that processes supplier invoices (PDF or image) through:
    1. Privacy check (must be LOCAL_ONLY)
    2. Text extraction (direct PDF text or OCR via Ollama vision)
    3. Structured extraction via Ollama (local LLM) to JSON
    4. Validation with Pydantic
    5. Deterministic checks (sums, VAT, duplicate)
    6. Lookup supplier in Dolibarr via DolibarrIntegrationService
    7. Return result for human approval
    8. On approval, create invoice in Dolibarr
    """

    def __init__(self, config: Dict):
        self.config = config
        self.agent_id = "invoice_processing"
        self.agent_name = "Invoice Processing Agent"

        # Initialize ModelRouter
        ollama_endpoint = config.get("OLLAMA_ENDPOINT", "http://ollama:11434")
        ollama_model = config.get("OLLAMA_MODEL", "qwen4b:latest")
        nvidia_api_key = config.get("NVIDIA_API_KEY", "")
        nvidia_base_url = config.get("NVIDIA_BASE_URL", "https://api.nvidia.com/v1")
        from app.core.model_router import create_ollama_provider, create_nvidia_provider, ModelRouter
        ollama_provider = create_ollama_provider(ollama_endpoint, ollama_model)
        nvidia_provider = create_nvidia_provider(nvidia_api_key, nvidia_base_url)
        self.router = ModelRouter(ollama=ollama_provider, nvidia=nvidia_provider)

        # Storage roots
        self.invoice_storage_root = config.get("INVOICE_STORAGE_ROOT", "/data/invoices")
        os.makedirs(self.invoice_storage_root, exist_ok=True)

        self.capabilities = [
            "process_invoice",
        ]
        self.restrictions = [
            "privacy_scope_aware",
            "no_cloud_fallback_for_private",
        ]

        logger = logger.bind(component=self.agent_id)

    async def _store_file(self, file_content: bytes, filename: str, supplier_folder: str) -> str:
        """Store file under invoice_storage_root/supplier_folder/ and return path."""
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
            logger.warning("pdf_text_extraction_failed", error=str(e))
            return ""

    async def _ocr_via_ollama(self, image_path: str) -> str:
        """Use Ollama vision model to extract text from image."""
        try:
            result = await self.router.vision(
                privacy_scope="LOCAL_ONLY",
                image_path=image_path,
                prompt="Extract all text from this image. Return only the raw text, no extra commentary."
            )
            return result.get("text", "").strip()
        except Exception as e:
            logger.error("ollama_ocr_failed", error=str(e))
            return ""

    async def _extract_structured_data(self, raw_text: str) -> Dict[str, Any]:
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
            start = json_str.find('{')
            end = json_str.rfind('}')
            if start != -1 and end != -1 and end > start:
                json_str = json_str[start:end+1]
            data = json.loads(json_str)
            return data
        except Exception as e:
            logger.error("structured_extraction_failed", error=str(e), raw_text=raw_text[:200])
            raise

    async def _validate_with_pydantic(self, data: Dict[str, Any]) -> InvoiceData:
        """Validate extracted data against InvoiceData model."""
        return InvoiceData(**data)

    async def _deterministic_checks(self, invoice: InvoiceData) -> List[str]:
        """Perform deterministic validations; return list of error messages."""
        errors = []
        # Check line totals sum to subtotal
        line_sum = sum(line.total for line in invoice.lines)
        if abs(line_sum - invoice.subtotal) > 0.01:
            errors.append(f"Line totals sum {line_sum} does not match subtotal {invoice.subtotal}")
        # Check subtotal + taxes = total
        tax_sum = sum(t.get('amount', 0.0) for t in invoice.taxes)
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

    async def _lookup_supplier(self, tax_id: str) -> Optional[Dict[str, Any]]:
        """Call DolibarrIntegrationService to find supplier by tax_id."""
        # Placeholder: we assume a service exists; we'll mock for now.
        # In real code, we would import DolibarrIntegrationService and call its method.
        try:
            from app.services.integration_service import DolibarrIntegrationService
            service = DolibarrIntegrationService()
            # Example method: get_supplier_by_tax_id
            result = await service.get_supplier_by_tax_id(tax_id)
            return result
        except Exception as e:
            logger.warning("dolibarr_supplier_lookup_failed", error=str(e))
            return None

    async def _check_duplicate(self, supplier_tax_id: str, invoice_number: str) -> bool:
        """Check if invoice already exists in Dolibarr."""
        try:
            from app.services.integration_service import DolibarrIntegrationService
            service = DolibarrIntegrationService()
            return await service.invoice_exists(supplier_tax_id, invoice_number)
        except Exception as e:
            logger.warning("duplicate_check_failed", error=str(e))
            # Fail closed: assume duplicate to avoid creating duplicate
            return True

    async def process_invoice(self, file_content: bytes, filename: str, uploaded_by: int = 0) -> Dict[str, Any]:
        """
        Main entry point: process an invoice file.
        Returns a dict with success, extracted data, validation errors, and next steps.
        """
        logger.info("processing_invoice", filename=filename, size=len(file_content))
        # Step 0: Determine privacy scope (should be LOCAL_ONLY for invoices)
        # We'll check content type and maybe filename.
        # For simplicity, we treat all uploads as LOCAL_ONLY.
        privacy_scope = "LOCAL_ONLY"
        # Step 1: Store file temporarily
        # We'll need a supplier folder; we don't know supplier yet, use pending.
        temp_folder = f"pending_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        try:
            file_path = await self._store_file(file_content, filename, temp_folder)
        except Exception as e:
            return {"success": False, "error": f"File storage failed: {e}"}

        # Step 2: Extract text
        raw_text = ""
        mime_type, _ = mimetypes.guess_type(filename)
        if mime_type == "application/pdf" or filename.lower().endswith('.pdf'):
            raw_text = await self._extract_text_from_pdf(file_path)
            if not raw_text:
                # No text layer, need OCR
                raw_text = await self._ocr_via_ollama(file_path)
        else:
            # Assume image
            raw_text = await self._ocr_via_ollama(file_path)

        if not raw_text:
            return {"success": False, "error": "Failed to extract text from file", "file_path": file_path}

        # Step 3: Extract structured data via Ollama
        try:
            extracted = await self._extract_structured_data(raw_text)
        except Exception as e:
            return {"success": False, "error": f"Structured extraction failed: {e}", "raw_text": raw_text[:500]}

        # Step 4: Validate with Pydantic
        try:
            invoice = await self._validate_with_pydantic(extracted)
        except Exception as e:
            return {"success": False, "error": f"Pydantic validation failed: {e}", "extracted": extracted}

        # Step 5: Deterministic checks
        check_errors = await self._deterministic_checks(invoice)
        if check_errors:
            return {"success": False, "error": "Deterministic checks failed", "details": check_errors, "invoice": invoice.dict()}

        # Step 6: Lookup supplier in Dolibarr
        supplier_tax_id = invoice.supplier.tax_id
        supplier_info = await self._lookup_supplier(supplier_tax_id)
        if not supplier_info:
            return {"success": False, "error": "Supplier not found in Dolibarr", "tax_id": supplier_tax_id, "invoice": invoice.dict()}

        # Step 7: Check duplicate
        invoice_number = invoice.invoice.get("number", "")
        is_dup = await self._check_duplicate(supplier_tax_id, invoice_number)
        if is_dup:
            return {"success": False, "error": "Duplicate invoice found", "supplier": supplier_info, "invoice_number": invoice_number, "invoice": invoice.dict()}

        # Step 8: Prepare for approval
        # We'll move file to final supplier folder after approval.
        supplier_folder = supplier_tax_id.replace("/", "_")
        final_path = os.path.join(self.invoice_storage_root, supplier_folder, os.path.basename(file_path))
        os.makedirs(os.path.dirname(final_path), exist_ok=True)
        # Note: we keep the file in temp for now; after approval we will move.

        return {
            "success": True,
            "message": "Invoice processed successfully, awaiting approval",
            "privacy_scope": privacy_scope,
            "file_path": file_path,
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
            }
        }

    async def approve_invoice(self, file_path: str, final_path: str, invoice_data: Dict[str, Any], uploaded_by: int = 0) -> Dict[str, Any]:
        """
        Call after human approval: move file, create invoice in Dolibarr via integration service.
        """
        try:
            # Move file
            os.rename(file_path, final_path)
        except Exception as e:
            logger.error("file_move_failed", error=str(e))
            return {"success": False, "error": f"Failed to move file: {e}"}

        # Create invoice in Dolibarr
        try:
            from app.services.integration_service import DolibarrIntegrationService
            service = DolibarrIntegrationService()
            result = await service.create_supplier_invoice(
                supplier_tax_id=invoice_data["supplier"]["tax_id"],
                invoice_number=invoice_data["invoice"]["number"],
                invoice_date=invoice_data["invoice"]["date"],
                lines=invoice_data["lines"],
                taxes=invoice_data["taxes"],
                currency=invoice_data.get("currency", "EUR"),
                # Optionally attach file reference
                attached_file=final_path
            )
            return {"success": True, "message": "Invoice created in Dolibarr", "dolibarr_invoice_id": result.get("id")}
        except Exception as e:
            logger.error("dolibarr_invoice_create_failed", error=str(e))
            # Optionally move file back? We'll leave it stored.
            return {"success": False, "error": f"Failed to create invoice in Dolibarr: {e}"}

    async def close(self):
        await self.router.aclose()


def create_invoice_processing_agent(config: Dict) -> InvoiceProcessingAgent:
    return InvoiceProcessingAgent(config)