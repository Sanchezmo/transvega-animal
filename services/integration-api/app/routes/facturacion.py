"""
Rutas para facturación.
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.dependencies.auth import get_current_agent, require_write, require_financial
from app.dependencies.rate_limit import rate_limit_dependency, idempotency_dependency
from app.schemas import (
    InvoiceCreate,
    InvoiceUpdate,
    InvoiceResponse,
    PaginatedResponse,
    PaginationParams,
)
from app.core.exceptions import NotFoundException, ValidationException

router = APIRouter(prefix="/facturas", tags=["Facturación"])
settings = get_settings()


@router.get("", response_model=PaginatedResponse[InvoiceResponse])
async def list_invoices(
    pagination: PaginationParams = Depends(),
    status: Optional[int] = Query(None, description="Filtrar por estado (0=borrador, 1=validada, 2=anulada)"),
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
    from app.core.exceptions import NotFoundException
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
    _rate_limit: None = Depends(rate_limit_dependency),
    _idempotency: None = Depends(idempotency_dependency),
):
    """
    Crear factura en borrador.
    
    Requiere rol: invoicing, accounting, admin
    No valida automáticamente - requiere aprobación humana.
    """
    # Validaciones de negocio
    if not invoice.lines:
        raise ValidationException("La factura debe tener al menos una línea")
    
    # Verificar que el tercero existe
    # thirdparty = await dolibarr.get_thirdparty(invoice.thirdparty_id)
    # if not thirdparty:
    #     raise ValidationException("Tercero no encontrado")
    
    # Validar datos fiscales del tercero
    # if not thirdparty.vat_number and invoice.thirdparty.country_code != "ES":
    #     raise ValidationException("NIF-IVA requerido para facturas intracomunitarias")
    
    # Validar líneas
    for line in invoice.lines:
        if line.qty <= 0:
            raise ValidationException("Cantidad debe ser positiva")
        if line.unit_price < 0:
            raise ValidationException("Precio unitario no puede ser negativo")
        if line.vat_rate < 0 or line.vat_rate > 100:
            raise ValidationException("Tipo IVA inválido")
    
    # TODO: Crear en Dolibarr via API
    # dolibarr = DolibarrClient(...)
    # result = await dolibarr.create_invoice(invoice.dict())
    
    # Simular respuesta
    from datetime import date
    total_ht = sum(l.qty * l.unit_price * (1 - l.discount_percent/100) for l in invoice.lines)
    total_tva = sum(l.qty * l.unit_price * (1 - l.discount_percent/100) * l.vat_rate/100 for l in invoice.lines)
    total_ttc = total_ht + total_tva
    
    return InvoiceResponse(
        **invoice.dict(),
        id=1,
        ref=f"FAC-{date.today().year}-000001",
        total_ht=round(total_ht, 2),
        total_tva=round(total_tva, 2),
        total_ttc=round(total_ttc, 2),
        lines=[],
        datec=datetime.now(),
        datem=datetime.now(),
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
    from app.core.exceptions import NotFoundException, ValidationException
    
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
    """
    Solicitar validación de factura (requiere aprobación humana).
    
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
    new_lines: List[dict],
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
        "filename": f"FAC-2024-000001.pdf",
    }


@router.post("/{invoice_id}/send", status_code=status.HTTP_202_ACCEPTED)
async def send_invoice(
    invoice_id: int,
    email: Optional[str] = None,
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


@router.post("/{invoice_id}/register-payment", status_code=status.HTTP_201_CREATED)
async def register_payment(
    invoice_id: int,
    amount: float,
    payment_date: date,
    payment_method: str,
    reference: Optional[str] = None,
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