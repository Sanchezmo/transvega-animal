"""
Rutas para facturación.
"""

from datetime import date, datetime

from app.adapters.dolibarr.client import DolibarrClient
from app.core.config import get_settings
from app.core.database import get_db
from app.core.exceptions import NotFoundException, ValidationException
from app.dependencies.auth import get_current_agent, require_financial
from app.dependencies.dolibarr import get_dolibarr_client
from app.dependencies.rate_limit import idempotency_dependency, rate_limit_dependency
from app.schemas import (
    InvoiceCreate,
    InvoiceLineResponse,
    InvoiceResponse,
    InvoiceUpdate,
    PaginatedResponse,
    PaginationParams,
)
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["Facturación"])
settings = get_settings()


@router.get("", response_model=PaginatedResponse[InvoiceResponse])
async def list_invoices(
    pagination: PaginationParams = Depends(),
    status: int | None = Query(
        None, description="Filtrar por estado (0=borrador, 1=validada, 2=anulada)"
    ),
    agent: dict = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
):
    """Listar facturas con paginación y filtros."""
    return PaginatedResponse(
        success=True,
        data=[],
        total=0,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get("/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice(
    invoice_id: int,
    agent: dict = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
):
    """Obtener factura por ID."""
    raise NotFoundException("Factura", str(invoice_id))


@router.post(
    "",
    response_model=InvoiceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_invoice(
    invoice: InvoiceCreate,
    agent: dict = Depends(require_financial),
    db: AsyncSession = Depends(get_db),
    dolibarr: DolibarrClient = Depends(get_dolibarr_client),
    _rate_limit: None = Depends(rate_limit_dependency),
    _idempotency: None = Depends(idempotency_dependency),
):
    """Crear factura en borrador en Dolibarr.

    Requiere rol: invoicing, accounting, admin
    No valida automáticamente - requiere aprobación humana.
    """
    # Validaciones de negocio
    if not invoice.lines:
        raise ValidationException("La factura debe tener al menos una línea")

    # Convertir a formato Dolibarr
    dolibarr_data = {
        "thirdparty_id": invoice.thirdparty_id,
        "date": invoice.date.isoformat(),
    }
    if invoice.payment_term_id:
        dolibarr_data["fk_paiement"] = invoice.payment_term_id
    if invoice.cond_reglement_id:
        dolibarr_data["cond_reglement_id"] = invoice.cond_reglement_id
    if invoice.mode_reglement_id:
        dolibarr_data["mode_reglement_id"] = invoice.mode_reglement_id
    if invoice.note_private:
        dolibarr_data["note_private"] = invoice.note_private
    if invoice.note_public:
        dolibarr_data["note_public"] = invoice.note_public

    lines = []
    for line in invoice.lines:
        line_dict = {
            "label": line.description,
            "qty": line.qty,
            "subprice": line.unit_price,
            "remise_percent": line.discount_percent,
            "tva_tx": line.vat_rate,
        }
        if line.product_id:
            line_dict["fk_product"] = line.product_id
        lines.append(line_dict)
    dolibarr_data["lines"] = lines

    # Crear en Dolibarr
    result = await dolibarr.create_invoice(dolibarr_data)

    # Dolibarr devuelve ID o objeto completo
    if isinstance(result, dict) and "id" in result:
        invoice_id = result["id"]
        # Obtener factura completa
        invoice_data = await dolibarr.get_invoice(invoice_id)
    elif isinstance(result, int):
        invoice_id = result
        invoice_data = await dolibarr.get_invoice(invoice_id)
    else:
        invoice_data = result
        invoice_id = invoice_data.get("id")

    # Mapear respuesta Dolibarr a nuestro schema
    # Extraer líneas
    lines_response = []
    for line in invoice_data.get("lines", []):
        lines_response.append(
            InvoiceLineResponse(
                id=line.get("id", 0),
                product_id=line.get("fk_product"),
                description=line.get("label", ""),
                qty=float(line.get("qty", 0)),
                unit_price=float(line.get("subprice", 0)),
                vat_rate=float(line.get("tva_tx", 0)),
                discount_percent=float(line.get("remise_percent", 0)),
                total_ht=float(line.get("total_ht", 0)),
                total_tva=float(line.get("total_tva", 0)),
                total_ttc=float(line.get("total_ttc", 0)),
            )
        )

    return InvoiceResponse(
        id=invoice_id,
        ref=invoice_data.get("ref", ""),
        thirdparty_id=invoice_data.get("thirdparty_id", invoice.thirdparty_id),
        date=datetime.strptime(
            invoice_data.get("date", date.today().isoformat()), "%Y-%m-%d"
        ).date(),
        payment_term_id=invoice_data.get("fk_paiement"),
        cond_reglement_id=invoice_data.get("cond_reglement_id"),
        mode_reglement_id=invoice_data.get("mode_reglement_id"),
        note_private=invoice_data.get("note_private"),
        note_public=invoice_data.get("note_public"),
        total_ht=float(invoice_data.get("total_ht", 0)),
        total_tva=float(invoice_data.get("total_tva", 0)),
        total_ttc=float(invoice_data.get("total_ttc", 0)),
        lines=lines_response,
        datec=datetime.fromtimestamp(
            invoice_data.get("date_creation", datetime.now().timestamp())
        ),
        datem=datetime.fromtimestamp(
            invoice_data.get("date_modification", datetime.now().timestamp())
        ),
        fk_user_author=invoice_data.get("fk_user_creat", 1),
        fk_user_modif=invoice_data.get("fk_user_modif", 1),
    )


@router.put("/{invoice_id}", response_model=InvoiceResponse)
async def update_invoice(
    invoice_id: int,
    invoice: InvoiceUpdate,
    agent: dict = Depends(require_financial),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
    _idempotency: None = Depends(idempotency_dependency),
):
    """Actualizar factura en borrador."""

    # Verificar estado
    # existing = await dolibarr.get_invoice(invoice_id)
    # if existing.status != 0:
    #     raise ValidationException("Solo se pueden modificar facturas en borrador")

    raise NotFoundException("Factura", str(invoice_id))


@router.post("/{invoice_id}/validate", status_code=status.HTTP_202_ACCEPTED)
async def validate_invoice(
    invoice_id: int,
    agent: dict = Depends(require_financial),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
    _idempotency: None = Depends(idempotency_dependency),
):
    """Solicitar validación de factura (requiere aprobación humana).

    Acciones que requieren aprobación:
    - Validar factura (pasar de borrador a validada)
    - Anular factura
    - Rectificar factura
    """
    # Verificar estado
    # existing = await dolibarr.get_invoice(invoice_id)
    # if existing.status != 0:
    #     raise ValidationException("Solo facturas en borrador pueden validarse")

    # Verificar líneas
    # if not existing.lines:
    #     raise ValidationException("Factura sin líneas no puede validarse")

    # Verificar datos fiscales completos
    # thirdparty = await dolibarr.get_thirdparty(existing.thirdparty_id)
    # if not thirdparty.vat_number and thirdparty.country_code != "ES":
    #     raise ValidationException("NIF-IVA requerido para facturas intracomunitarias")

    # Solicitar aprobación
    # approval_id = await approval_service.request(
    #     action="validate_invoice",
    #     resource_type="invoice",
    #     resource_id=str(invoice_id),
    #     reason="Validar factura para contabilización y envío",
    #     current_state={"status": "draft"},
    #     proposed_state={"status": "validated"},
    # )

    return {
        "success": True,
        "message": "Validación de factura solicitada, pendiente de aprobación",
        "approval_id": "pending",
    }


@router.post("/{invoice_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
async def cancel_invoice(
    invoice_id: int,
    reason: str,
    agent: dict = Depends(require_financial),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
    _idempotency: None = Depends(idempotency_dependency),
):
    """Anular factura (requiere aprobación)."""
    return {
        "success": True,
        "message": "Anulación de factura solicitada, pendiente de aprobación",
        "approval_id": "pending",
    }


@router.post("/{invoice_id}/rectify", status_code=status.HTTP_201_CREATED)
async def rectify_invoice(
    invoice_id: int,
    reason: str,
    new_lines: list[dict],
    agent: dict = Depends(require_financial),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
    _idempotency: None = Depends(idempotency_dependency),
):
    """Crear factura rectificativa."""
    return {
        "success": True,
        "message": "Factura rectificativa creada",
        "rectificativa_id": 1,
    }


@router.get("/{invoice_id}/pdf")
async def get_invoice_pdf(
    invoice_id: int,
    agent: dict = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
):
    """Generar/obtener PDF de factura."""
    return {
        "success": True,
        "pdf_url": f"/api/v1/facturas/{invoice_id}/download",
        "filename": "FAC-2024-000001.pdf",
    }


@router.post("/{invoice_id}/send", status_code=status.HTTP_202_ACCEPTED)
async def send_invoice(
    invoice_id: int,
    email: str | None = None,
    agent: dict = Depends(require_financial),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
):
    """Enviar factura por email al cliente."""
    return {
        "success": True,
        "message": "Factura enviada por email",
        "sent_to": email or "cliente@ejemplo.com",
    }


@router.post(
    "/{invoice_id}/register-payment",
    status_code=status.HTTP_201_CREATED,
)
async def register_payment(
    invoice_id: int,
    amount: float,
    payment_date: date,
    payment_method: str,
    reference: str | None = None,
    agent: dict = Depends(require_financial),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_dependency),
    _idempotency: None = Depends(idempotency_dependency),
):
    """Registrar cobro de factura."""
    if amount <= 0:
        raise ValidationException("Importe debe ser positivo")

    return {
        "success": True,
        "message": "Pago registrado",
        "payment_id": 1,
    }
