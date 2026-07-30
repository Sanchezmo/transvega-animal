"""
Rutas para Proveedores (Terceros con supplier=1) y Facturas/Órdenes de Proveedor.
"""
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel

from app.core.config import get_settings
from app.dependencies.auth import get_current_agent, require_write, require_financial
from app.dependencies.dolibarr import get_dolibarr_client
from app.dependencies.rate_limit import rate_limit_dependency, idempotency_dependency
from app.schemas import (
    ThirdPartyCreate,
    ThirdPartyUpdate,
    ThirdPartyResponse,
    SupplierInvoiceCreate,
    SupplierInvoiceUpdate,
    SupplierInvoiceResponse,
    SupplierOrderCreate,
    SupplierOrderUpdate,
    SupplierOrderResponse,
    SupplierProposalCreate,
    SupplierProposalUpdate,
    SupplierProposalResponse,
    PaginationParams,
    PaginatedResponse,
)
from app.adapters.dolibarr.client import DolibarrClient
from app.core.exceptions import NotFoundException, ValidationException

settings = get_settings()

# =============================================================================
# PROVEEDORES (TERCEROS CON SUPPLIER=1)
# =============================================================================

router = APIRouter(prefix="/proveedores", tags=["Proveedores"])


@router.get("", response_model=PaginatedResponse[ThirdPartyResponse])
async def list_proveedores(
    pagination: PaginationParams = Depends(),
    sqlfilters: Optional[str] = Query(default=None, description="Filtros SQL adicionales"),
    dolibarr: DolibarrClient = Depends(get_dolibarr_client),
    current_agent = Depends(get_current_agent),
):
    """Listar proveedores (terceros con supplier=1)."""
    proveedores = await dolibarr.list_suppliers(
        limit=pagination.limit,
        offset=pagination.offset,
        sqlfilters=sqlfilters,
    )
    
    return PaginatedResponse(
        success=True,
        data=proveedores,
        total=len(proveedores),
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get("/{proveedor_id}", response_model=ThirdPartyResponse)
async def get_proveedor(
    proveedor_id: int,
    dolibarr: DolibarrClient = Depends(get_dolibarr_client),
    current_agent = Depends(get_current_agent),
):
    """Obtener proveedor por ID."""
    try:
        proveedor = await dolibarr.get_supplier(proveedor_id)
        if not proveedor or proveedor.get("id") is None:
            raise NotFoundException(f"Proveedor {proveedor_id} no encontrado")
        return proveedor
    except NotFoundException:
        raise
    except Exception as e:
        raise NotFoundException(f"Proveedor {proveedor_id} no encontrado: {str(e)}")


@router.post("", response_model=ThirdPartyResponse, status_code=status.HTTP_201_CREATED)
async def create_proveedor(
    proveedor_data: ThirdPartyCreate,
    dolibarr: DolibarrClient = Depends(get_dolibarr_client),
    current_agent = Depends(require_write),
    _rate_limit = Depends(rate_limit_dependency),
    _idempotency = Depends(idempotency_dependency),
):
    """Crear nuevo proveedor. Forza supplier=1 y client=0."""
    # Forzar que sea proveedor
    proveedor_data.supplier = 1
    proveedor_data.client = 0
    
    # Validar código proveedor si se proporciona (Dolibarr requiere formato SU...)
    if proveedor_data.code_fournisseur and not proveedor_data.code_fournisseur.startswith("SU"):
        raise ValidationException(
            "El código de proveedor debe empezar con 'SU' (ej: SU2407-00001)"
        )
    
    # Dolibarr usa 'code_fournisseur' para proveedores
    data = proveedor_data.model_dump(exclude_none=True)
    if "code_fournisseur" in data:
        data["code_fournisseur"] = data.pop("code_fournisseur")
    
    proveedor = await dolibarr.create_supplier(data)
    return proveedor


@router.put("/{proveedor_id}", response_model=ThirdPartyResponse)
async def update_proveedor(
    proveedor_id: int,
    proveedor_data: ThirdPartyUpdate,
    dolibarr: DolibarrClient = Depends(get_dolibarr_client),
    current_agent = Depends(require_write),
    _rate_limit = Depends(rate_limit_dependency),
):
    """Actualizar proveedor."""
    proveedor_data.supplier = 1
    proveedor_data.client = 0
    
    proveedor = await dolibarr.update_supplier(
        proveedor_id,
        proveedor_data.model_dump(exclude_none=True, exclude_unset=True)
    )
    return proveedor


@router.delete("/{proveedor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_proveedor(
    proveedor_id: int,
    dolibarr: DolibarrClient = Depends(get_dolibarr_client),
    current_agent = Depends(require_write),
    _rate_limit = Depends(rate_limit_dependency),
):
    """Eliminar proveedor."""
    await dolibarr.delete_supplier(proveedor_id)
    return None


# =============================================================================
# FACTURAS PROVEEDOR (COMPRAS)
# =============================================================================

supplier_invoices_router = APIRouter(prefix="/facturas-proveedor", tags=["Facturas Proveedor"])


@supplier_invoices_router.get("", response_model=PaginatedResponse[SupplierInvoiceResponse])
async def list_supplier_invoices(
    pagination: PaginationParams = Depends(),
    status: Optional[int] = Query(default=None, ge=0, le=2),
    thirdparty_id: Optional[int] = None,
    dolibarr: DolibarrClient = Depends(get_dolibarr_client),
    current_agent = Depends(get_current_agent),
):
    """Listar facturas de proveedor."""
    invoices = await dolibarr.list_supplier_invoices(
        limit=pagination.limit,
        offset=pagination.offset,
        status=status,
        thirdparty_id=thirdparty_id,
    )
    
    return PaginatedResponse(
        success=True,
        data=invoices,
        total=len(invoices),
        limit=pagination.limit,
        offset=pagination.offset,
    )


@supplier_invoices_router.get("/{invoice_id}", response_model=SupplierInvoiceResponse)
async def get_supplier_invoice(
    invoice_id: int,
    dolibarr: DolibarrClient = Depends(get_dolibarr_client),
    current_agent = Depends(get_current_agent),
):
    """Obtener factura proveedor por ID."""
    try:
        invoice = await dolibarr.get_supplier_invoice(invoice_id)
        if not invoice or invoice.get("id") is None:
            raise NotFoundException(f"Factura proveedor {invoice_id} no encontrada")
        return invoice
    except NotFoundException:
        raise
    except Exception as e:
        raise NotFoundException(f"Factura proveedor {invoice_id} no encontrada: {str(e)}")


@supplier_invoices_router.post("", response_model=SupplierInvoiceResponse, status_code=status.HTTP_201_CREATED)
async def create_supplier_invoice(
    invoice_data: SupplierInvoiceCreate,
    dolibarr: DolibarrClient = Depends(get_dolibarr_client),
    current_agent = Depends(require_financial),
    _rate_limit = Depends(rate_limit_dependency),
    _idempotency = Depends(idempotency_dependency),
):
    """Crear factura de proveedor (compra)."""
    # Dolibarr usa 'socid' para el proveedor
    data = invoice_data.model_dump(exclude_none=True)
    
    invoice = await dolibarr.create_supplier_invoice(data)
    return invoice


@supplier_invoices_router.put("/{invoice_id}", response_model=SupplierInvoiceResponse)
async def update_supplier_invoice(
    invoice_id: int,
    invoice_data: SupplierInvoiceUpdate,
    dolibarr: DolibarrClient = Depends(get_dolibarr_client),
    current_agent = Depends(require_financial),
    _rate_limit = Depends(rate_limit_dependency),
):
    """Actualizar factura proveedor (solo en borrador)."""
    invoice = await dolibarr.update_supplier_invoice(
        invoice_id,
        invoice_data.model_dump(exclude_none=True, exclude_unset=True)
    )
    return invoice


@supplier_invoices_router.post("/{invoice_id}/validate", response_model=SupplierInvoiceResponse)
async def validate_supplier_invoice(
    invoice_id: int,
    dolibarr: DolibarrClient = Depends(get_dolibarr_client),
    current_agent = Depends(require_financial),
    _rate_limit = Depends(rate_limit_dependency),
):
    """Validar factura proveedor (pasar de borrador a validada)."""
    invoice = await dolibarr.validate_supplier_invoice(invoice_id)
    return invoice


@supplier_invoices_router.post("/{invoice_id}/cancel", response_model=SupplierInvoiceResponse)
async def cancel_supplier_invoice(
    invoice_id: int,
    dolibarr: DolibarrClient = Depends(get_dolibarr_client),
    current_agent = Depends(require_financial),
    _rate_limit = Depends(rate_limit_dependency),
):
    """Anular factura proveedor."""
    invoice = await dolibarr.cancel_supplier_invoice(invoice_id)
    return invoice


@supplier_invoices_router.post("/{invoice_id}/lines", response_model=dict)
async def add_supplier_invoice_line(
    invoice_id: int,
    line_data: dict,
    dolibarr: DolibarrClient = Depends(get_dolibarr_client),
    current_agent = Depends(require_financial),
    _rate_limit = Depends(rate_limit_dependency),
):
    """Añadir línea a factura proveedor."""
    # Validar campos requeridos
    required_fields = ["description", "pu_ht", "tva_tx", "qty"]
    for field in required_fields:
        if field not in line_data:
            raise ValidationException(f"Campo requerido: {field}")
    
    line = await dolibarr.add_supplier_invoice_line(invoice_id, line_data)
    return line


# =============================================================================
# PEDIDOS PROVEEDOR (ÓRDENES DE COMPRA)
# =============================================================================

supplier_orders_router = APIRouter(prefix="/pedidos-proveedor", tags=["Pedidos Proveedor"])


@supplier_orders_router.get("", response_model=PaginatedResponse[SupplierOrderResponse])
async def list_supplier_orders(
    pagination: PaginationParams = Depends(),
    status: Optional[int] = Query(default=None, ge=0, le=2),
    thirdparty_id: Optional[int] = None,
    dolibarr: DolibarrClient = Depends(get_dolibarr_client),
    current_agent = Depends(get_current_agent),
):
    """Listar pedidos de proveedor."""
    orders = await dolibarr.list_supplier_orders(
        limit=pagination.limit,
        offset=pagination.offset,
        status=status,
        thirdparty_id=thirdparty_id,
    )
    
    return PaginatedResponse(
        success=True,
        data=orders,
        total=len(orders),
        limit=pagination.limit,
        offset=pagination.offset,
    )


@supplier_orders_router.get("/{order_id}", response_model=SupplierOrderResponse)
async def get_supplier_order(
    order_id: int,
    dolibarr: DolibarrClient = Depends(get_dolibarr_client),
    current_agent = Depends(get_current_agent),
):
    """Obtener pedido proveedor por ID."""
    try:
        order = await dolibarr.get_supplier_order(order_id)
        if not order or order.get("id") is None:
            raise NotFoundException(f"Pedido proveedor {order_id} no encontrado")
        return order
    except NotFoundException:
        raise
    except Exception as e:
        raise NotFoundException(f"Pedido proveedor {order_id} no encontrado: {str(e)}")


@supplier_orders_router.post("", response_model=SupplierOrderResponse, status_code=status.HTTP_201_CREATED)
async def create_supplier_order(
    order_data: SupplierOrderCreate,
    dolibarr: DolibarrClient = Depends(get_dolibarr_client),
    current_agent = Depends(require_financial),
    _rate_limit = Depends(rate_limit_dependency),
    _idempotency = Depends(idempotency_dependency),
):
    """Crear pedido de proveedor (orden de compra)."""
    data = order_data.model_dump(exclude_none=True)
    
    order = await dolibarr.create_supplier_order(data)
    return order


@supplier_orders_router.put("/{order_id}", response_model=SupplierOrderResponse)
async def update_supplier_order(
    order_id: int,
    order_data: SupplierOrderUpdate,
    dolibarr: DolibarrClient = Depends(get_dolibarr_client),
    current_agent = Depends(require_financial),
    _rate_limit = Depends(rate_limit_dependency),
):
    """Actualizar pedido proveedor."""
    order = await dolibarr.update_supplier_order(
        order_id,
        order_data.model_dump(exclude_none=True, exclude_unset=True)
    )
    return order


@supplier_orders_router.post("/{order_id}/validate", response_model=SupplierOrderResponse)
async def validate_supplier_order(
    order_id: int,
    dolibarr: DolibarrClient = Depends(get_dolibarr_client),
    current_agent = Depends(require_financial),
    _rate_limit = Depends(rate_limit_dependency),
):
    """Validar pedido proveedor."""
    order = await dolibarr.validate_supplier_order(order_id)
    return order


@supplier_orders_router.post("/{order_id}/lines", response_model=dict)
async def add_supplier_order_line(
    order_id: int,
    line_data: dict,
    dolibarr: DolibarrClient = Depends(get_dolibarr_client),
    current_agent = Depends(require_financial),
    _rate_limit = Depends(rate_limit_dependency),
):
    """Añadir línea a pedido proveedor."""
    required_fields = ["description", "pu_ht", "tva_tx", "qty"]
    for field in required_fields:
        if field not in line_data:
            raise ValidationException(f"Campo requerido: {field}")
    
    line = await dolibarr.add_supplier_order_line(order_id, line_data)
    return line


# =============================================================================
# PROPUESTAS PROVEEDOR
# =============================================================================

supplier_proposals_router = APIRouter(prefix="/propuestas-proveedor", tags=["Propuestas Proveedor"])


@supplier_proposals_router.get("", response_model=PaginatedResponse[SupplierProposalResponse])
async def list_supplier_proposals(
    pagination: PaginationParams = Depends(),
    status: Optional[int] = Query(default=None, ge=0, le=2),
    thirdparty_id: Optional[int] = None,
    dolibarr: DolibarrClient = Depends(get_dolibarr_client),
    current_agent = Depends(get_current_agent),
):
    """Listar propuestas de proveedor."""
    proposals = await dolibarr.list_supplier_proposals(
        limit=pagination.limit,
        offset=pagination.offset,
        status=status,
        thirdparty_id=thirdparty_id,
    )
    
    return PaginatedResponse(
        success=True,
        data=proposals,
        total=len(proposals),
        limit=pagination.limit,
        offset=pagination.offset,
    )


@supplier_proposals_router.get("/{proposal_id}", response_model=SupplierProposalResponse)
async def get_supplier_proposal(
    proposal_id: int,
    dolibarr: DolibarrClient = Depends(get_dolibarr_client),
    current_agent = Depends(get_current_agent),
):
    """Obtener propuesta proveedor por ID."""
    try:
        proposal = await dolibarr.get_supplier_proposal(proposal_id)
        if not proposal or proposal.get("id") is None:
            raise NotFoundException(f"Propuesta proveedor {proposal_id} no encontrada")
        return proposal
    except NotFoundException:
        raise
    except Exception as e:
        raise NotFoundException(f"Propuesta proveedor {proposal_id} no encontrada: {str(e)}")


@supplier_proposals_router.post("", response_model=SupplierProposalResponse, status_code=status.HTTP_201_CREATED)
async def create_supplier_proposal(
    proposal_data: SupplierProposalCreate,
    dolibarr: DolibarrClient = Depends(get_dolibarr_client),
    current_agent = Depends(require_financial),
    _rate_limit = Depends(rate_limit_dependency),
    _idempotency = Depends(idempotency_dependency),
):
    """Crear propuesta de proveedor."""
    data = proposal_data.model_dump(exclude_none=True)
    
    proposal = await dolibarr.create_supplier_proposal(data)
    return proposal


@supplier_proposals_router.put("/{proposal_id}", response_model=SupplierProposalResponse)
async def update_supplier_proposal(
    proposal_id: int,
    proposal_data: SupplierProposalUpdate,
    dolibarr: DolibarrClient = Depends(get_dolibarr_client),
    current_agent = Depends(require_financial),
    _rate_limit = Depends(rate_limit_dependency),
):
    """Actualizar propuesta proveedor."""
    proposal = await dolibarr.update_supplier_proposal(
        proposal_id,
        proposal_data.model_dump(exclude_none=True, exclude_unset=True)
    )
    return proposal


@supplier_proposals_router.post("/{proposal_id}/convert-to-order", response_model=SupplierOrderResponse)
async def convert_supplier_proposal_to_order(
    proposal_id: int,
    dolibarr: DolibarrClient = Depends(get_dolibarr_client),
    current_agent = Depends(require_financial),
    _rate_limit = Depends(rate_limit_dependency),
):
    """Convertir propuesta proveedor a pedido."""
    order = await dolibarr.convert_supplier_proposal_to_order(proposal_id)
    return order


# Combinar todos los routers
router.include_router(supplier_invoices_router)
router.include_router(supplier_orders_router)
router.include_router(supplier_proposals_router)