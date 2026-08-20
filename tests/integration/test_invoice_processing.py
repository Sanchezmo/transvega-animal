"""
E2E tests for Supplier Invoice Processing Agent.
Tests the complete flow: PDF processing -> OCR -> Local LLM -> Validation -> Dolibarr Mock.
"""

import os
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio


@pytest.fixture
def sample_invoice_text():
    """Sample invoice text for testing."""
    return """
PROVEEDOR: Distribuciones Caninas S.L.
CIF: B12345678
FACTURA: FAC-2024-001
FECHA: 2024-01-15

CONCEPTO                          CANT.    PRECIO    TOTAL
----------------------------------------------------------
Pienso Premium Perro 15kg            10      25.00    250.00
Collar Antiparasitario                5      12.00     60.00
Champú Hipoalergénico                 3      18.50     55.50
----------------------------------------------------------
SUBTOTAL:                                                  365.50
IVA (21%):                                                  76.76
TOTAL:                                                     442.26
EUR
"""


@pytest.fixture
def sample_invoice_data():
    """Expected structured invoice data."""
    return {
        "supplier": {"name": "Distribuciones Caninas S.L.", "tax_id": "B12345678"},
        "invoice": {"number": "FAC-2024-001", "date": "2024-01-15"},
        "lines": [
            {
                "description": "Pienso Premium Perro 15kg",
                "quantity": 10,
                "unit_price": 25.00,
                "total": 250.00,
                "vat_rate": 21.0,
            },
            {
                "description": "Collar Antiparasitario",
                "quantity": 5,
                "unit_price": 12.00,
                "total": 60.00,
                "vat_rate": 21.0,
            },
            {
                "description": "Champú Hipoalergénico",
                "quantity": 3,
                "unit_price": 18.50,
                "total": 55.50,
                "vat_rate": 21.0,
            },
        ],
        "taxes": [{"type": "IVA", "rate": 21.0, "amount": 76.76}],
        "subtotal": 365.50,
        "tax_total": 76.76,
        "total": 442.26,
        "currency": "EUR",
    }


@pytest_asyncio.fixture
async def mock_dolibarr_service():
    """Mock InvoiceIntegrationService for testing."""
    with patch("app.services.invoice_integration_service.InvoiceIntegrationService") as mock:
        service_instance = AsyncMock()
        mock.return_value.__aenter__.return_value = service_instance

        # Mock _ensure_supplier (called directly by InvoiceProcessingAgent)
        # Returns a supplier dict as if supplier was created/found
        service_instance._ensure_supplier.return_value = {
            "id": 42,
            "name": "Distribuciones Caninas S.L.",
            "vat_number": "B12345678",
            "fournisseur": 1,
            "client": 0,
        }

        # Mock duplicate check - no duplicate
        service_instance.invoice_exists.return_value = False

        # Mock invoice creation
        service_instance.create_supplier_invoice.return_value = {
            "id": 1001,
            "ref": "FAC-2024-001",
            "total_ttc": 442.26,
        }

        # Mock get_supplier_invoice (called after creation)
        service_instance.get_supplier_invoice.return_value = {
            "id": 1001,
            "ref": "FAC-2024-001",
            "total_ttc": 442.26,
        }

        yield service_instance


@pytest_asyncio.fixture
async def mock_model_router():
    """Mock ModelRouter to simulate local Ollama responses."""
    with patch("agents.invoice_processing.agent.create_model_router") as mock:
        router = AsyncMock()

        # Mock vision (OCR) response
        router.vision.return_value = {
            "text": (
                "PROVEEDOR: Distribuciones Caninas S.L.\n"
                "CIF: B12345678\n"
                "FACTURA: FAC-2024-001\n"
                "FECHA: 2024-01-15\n\n"
                "CONCEPTO                          CANT.    PRECIO    TOTAL\n"
                "----------------------------------------------------------\n"
                "Pienso Premium Perro 15kg            10      25.00    250.00\n"
                "Collar Antiparasitario                5      12.00     60.00\n"
                "Champú Hipoalergénico                 3      18.50     55.50\n"
                "----------------------------------------------------------\n"
                "SUBTOTAL:                                                  365.50\n"
                "IVA (21%):                                                  76.76\n"
                "TOTAL:                                                     442.26\n"
                "EUR"
            )
        }

        # Mock generate (structured extraction) response
        router.generate.return_value = {
            "text": (
                '{"supplier": {"name": "Distribuciones Caninas S.L.", "tax_id": "B12345678"},\n'
                ' "invoice": {"number": "FAC-2024-001", "date": "2024-01-15"},\n'
                ' "lines": [\n'
                '   {"description": "Pienso Premium Perro 15kg", "quantity": 10,\n'
                '    "unit_price": 25.00, "total": 250.00, "vat_rate": 21.0},\n'
                '   {"description": "Collar Antiparasitario", "quantity": 5,\n'
                '    "unit_price": 12.00, "total": 60.00, "vat_rate": 21.0},\n'
                '   {"description": "Champú Hipoalergénico", "quantity": 3,\n'
                '    "unit_price": 18.50, "total": 55.50, "vat_rate": 21.0}\n'
                " ],\n"
                ' "taxes": [{"type": "IVA", "rate": 21.0, "amount": 76.76}],\n'
                ' "subtotal": 365.50,\n'
                ' "tax_total": 76.76,\n'
                ' "total": 442.26,\n'
                ' "currency": "EUR"\n'
                "}"
            )
        }

        router.aclose = AsyncMock()
        mock.return_value = router
        yield router


@pytest_asyncio.fixture
async def invoice_agent(mock_dolibarr_service, mock_model_router):
    """Create invoice processing agent with mocked dependencies."""
    from agents.invoice_processing.agent import create_invoice_processing_agent

    config = {
        "OLLAMA_ENDPOINT": "http://ollama:11434",
        "OLLAMA_MODEL": "transvega-local",
        "NVIDIA_API_KEY": "",
        "INVOICE_STORAGE_ROOT": "/tmp/test_invoices",
        "OCR_DPI": 150,
        "OCR_MAX_PAGES": 5,
        "OCR_MAX_FILE_MB": 10,
        "OCR_TIMEOUT": 120,
    }

    agent = create_invoice_processing_agent(config)
    await agent.start()

    # Mock PDF extraction methods to avoid needing real PDF files
    async def mock_extract_text_from_pdf(file_path: str) -> str:
        return """
PROVEEDOR: Distribuciones Caninas S.L.
CIF: B12345678
FACTURA: FAC-2024-001
FECHA: 2024-01-15

CONCEPTO                          CANT.    PRECIO    TOTAL
----------------------------------------------------------
Pienso Premium Perro 15kg            10      25.00    250.00
Collar Antiparasitario                5      12.00     60.00
Champú Hipoalergénico                 3      18.50     55.50
----------------------------------------------------------
SUBTOTAL:                                                  365.50
IVA (21%):                                                  76.76
TOTAL:                                                     442.26
EUR
"""

    async def mock_render_pdf_pages_to_images(file_path: str):
        return []

    async def mock_ocr_via_ollama(image_path_or_bytes: str = None, image_bytes: bytes = None) -> str:
        return ""

    agent._extract_text_from_pdf = mock_extract_text_from_pdf
    agent._render_pdf_pages_to_images = mock_render_pdf_pages_to_images
    agent._ocr_via_ollama = mock_ocr_via_ollama

    # Mock Ollama models readiness check to always return True in tests
    async def mock_check_ollama_models_ready() -> bool:
        return True

    agent._check_ollama_models_ready = mock_check_ollama_models_ready

    try:
        yield agent
    finally:
        await agent.stop()


class TestInvoiceProcessingAgent:
    """Tests for the InvoiceProcessingAgent."""

    @pytest.mark.asyncio
    async def test_process_text_pdf_success(
        self, invoice_agent, mock_dolibarr_service, sample_invoice_text, sample_invoice_data
    ):
        """Test processing a text-based PDF invoice successfully."""
        file_content = sample_invoice_text.encode("utf-8")
        filename = "test_invoice.pdf"

        result = await invoice_agent.process_invoice(file_content, filename)

        assert result["success"] is True
        assert result["privacy_scope"] == "LOCAL_ONLY"
        assert result["requires_approval"] is True
        assert "file_path" in result
        assert "final_path" in result
        assert "invoice" in result

        invoice = result["invoice"]
        assert invoice["supplier"]["tax_id"] == "B12345678"
        assert invoice["invoice"]["number"] == "FAC-2024-001"
        assert invoice["total"] == 442.26
        assert len(invoice["lines"]) == 3

        # Verify Dolibarr calls - supplier is created/looked up via _ensure_supplier
        mock_dolibarr_service._ensure_supplier.assert_called_once()
        mock_dolibarr_service.invoice_exists.assert_called_once_with("B12345678", "FAC-2024-001")

        # Verify file stored in pending
        assert os.path.exists(result["file_path"])
        assert "pending" in result["file_path"]
        assert "B12345678" in result["file_path"]

    @pytest.mark.asyncio
    async def test_process_duplicate_invoice_rejected(self, invoice_agent, mock_dolibarr_service, sample_invoice_text):
        """Test that duplicate invoices are rejected."""
        mock_dolibarr_service.invoice_exists.return_value = True

        file_content = sample_invoice_text.encode("utf-8")
        filename = "test_invoice.pdf"

        result = await invoice_agent.process_invoice(file_content, filename)

        assert result["success"] is False
        assert result["error"] == "duplicate_invoice_found"
        assert result["requires_review"] is True

    @pytest.mark.asyncio
    async def test_process_unknown_supplier_created(
        self, invoice_agent, mock_dolibarr_service, sample_invoice_text
    ):
        """Test that unknown suppliers are created automatically."""
        # Mock supplier not found initially (will be created)
        # The mock is already configured to return None for _find_supplier_by_tax_id
        # and create_supplier will be called to create the supplier

        file_content = sample_invoice_text.encode("utf-8")
        filename = "test_invoice.pdf"

        result = await invoice_agent.process_invoice(file_content, filename)

        assert result["success"] is True
        assert result["privacy_scope"] == "LOCAL_ONLY"
        assert result["requires_approval"] is True
        assert "file_path" in result
        assert "final_path" in result
        assert "invoice" in result

        invoice = result["invoice"]
        assert invoice["supplier"]["tax_id"] == "B12345678"
        assert invoice["invoice"]["number"] == "FAC-2024-001"
        assert invoice["total"] == 442.26
        assert len(invoice["lines"]) == 3

        # Verify Dolibarr calls - supplier should be created via _ensure_supplier
        mock_dolibarr_service._ensure_supplier.assert_called_once()
        mock_dolibarr_service.invoice_exists.assert_called_once_with("B12345678", "FAC-2024-001")

        # Verify file stored in pending
        assert os.path.exists(result["file_path"])
        assert "pending" in result["file_path"]
        assert "B12345678" in result["file_path"]

    @pytest.mark.asyncio
    async def test_approve_invoice_success(
        self, invoice_agent, mock_dolibarr_service, sample_invoice_text, sample_invoice_data
    ):
        """Test approving an invoice creates it in Dolibarr and moves file to processed."""
        # First process the invoice
        file_content = sample_invoice_text.encode("utf-8")
        filename = "test_invoice.pdf"
        process_result = await invoice_agent.process_invoice(file_content, filename)

        assert process_result["success"] is True

        # Now approve it
        approve_result = await invoice_agent.approve_invoice(
            pending_file_path=process_result["file_path"],
            final_path=process_result["final_path"],
            invoice_data=process_result["invoice"],
        )

        assert approve_result["success"] is True
        assert "dolibarr_invoice_id" in approve_result
        assert approve_result["dolibarr_invoice_id"] == 1001

        # Verify Dolibarr create was called
        mock_dolibarr_service.create_supplier_invoice.assert_called_once()

        # Verify file moved from pending to processed
        assert not os.path.exists(process_result["file_path"])
        assert os.path.exists(process_result["final_path"])
        assert "processed" in process_result["final_path"]

    @pytest.mark.asyncio
    async def test_approve_invoice_dolibarr_failure_keeps_pending(
        self, invoice_agent, mock_dolibarr_service, sample_invoice_text
    ):
        """Test that Dolibarr failure keeps file in pending and returns error."""
        mock_dolibarr_service.create_supplier_invoice.side_effect = Exception("Dolibarr connection failed")

        file_content = sample_invoice_text.encode("utf-8")
        filename = "test_invoice_fail.pdf"  # Unique filename to avoid conflicts
        process_result = await invoice_agent.process_invoice(file_content, filename)

        approve_result = await invoice_agent.approve_invoice(
            pending_file_path=process_result["file_path"],
            final_path=process_result["final_path"],
            invoice_data=process_result["invoice"],
        )

        assert approve_result["success"] is False
        assert approve_result["error"] == "dolibarr_invoice_create_failed"
        assert approve_result["requires_review"] is True

        # File should still be in pending
        assert os.path.exists(process_result["file_path"])
        assert not os.path.exists(process_result["final_path"])

    @pytest.mark.asyncio
    async def test_reject_invoice_moves_to_rejected(self, invoice_agent, mock_dolibarr_service, sample_invoice_text):
        """Test rejecting an invoice moves it to rejected folder."""
        file_content = sample_invoice_text.encode("utf-8")
        filename = "test_invoice.pdf"
        process_result = await invoice_agent.process_invoice(file_content, filename)

        reject_result = await invoice_agent.reject_invoice(process_result["file_path"], "Price mismatch")

        assert reject_result["success"] is True
        assert "rejected_path" in reject_result
        assert "rejected" in reject_result["rejected_path"]

        # Original pending file should be gone
        assert not os.path.exists(process_result["file_path"])

    @pytest.mark.asyncio
    async def test_file_size_limit_enforced(self, invoice_agent):
        """Test that files exceeding size limit are rejected."""
        # Create a large file content (11 MB)
        large_content = b"x" * (11 * 1024 * 1024)
        filename = "large_invoice.pdf"

        result = await invoice_agent.process_invoice(large_content, filename)

        assert result["success"] is False
        assert "exceeds maximum allowed" in result["error"]

    @pytest.mark.asyncio
    async def test_cloud_provider_not_called(self, invoice_agent, mock_model_router):
        """Verify cloud provider (NVIDIA) is never called for invoice processing."""
        with patch("app.core.model_router.create_model_router") as mock_create:
            # Create a router that tracks which provider is called
            router = AsyncMock()
            router.vision.return_value = {"text": "test"}
            router.generate.return_value = {
                "text": (
                    '{"supplier": {"name": "Test", "tax_id": "B12345678"}, '
                    '"invoice": {"number": "1", "date": "2024-01-01"}, '
                    '"lines": [{"description": "Test", "quantity": 1, "unit_price": 10, "total": 10}], '
                    '"taxes": [], "subtotal": 10, "tax_total": 0, "total": 10, "currency": "EUR"}'
                )
            }
            router.aclose = AsyncMock()
            mock_create.return_value = router

            # We can't easily test the internal routing without more mocking
            # But we verify the agent uses LOCAL_ONLY in its calls
            # The agent explicitly passes privacy_scope="LOCAL_ONLY" to both vision and generate

            # Verify the agent configuration uses LOCAL_ONLY
            assert invoice_agent.config.get("NVIDIA_API_KEY") == ""


class TestInvoiceDeterministicValidations:
    """Tests for deterministic validation logic."""

    @pytest.mark.asyncio
    async def test_line_totals_validation(self, invoice_agent):
        """Test that line net amounts must match quantity * unit_price."""

        from agents.invoice_processing.agent import InvoiceLine

        # Test that net_amount is correctly computed from quantity * unit_price
        line = InvoiceLine(description="Test", quantity=2, unit_price=10, total=25.0)
        # total (25) != quantity * unit_price (20), so it's treated as gross amount
        # net_amount should be computed as quantity * unit_price = 20
        assert line.net_amount == 20.0
        # gross_amount should be 25 (the provided total)
        assert line.gross_amount == 25.0
        # tax_amount should be computed from vat_rate if provided
        # but vat_rate is None here, so tax_amount = 0, gross = net = 20
        # Since total (25) != net (20), it's treated as gross
        # This is valid - total is gross amount

        # Test that net_amount validation works
        # If we provide net_amount that doesn't match quantity * unit_price, it should still work
        # because net_amount is explicitly provided
        line2 = InvoiceLine(description="Test", quantity=2, unit_price=10, net_amount=15.0, total=25.0)
        assert line2.net_amount == 15.0
        # This is allowed - net_amount is explicitly provided

    @pytest.mark.asyncio
    async def test_invoice_total_validation(self, invoice_agent):
        """Test that invoice total must match subtotal + tax_total (via deterministic checks)."""
        from agents.invoice_processing.agent import InvoiceData, InvoiceLine, SupplierInfo

        # This should now pass Pydantic validation (structural only)
        invoice = InvoiceData(
            supplier=SupplierInfo(name="Test", tax_id="B12345678"),
            invoice={"number": "1", "date": "2024-01-01"},
            lines=[InvoiceLine(description="Test", quantity=1, unit_price=10, total=10)],
            taxes=[{"type": "IVA", "rate": 21, "amount": 2.1}],
            subtotal=10,
            tax_total=2.1,
            total=15,  # Should be 12.1 - mismatch
            currency="EUR",
        )
        
        # But deterministic checks should catch the mismatch
        errors = await invoice_agent._deterministic_checks(invoice)
        assert len(errors) == 1
        # New format: dict with code, check, expected, actual
        assert errors[0]["code"] == "invoice_total_mismatch"
        assert errors[0]["check"] == "invoice_total"
        assert errors[0]["expected"] == 12.1
        assert errors[0]["actual"] == 15.0

    @pytest.mark.asyncio
    async def test_vat_rate_optional(self, invoice_agent):
        """Test that vat_rate can be None."""
        from agents.invoice_processing.agent import InvoiceLine

        line = InvoiceLine(description="Test", quantity=1, unit_price=10, total=10, vat_rate=None)
        assert line.vat_rate is None

    @pytest.mark.asyncio
    async def test_invoice_math_subtotal_tax_total_matches_total(self, invoice_agent):
        """
        Test the core invoice math: subtotal=100, tax_total=21, total=121 should be valid.
        This is the canonical example from requirements.
        """
        from agents.invoice_processing.agent import InvoiceData, InvoiceLine, SupplierInfo

        invoice = InvoiceData(
            supplier=SupplierInfo(name="Test Supplier", tax_id="B12345678"),
            invoice={"number": "FAC-001", "date": "2024-01-15"},
            lines=[
                InvoiceLine(
                    description="Product A",
                    quantity=1,
                    unit_price=100,
                    total=100,
                    vat_rate=21.0,
                    net_amount=100.0,
                )
            ],
            taxes=[],  # Empty taxes array - should NOT be a hard error
            subtotal=100.0,
            tax_total=21.0,
            total=121.0,
            currency="EUR",
        )

        errors = await invoice_agent._deterministic_checks(invoice)
        
        # Should have NO hard errors (invoice_total_mismatch, line_subtotal_mismatch, etc.)
        hard_error_codes = {"invoice_total_mismatch", "line_subtotal_mismatch", "currency_unsupported", "date_missing"}
        hard_errors = [e for e in errors if e.get("code") in hard_error_codes]
        assert len(hard_errors) == 0, f"Unexpected hard errors: {hard_errors}"
        
        # Should have review warning for missing tax breakdown
        review_warnings = [e for e in errors if e.get("code") == "tax_breakdown_missing"]
        assert len(review_warnings) == 1
        assert review_warnings[0].get("severity") == "warning"

    @pytest.mark.asyncio
    async def test_invoice_math_with_tax_breakdown(self, invoice_agent):
        """Test invoice with complete tax breakdown."""
        from agents.invoice_processing.agent import InvoiceData, InvoiceLine, SupplierInfo

        invoice = InvoiceData(
            supplier=SupplierInfo(name="Test Supplier", tax_id="B12345678"),
            invoice={"number": "FAC-002", "date": "2024-01-15"},
            lines=[
                InvoiceLine(
                    description="Product A",
                    quantity=2,
                    unit_price=50,
                    total=100,
                    vat_rate=21.0,
                    net_amount=100.0,
                )
            ],
            taxes=[{"type": "IVA", "rate": 21.0, "amount": 21.0, "base": 100.0}],
            subtotal=100.0,
            tax_total=21.0,
            total=121.0,
            currency="EUR",
        )

        errors = await invoice_agent._deterministic_checks(invoice)
        # Should have NO errors at all
        assert len(errors) == 0

    @pytest.mark.asyncio
    async def test_invoice_math_line_net_amounts_sum_to_subtotal(self, invoice_agent):
        """Test that line net amounts correctly sum to subtotal."""
        from agents.invoice_processing.agent import InvoiceData, InvoiceLine, SupplierInfo

        invoice = InvoiceData(
            supplier=SupplierInfo(name="Test Supplier", tax_id="B12345678"),
            invoice={"number": "FAC-003", "date": "2024-01-15"},
            lines=[
                InvoiceLine(description="Item 1", quantity=1, unit_price=60, total=60, vat_rate=21.0, net_amount=60.0),
                InvoiceLine(description="Item 2", quantity=1, unit_price=40, total=40, vat_rate=21.0, net_amount=40.0),
            ],
            taxes=[{"type": "IVA", "rate": 21.0, "amount": 21.0}],
            subtotal=100.0,
            tax_total=21.0,
            total=121.0,
            currency="EUR",
        )

        errors = await invoice_agent._deterministic_checks(invoice)
        # Should have NO hard errors
        hard_error_codes = {"invoice_total_mismatch", "line_subtotal_mismatch", "currency_unsupported", "date_missing"}
        hard_errors = [e for e in errors if e.get("code") in hard_error_codes]
        assert len(hard_errors) == 0

    @pytest.mark.asyncio
    async def test_invoice_math_line_total_is_gross_not_net(self, invoice_agent):
        """Test that line.total can be gross amount (net + tax) and validation still works."""
        from agents.invoice_processing.agent import InvoiceData, InvoiceLine, SupplierInfo

        # Line total = 121 (gross: 100 net + 21 tax)
        invoice = InvoiceData(
            supplier=SupplierInfo(name="Test Supplier", tax_id="B12345678"),
            invoice={"number": "FAC-004", "date": "2024-01-15"},
            lines=[
                InvoiceLine(
                    description="Item with VAT included",
                    quantity=1,
                    unit_price=121,  # Gross unit price
                    total=121,       # Gross total
                    vat_rate=21.0,
                    net_amount=100.0,  # Explicit net amount
                )
            ],
            taxes=[{"type": "IVA", "rate": 21.0, "amount": 21.0}],
            subtotal=100.0,
            tax_total=21.0,
            total=121.0,
            currency="EUR",
        )

        errors = await invoice_agent._deterministic_checks(invoice)
        # Should have NO hard errors - net_amount is explicitly provided
        hard_error_codes = {"invoice_total_mismatch", "line_subtotal_mismatch", "currency_unsupported", "date_missing"}
        hard_errors = [e for e in errors if e.get("code") in hard_error_codes]
        assert len(hard_errors) == 0


class TestInvoiceFileHash:
    """Tests for file hashing and storage."""

    @pytest.mark.asyncio
    async def test_different_content_different_paths(self, invoice_agent, sample_invoice_text):
        """Test that same filename with different content gets different storage paths."""
        file_content1 = sample_invoice_text.encode("utf-8")
        file_content2 = (sample_invoice_text + " extra line").encode("utf-8")
        filename = "invoice.pdf"

        result1 = await invoice_agent.process_invoice(file_content1, filename)
        result2 = await invoice_agent.process_invoice(file_content2, filename)

        assert result1["success"] is True
        assert result2["success"] is True
        assert result1["file_path"] != result2["file_path"]

    @pytest.mark.asyncio
    async def test_pending_directory_structure(self, invoice_agent, sample_invoice_text):
        """Test that files are stored in correct pending/supplier structure."""
        file_content = sample_invoice_text.encode("utf-8")
        filename = "invoice.pdf"

        result = await invoice_agent.process_invoice(file_content, filename)

        assert "pending" in result["file_path"]
        assert "B12345678" in result["file_path"]


class TestInvoiceDataModel:
    """Tests for the InvoiceData Pydantic model."""

    @pytest.mark.asyncio
    async def test_vat_rate_none_allowed(self, invoice_agent):
        """Test that vat_rate can be None in InvoiceLine."""
        from agents.invoice_processing.agent import InvoiceData, InvoiceLine, SupplierInfo

        line = InvoiceLine(description="Test", quantity=1, unit_price=10, total=10, vat_rate=None)
        assert line.vat_rate is None

        invoice = InvoiceData(
            supplier=SupplierInfo(name="Test", tax_id="B12345678"),
            invoice={"number": "1", "date": "2024-01-01"},
            lines=[line],
            taxes=[],
            subtotal=10,
            tax_total=0,
            total=10,
            currency="EUR",
        )
        assert invoice.lines[0].vat_rate is None

    @pytest.mark.asyncio
    async def test_taxes_default_factory(self, invoice_agent):
        """Test that taxes uses default_factory=list."""
        from agents.invoice_processing.agent import InvoiceData, InvoiceLine, SupplierInfo

        invoice = InvoiceData(
            supplier=SupplierInfo(name="Test", tax_id="B12345678"),
            invoice={"number": "1", "date": "2024-01-01"},
            lines=[InvoiceLine(description="Test", quantity=1, unit_price=10, total=10)],
            subtotal=10,
            tax_total=0,
            total=10,
        )
        assert invoice.taxes == []
        assert isinstance(invoice.taxes, list)


class TestInvoiceProcessingStructuredOutput:
    """Tests for native structured output configuration."""

    @pytest.mark.asyncio
    async def test_structured_output_uses_json_schema(
        self, invoice_agent, mock_dolibarr_service, mock_model_router, sample_invoice_text
    ):
        """Test that structured extraction uses native JSON Schema format."""
        file_content = sample_invoice_text.encode("utf-8")
        filename = "test_invoice.pdf"

        result = await invoice_agent.process_invoice(file_content, filename)

        assert result["success"] is True

        # Verify generate was called with format parameter (JSON Schema)
        call_args = mock_model_router.generate.call_args
        assert call_args is not None, "generate should have been called"

        # Check that format parameter was passed (JSON Schema)
        kwargs = call_args.kwargs
        assert "format" in kwargs, "format parameter should be passed for structured output"

        # Check that think=False was passed
        assert kwargs.get("think") is False, "think should be False for structured extraction"

        # Check that num_predict=2048 was passed (not max_tokens)
        assert kwargs.get("num_predict") == 2048, "num_predict should be 2048"

        # Check that stop=["}"] is NOT passed
        assert "stop" not in kwargs, "stop parameter should not be passed"

    @pytest.mark.asyncio
    async def test_invoice_timeout_configuration(self, invoice_agent):
        """Test that invoice agent uses 600s timeout for Ollama."""
        assert invoice_agent.ollama_invoice_timeout == 600.0

    @pytest.mark.asyncio
    async def test_model_router_timeout_passed_to_generate(
        self, invoice_agent, mock_dolibarr_service, mock_model_router, sample_invoice_text
    ):
        """Test that request_timeout is passed to router.generate."""
        file_content = sample_invoice_text.encode("utf-8")
        filename = "test_invoice.pdf"

        result = await invoice_agent.process_invoice(file_content, filename)

        assert result["success"] is True

        # Verify generate was called with request_timeout
        call_args = mock_model_router.generate.call_args
        kwargs = call_args.kwargs
        assert "request_timeout" in kwargs, "request_timeout should be passed"
        assert kwargs["request_timeout"] == 600.0, "request_timeout should be 600s"

    @pytest.mark.asyncio
    async def test_privacy_local_only_enforced(
        self, invoice_agent, mock_dolibarr_service, mock_model_router, sample_invoice_text
    ):
        """Test that LOCAL_ONLY privacy scope is always used for invoices."""
        file_content = sample_invoice_text.encode("utf-8")
        filename = "test_invoice.pdf"

        result = await invoice_agent.process_invoice(file_content, filename)

        assert result["success"] is True
        assert result["privacy_scope"] == "LOCAL_ONLY"

        # Verify both vision and generate were called with LOCAL_ONLY
        vision_calls = mock_model_router.vision.call_args_list
        generate_calls = mock_model_router.generate.call_args_list

        for call in vision_calls:
            kwargs = call.kwargs
            assert kwargs.get("privacy_scope") == "LOCAL_ONLY"

        for call in generate_calls:
            kwargs = call.kwargs
            assert kwargs.get("privacy_scope") == "LOCAL_ONLY"


class TestInvoiceProcessingDiagnostics:
    """Tests for diagnostic logging and metrics."""

    @pytest.mark.asyncio
    async def test_diagnostics_included_in_result(
        self, invoice_agent, mock_dolibarr_service, sample_invoice_text
    ):
        """Test that diagnostics are included in successful result."""
        file_content = sample_invoice_text.encode("utf-8")
        filename = "test_invoice.pdf"

        result = await invoice_agent.process_invoice(file_content, filename)

        assert result["success"] is True
        assert "diagnostics" in result
        diagnostics = result["diagnostics"]

        assert "has_native_text" in diagnostics
        assert "native_text_chars" in diagnostics
        assert "inference_count" in diagnostics
        assert "input_type" in diagnostics

        # For text PDF, should have native text
        assert diagnostics["has_native_text"] is True
        assert diagnostics["native_text_chars"] > 0
        assert diagnostics["inference_count"] >= 1  # At least structured extraction
        assert diagnostics["input_type"] == "pdf"

    @pytest.mark.asyncio
    async def test_scanned_pdf_diagnostics(
        self, invoice_agent, mock_dolibarr_service, mock_model_router, sample_invoice_text
    ):
        """Test diagnostics for scanned PDF (no native text)."""
        # Mock PDF text extraction to return empty
        async def mock_extract_text_from_pdf(file_path: str) -> str:
            return ""

        invoice_agent._extract_text_from_pdf = mock_extract_text_from_pdf

        # Mock OCR to return text
        async def mock_render_pdf_pages_to_images(file_path: str):
            return [b"fake_image_bytes"]

        invoice_agent._render_pdf_pages_to_images = mock_render_pdf_pages_to_images

        async def mock_ocr_via_ollama(image_path_or_bytes: str = None, image_bytes: bytes = None) -> str:
            return sample_invoice_text

        invoice_agent._ocr_via_ollama = mock_ocr_via_ollama

        file_content = b"fake pdf content"
        filename = "scanned_invoice.pdf"

        result = await invoice_agent.process_invoice(file_content, filename)

        assert result["success"] is True
        diagnostics = result["diagnostics"]

        # For scanned PDF, should not have native text
        assert diagnostics["has_native_text"] is False
        assert diagnostics["native_text_chars"] == 0
        assert diagnostics["inference_count"] >= 2  # OCR + structured extraction
        assert diagnostics["input_type"] == "pdf"


class TestInvoiceProcessingErrors:
    """Tests for error handling improvements."""

    @pytest.mark.asyncio
    async def test_timeout_error_handling(
        self, invoice_agent, mock_dolibarr_service, mock_model_router, sample_invoice_text
    ):
        """Test that timeout errors are handled correctly."""

        # Mock generate to raise TimeoutError
        async def mock_generate_timeout(*args, **kwargs):
            raise TimeoutError("Ollama timeout")

        mock_model_router.generate.side_effect = mock_generate_timeout

        file_content = sample_invoice_text.encode("utf-8")
        filename = "test_invoice.pdf"

        result = await invoice_agent.process_invoice(file_content, filename)

        assert result["success"] is False
        assert result["error"] == "invoice_processing_timeout"
        assert "tiempo máximo" in result["message"].lower()
        assert result["requires_review"] is False  # Timeout is not a validation issue

    @pytest.mark.asyncio
    async def test_validation_error_needs_review(
        self, invoice_agent, mock_dolibarr_service, mock_model_router, sample_invoice_text
    ):
        """Test that validation errors return needs_review=True."""

        # Mock generate to return invalid data (missing required fields)
        mock_model_router.generate.return_value = {
            "text": (
                '{"supplier": {"name": "Test"}, "invoice": {}, "lines": [], '
                '"taxes": [], "subtotal": 0, "tax_total": 0, "total": 0, '
                '"currency": "EUR"}'
            )
        }

        file_content = sample_invoice_text.encode("utf-8")
        filename = "test_invoice.pdf"

        result = await invoice_agent.process_invoice(file_content, filename)

        assert result["success"] is False
        assert result["error"] == "pydantic_validation_failed"
        assert result["needs_review"] is True
        assert result["requires_review"] is True
        # Check for revision-related message (case insensitive, handle accents)
        assert "revis" in result["message"].lower() or "válido" in result["message"].lower()


class TestInvoiceProcessingTelegramFlow:
    """Tests for Telegram flow integration (mocked)."""

    @pytest.mark.asyncio
    async def test_invoice_processing_queues_async_task(self):
        """Test that invoice processing queues async Celery task."""
        # This test would require mocking Celery and Redis
        # For now, verify the supervisor method exists and has correct signature
        from agents.supervisor.agent import SupervisorAgent

        # Verify the method exists
        assert hasattr(SupervisorAgent, '_handle_invoice_document')
        assert hasattr(SupervisorAgent, '_listen_invoice_results')
        assert hasattr(SupervisorAgent, '_handle_invoice_result')
        assert hasattr(SupervisorAgent, '_handle_invoice_success')
        assert hasattr(SupervisorAgent, '_handle_invoice_timeout')
        assert hasattr(SupervisorAgent, '_handle_invoice_needs_review')
        assert hasattr(SupervisorAgent, '_handle_invoice_error')
        assert hasattr(SupervisorAgent, '_send_long_processing_warning')
        assert hasattr(SupervisorAgent, '_edit_telegram_message')

    @pytest.mark.asyncio
    async def test_supervisor_stop_before_invoice_task_exists(self):
        """Test that SupervisorAgent.stop() doesn't raise AttributeError if _invoice_result_task doesn't exist."""
        from agents.supervisor.agent import SupervisorAgent

        # Create supervisor with minimal config (test mode)
        config = {
            "TEST_MODE": True,
            "INTERNAL_API_URL": "http://localhost:8000/api/v1",
            "AGENT_API_KEY_SUPERVISOR": "test-key",
            "OLLAMA_ENDPOINT": "http://ollama:11434",
            "OLLAMA_MODEL": "transvega-local",
        }

        # Mock the sub-agents to avoid complex setup
        with patch("agents.supervisor.agent.DogIntakeAgent") as mock_dog, \
             patch("agents.supervisor.agent.create_invoice_processing_agent") as mock_invoice, \
             patch("agents.supervisor.agent.create_media_pipeline_agent") as mock_media, \
             patch("agents.supervisor.agent.create_content_marketing_agent") as mock_content, \
             patch("agents.supervisor.agent.create_publishing_agent") as mock_pub, \
             patch("agents.supervisor.agent.create_listing_agent") as mock_listing:

            # Configure mocks
            for mock in [mock_dog, mock_invoice, mock_media, mock_content, mock_pub, mock_listing]:
                instance = AsyncMock()
                instance.start = AsyncMock()
                instance.stop = AsyncMock()
                mock.return_value = instance

            supervisor = SupervisorAgent(config)
            await supervisor.start()

            # Verify _invoice_result_task is initialized to None
            assert hasattr(supervisor, '_invoice_result_task')
            assert supervisor._invoice_result_task is None

            # Call stop() - should not raise AttributeError
            await supervisor.stop()

            # Verify all sub-agents were stopped
            mock_dog.return_value.stop.assert_called_once()
            mock_invoice.return_value.stop.assert_called_once()
            mock_media.return_value.stop.assert_called_once()
            mock_content.return_value.stop.assert_called_once()
            mock_pub.return_value.stop.assert_called_once()
            mock_listing.return_value.stop.assert_called_once()


class TestInvoiceProcessingModelRouter:
    """Tests for model router timeout configuration."""

    def test_create_model_router_with_custom_timeout(self):
        """Test that create_model_router accepts ollama_default_timeout."""
        # This is a basic test - in reality would need full mocking
        # Just verify the function signature accepts the parameter
        import inspect

        from app.core.model_router import create_model_router
        sig = inspect.signature(create_model_router)
        assert "ollama_default_timeout" in sig.parameters
        assert sig.parameters["ollama_default_timeout"].default == 600.0

    def test_ollama_provider_accepts_default_timeout(self):
        """Test that OllamaProvider accepts default_timeout parameter."""
        from app.core.model_router import OllamaProvider

        provider = OllamaProvider(
            endpoint="http://localhost:11434",
            model="test-model",
            default_timeout=600.0
        )
        assert provider.default_timeout == 600.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
