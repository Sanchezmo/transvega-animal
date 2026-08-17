"""
Esquemas Pydantic para validación de datos de entrada/salida.
"""

import datetime
from typing import Any, Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

# =============================================================================
# ESQUEMAS BASE
# =============================================================================

T = TypeVar("T")


class BaseSchema(BaseModel):
    """Esquema base con configuración común."""

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
        "use_enum_values": True,
        # Note: json_encoders removed in Pydantic v2; handle serialization separately if needed.
    }


class PaginationParams(BaseModel):
    """Parámetros de paginación estándar."""

    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)

    @property
    def page(self) -> int:
        return (self.offset // self.limit) + 1


class PaginatedResponse(BaseModel, Generic[T]):
    """Respuesta paginada estándar."""

    success: bool = True
    data: list[T]
    total: int
    limit: int
    offset: int

    @property
    def has_more(self) -> bool:
        return self.offset + self.limit < self.total


# =============================================================================
# TERCEROS (CLIENTES/PROVEEDORES)
# =============================================================================


class ThirdPartyBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    name_alias: str | None = Field(None, max_length=200)
    email: str | None = Field(None, pattern=r"^[^@]+@[^@]+\.[^@]+$")
    phone: str | None = Field(None, max_length=50)
    address: str | None = Field(None, max_length=500)
    zip: str | None = Field(None, max_length=20)
    town: str | None = Field(None, max_length=100)
    country_id: int | None = None
    country_code: str | None = Field(None, pattern=r"^[A-Z]{2}$")
    state_id: int | None = None
    client: int = Field(default=1, ge=0, le=1)
    supplier: int = Field(default=0, ge=0, le=1)
    status: int = Field(default=1, ge=0, le=1)
    vat_number: str | None = Field(None, max_length=50)
    default_lang: str | None = Field(default="es_ES", pattern=r"^[a-z]{2}_[A-Z]{2}$")
    code_client: str | None = Field(
        None,
        max_length=24,
        description="Código cliente (requerido por Dolibarr para clientes)",
    )
    code_fournisseur: str | None = Field(
        None,
        max_length=24,
        description="Código proveedor (requerido por Dolibarr para proveedores, formato SU...)",
    )


class ThirdPartyCreate(ThirdPartyBase):
    pass


class ThirdPartyUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    name_alias: str | None = Field(None, max_length=200)
    email: str | None = Field(None, pattern=r"^[^@]+@[^@]+\.[^@]+$")
    phone: str | None = Field(None, max_length=50)
    address: str | None = Field(None, max_length=500)
    zip: str | None = Field(None, max_length=20)
    town: str | None = Field(None, max_length=100)
    country_id: int | None = None
    country_code: str | None = Field(None, pattern=r"^[A-Z]{2}$")
    state_id: int | None = None
    client: int | None = Field(None, ge=0, le=1)
    supplier: int | None = Field(None, ge=0, le=1)
    status: int | None = Field(None, ge=0, le=1)
    vat_number: str | None = Field(None, max_length=50)
    default_lang: str | None = Field(None, pattern=r"^[a-z]{2}_[A-Z]{2}$")
    code_client: str | None = Field(
        None,
        max_length=24,
        description="Código cliente (requerido por Dolibarr para clientes)",
    )


class ThirdPartyResponse(ThirdPartyBase):
    id: int
    ref: str
    ref_ext: str | None = None
    canvas: str | None = None
    datec: datetime.datetime | None = None
    datem: datetime.datetime | None = None
    fk_user_author: int | None = None
    fk_user_modif: int | None = None
    country_code: str | None = None


# =============================================================================
# PRODUCTOS/SERVICIOS
# =============================================================================


class ProductBase(BaseModel):
    ref: str = Field(..., min_length=1, max_length=50)
    label: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    price: float = Field(default=0.0, ge=0)
    price_ttc: float = Field(default=0.0, ge=0)
    tva_tx: float = Field(default=21.0, ge=0, le=100)
    prix_achat: float = Field(default=0.0, ge=0)
    poids: float = Field(default=0.0, ge=0)
    poids_unites: int = Field(default=1, ge=1)
    statut: int = Field(default=1, ge=0, le=1)
    type: int = Field(default=0, ge=0, le=2)  # renamed from 'product_type' to match Dolibarr field
    fk_product_type: int | None = None


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    ref: str | None = Field(None, min_length=1, max_length=50)
    label: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    price: float | None = Field(None, ge=0)
    price_ttc: float | None = Field(None, ge=0)
    tva_tx: float | None = Field(None, ge=0, le=100)
    prix_achat: float | None = Field(None, ge=0)
    poids: float | None = Field(None, ge=0)
    poids_unites: int | None = Field(None, ge=1)
    statut: int | None = Field(None, ge=0, le=1)
    type: int | None = Field(None, ge=0, le=2)  # renamed
    fk_product_type: int | None = None


class ProductResponse(ProductBase):
    id: int
    ref_ext: str | None = None
    datec: datetime.datetime
    datem: datetime.datetime


# =============================================================================
# EXPEDIENTES ANIMALES
# =============================================================================


class VaccineRecord(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    date: datetime.date
    batch: str | None = Field(None, max_length=50)
    vet: str | None = Field(None, max_length=100)
    next_due: datetime.date | None = None


class DewormingRecord(BaseModel):
    product: str = Field(..., min_length=1, max_length=100)
    date: datetime.date
    next_due: datetime.date | None = None
    vet: str | None = Field(None, max_length=100)


class CertificateRecord(BaseModel):
    cert_type: str = Field(..., max_length=50)  # renamed from 'type'
    date: datetime.date
    issuer: str | None = Field(None, max_length=100)
    document_url: str | None = None
    expires_at: datetime.date | None = None


class IncidentRecord(BaseModel):
    date: datetime.date
    incident_type: str = Field(..., max_length=50)  # renamed from 'type'
    description: str
    severity: str = Field(default="low", pattern=r"^(low|medium|high|critical)$")
    resolved: bool = False
    resolution_date: datetime.date | None = None
    resolution_notes: str | None = None


class PostSaleFollowupRecord(BaseModel):
    date: datetime.date
    followup_type: str = Field(..., max_length=50)  # renamed from 'type'
    notes: str
    next_action: str | None = None
    next_action_date: datetime.date | None = None


class ExpedienteAnimalBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=200)
    species: str = Field(default="perro", max_length=50)
    breed: str = Field(..., min_length=1, max_length=100)
    sex: str = Field(..., pattern=r"^[MH]$")
    birth_date: datetime.date
    color: str = Field(..., max_length=50)
    weight_kg: float = Field(..., gt=0, le=100)
    microchip: str | None = Field(None, pattern=r"^\d{15}$")
    breeder_id: int | None = None
    breeder_registration: str | None = Field(None, max_length=50)
    zoological_nucleus: str | None = Field(None, max_length=50)
    country_origin: str = Field(default="ES", pattern=r"^[A-Z]{2}$")
    place_origin: str | None = Field(None, max_length=100)
    sire_name: str | None = Field(None, max_length=200)
    dam_name: str | None = Field(None, max_length=200)
    pedigree: str | None = Field(None, max_length=100)
    vet_status: str = Field(default="healthy", max_length=50)
    vaccines: list[VaccineRecord] = Field(default_factory=list)
    deworming: list[DewormingRecord] = Field(default_factory=list)
    passport: str | None = Field(None, max_length=50)
    certificates: list[CertificateRecord] = Field(default_factory=list)
    photos: list[str] = Field(default_factory=list)
    videos: list[str] = Field(default_factory=list)
    purchase_price: float = Field(default=0.0, ge=0)
    sale_price: float = Field(default=0.0, ge=0)
    associated_costs: float = Field(default=0.0, ge=0)
    commercial_status: str = Field(
        default="draft",
        pattern=r"^(draft|pending_docs|pending_review|available|published|reserved|paid|preparing_transport|in_transport|delivered|post_sale|unavailable|archived)$",
    )
    client_id: int | None = None
    reservation_id: int | None = None
    order_id: int | None = None
    invoice_id: int | None = None
    transport_id: int | None = None
    expected_delivery_date: datetime.date | None = None
    actual_delivery_date: datetime.date | None = None
    incidents: list[IncidentRecord] = Field(default_factory=list)
    post_sale_followup: list[PostSaleFollowupRecord] = Field(default_factory=list)


class ExpedienteAnimalCreate(ExpedienteAnimalBase):
    pass


class ExpedienteAnimalUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    breed: str | None = Field(None, min_length=1, max_length=100)
    color: str | None = Field(None, max_length=50)
    weight_kg: float | None = Field(None, gt=0, le=100)
    microchip: str | None = Field(None, pattern=r"^\d{15}$")
    vet_status: str | None = Field(None, max_length=50)
    vaccines: list[VaccineRecord] | None = None
    deworming: list[DewormingRecord] | None = None
    certificates: list[CertificateRecord] | None = None
    photos: list[str] | None = None
    videos: list[str] | None = None
    sale_price: float | None = Field(None, ge=0)
    associated_costs: float | None = Field(None, ge=0)
    commercial_status: str | None = Field(
        None,
        pattern=r"^(draft|pending_docs|pending_review|available|published|reserved|paid|preparing_transport|in_transport|delivered|post_sale|unavailable|archived)$",
    )
    client_id: int | None = None
    expected_delivery_date: datetime.date | None = None
    actual_delivery_date: datetime.date | None = None


class ExpedienteAnimalResponse(ExpedienteAnimalBase):
    id: int
    internal_id: str
    created_at: datetime.datetime
    updated_at: datetime.datetime
    created_by: int = 1
    updated_by: int = 1


# =============================================================================
# FACTURAS
# =============================================================================


class InvoiceLineBase(BaseModel):
    product_id: int | None = None
    description: str = Field(..., min_length=1, max_length=500)
    qty: float = Field(default=1.0, gt=0)
    unit_price: float = Field(..., ge=0)
    vat_rate: float = Field(default=21.0, ge=0, le=100)
    discount_percent: float = Field(default=0.0, ge=0, le=100)


class InvoiceLineCreate(InvoiceLineBase):
    pass


class InvoiceLineResponse(InvoiceLineBase):
    id: int
    total_ht: float
    total_tva: float
    total_ttc: float


class InvoiceBase(BaseModel):
    thirdparty_id: int = Field(..., gt=0)
    date: datetime.date = Field(default_factory=datetime.date.today)
    lines: list[InvoiceLineCreate] = Field(..., min_length=1)
    payment_term_id: int | None = None
    cond_reglement_id: int | None = None
    mode_reglement_id: int | None = None
    note_private: str | None = None
    note_public: str | None = None


class InvoiceCreate(InvoiceBase):
    pass


class InvoiceUpdate(BaseModel):
    status: int | None = Field(None, ge=0, le=2)
    payment_term_id: int | None = None
    cond_reglement_id: int | None = None
    mode_reglement_id: int | None = None
    note_private: str | None = None
    note_public: str | None = None


class InvoiceResponse(InvoiceBase):
    id: int
    ref: str
    total_ht: float
    total_tva: float
    total_ttc: float
    lines: list[InvoiceLineResponse]
    datec: datetime.datetime
    datem: datetime.datetime
    fk_user_author: int = 1
    fk_user_modif: int = 1


# =============================================================================
# FACTURAS PROVEEDOR (COMPRAS)
# =============================================================================


class SupplierInvoiceLineBase(BaseModel):
    product_id: int | None = None
    description: str = Field(..., min_length=1, max_length=500)
    qty: float = Field(default=1.0, gt=0)
    unit_price: float = Field(..., ge=0)
    vat_rate: float = Field(default=21.0, ge=0, le=100)
    discount_percent: float = Field(default=0.0, ge=0, le=100)


class SupplierInvoiceLineCreate(SupplierInvoiceLineBase):
    pass


class SupplierInvoiceLineResponse(SupplierInvoiceLineBase):
    id: int
    total_ht: float
    total_tva: float
    total_ttc: float


class SupplierInvoiceBase(BaseModel):
    thirdparty_id: int = Field(..., gt=0, description="ID del proveedor (debe ser supplier=1)")
    date: datetime.date = Field(default_factory=datetime.date.today)
    lines: list[SupplierInvoiceLineCreate] = Field(..., min_length=1)
    payment_term_id: int | None = None
    cond_reglement_id: int | None = None
    mode_reglement_id: int | None = None
    note_private: str | None = None
    note_public: str | None = None
    ref_supplier: str | None = Field(None, max_length=50, description="Referencia del proveedor")


class SupplierInvoiceCreate(SupplierInvoiceBase):
    pass


class SupplierInvoiceUpdate(BaseModel):
    status: int | None = Field(None, ge=0, le=2)
    payment_term_id: int | None = None
    cond_reglement_id: int | None = None
    mode_reglement_id: int | None = None
    note_private: str | None = None
    note_public: str | None = None
    ref_supplier: str | None = Field(None, max_length=50)


class SupplierInvoiceResponse(SupplierInvoiceBase):
    id: int
    ref: str
    total_ht: float
    total_tva: float
    total_ttc: float
    lines: list[SupplierInvoiceLineResponse]
    datec: datetime.datetime
    datem: datetime.datetime
    fk_user_author: int = 1
    fk_user_modif: int = 1
    status: int = 0  # 0=draft, 1=validated, 2=cancelled


# =============================================================================
# PEDIDOS PROVEEDOR (ÓRDENES DE COMPRA)
# =============================================================================


class SupplierOrderLineBase(BaseModel):
    product_id: int | None = None
    description: str = Field(..., min_length=1, max_length=500)
    qty: float = Field(default=1.0, gt=0)
    unit_price: float = Field(..., ge=0)
    vat_rate: float = Field(default=21.0, ge=0, le=100)
    discount_percent: float = Field(default=0.0, ge=0, le=100)


class SupplierOrderLineCreate(SupplierOrderLineBase):
    pass


class SupplierOrderLineResponse(SupplierOrderLineBase):
    id: int
    total_ht: float
    total_tva: float
    total_ttc: float


class SupplierOrderBase(BaseModel):
    thirdparty_id: int = Field(..., gt=0, description="ID del proveedor (debe ser supplier=1)")
    date: datetime.date = Field(default_factory=datetime.date.today)
    lines: list[SupplierOrderLineCreate] = Field(..., min_length=1)
    payment_term_id: int | None = None
    cond_reglement_id: int | None = None
    mode_reglement_id: int | None = None
    note_private: str | None = None
    note_public: str | None = None
    ref_supplier: str | None = Field(None, max_length=50)


class SupplierOrderCreate(SupplierOrderBase):
    pass


class SupplierOrderUpdate(BaseModel):
    status: int | None = Field(None, ge=0, le=2)
    payment_term_id: int | None = None
    cond_reglement_id: int | None = None
    mode_reglement_id: int | None = None
    note_private: str | None = None
    note_public: str | None = None
    ref_supplier: str | None = Field(None, max_length=50)


class SupplierOrderResponse(SupplierOrderBase):
    id: int
    ref: str
    total_ht: float
    total_tva: float
    total_ttc: float
    lines: list[SupplierOrderLineResponse]
    datec: datetime.datetime
    datem: datetime.datetime
    fk_user_author: int = 1
    fk_user_modif: int = 1
    status: int = 0


# =============================================================================
# CATEGORÍAS DE GASTO (CATÁLOGO CONTROLADO)
# =============================================================================


class ExpenseCategoryBase(BaseModel):
    """Catálogo controlado de categorías de gasto para facturas de proveedor."""

    code: str = Field(..., min_length=1, max_length=50, pattern=r"^[a-z_]+$")
    label: str = Field(..., min_length=1, max_length=100)
    active: bool = True
    accounting_mapping: str | None = Field(None, max_length=50, description="Código de cuenta contable (opcional)")


class ExpenseCategoryCreate(ExpenseCategoryBase):
    pass


class ExpenseCategoryUpdate(BaseModel):
    label: str | None = Field(None, min_length=1, max_length=100)
    active: bool | None = None
    accounting_mapping: str | None = Field(None, max_length=50)


class ExpenseCategoryResponse(ExpenseCategoryBase):
    id: int
    created_at: datetime.datetime
    updated_at: datetime.datetime


# Default expense categories (V1)
DEFAULT_EXPENSE_CATEGORIES: list[dict[str, Any]] = [
    {"code": "veterinary", "label": "Veterinario", "active": True, "accounting_mapping": "6280"},
    {"code": "feed", "label": "Alimentación (Pienso)", "active": True, "accounting_mapping": "6281"},
    {"code": "fuel", "label": "Combustible", "active": True, "accounting_mapping": "6240"},
    {"code": "transport", "label": "Transporte", "active": True, "accounting_mapping": "6241"},
    {"code": "advertising", "label": "Publicidad", "active": True, "accounting_mapping": "6270"},
    {"code": "training", "label": "Formación", "active": True, "accounting_mapping": "6230"},
    {"code": "office", "label": "Material de oficina", "active": True, "accounting_mapping": "6260"},
    {"code": "professional_services", "label": "Servicios profesionales", "active": True, "accounting_mapping": "6231"},
    {"code": "utilities", "label": "Suministros (Luz, Agua, Gas)", "active": True, "accounting_mapping": "6250"},
    {"code": "pet_supplies", "label": "Artículos para mascotas", "active": True, "accounting_mapping": "6282"},
    {"code": "insurance", "label": "Seguros", "active": True, "accounting_mapping": "6290"},
    {"code": "rent", "label": "Alquileres", "active": True, "accounting_mapping": "6210"},
    {"code": "taxes_fees", "label": "Tasas e impuestos", "active": True, "accounting_mapping": "6350"},
    {"code": "other", "label": "Otros", "active": True, "accounting_mapping": "6299"},
]


# =============================================================================
# PROPUESTAS PROVEEDOR
# =============================================================================


class SupplierProposalBase(BaseModel):
    thirdparty_id: int = Field(..., gt=0)
    date: datetime.date = Field(default_factory=datetime.date.today)
    lines: list[SupplierOrderLineCreate] = Field(..., min_length=1)
    payment_term_id: int | None = None
    cond_reglement_id: int | None = None
    note_private: str | None = None
    note_public: str | None = None
    ref_supplier: str | None = Field(None, max_length=50)


class SupplierProposalCreate(SupplierProposalBase):
    pass


class SupplierProposalUpdate(BaseModel):
    status: int | None = Field(None, ge=0, le=2)
    note_private: str | None = None
    note_public: str | None = None
    ref_supplier: str | None = Field(None, max_length=50)


class SupplierProposalResponse(SupplierProposalBase):
    id: int
    ref: str
    total_ht: float
    total_tva: float
    total_ttc: float
    lines: list[SupplierOrderLineResponse]
    datec: datetime.datetime
    datem: datetime.datetime
    fk_user_author: int = 1
    fk_user_modif: int = 1
    status: int = 0


# =============================================================================
# PUBLICACIONES/ANUNCIOS
# =============================================================================


class PublicationBase(BaseModel):
    expediente_id: int = Field(..., gt=0)
    platform: str = Field(..., max_length=50)  # milanuncios, facebook, instagram, tiktok, web, etc.
    title: str = Field(..., min_length=5, max_length=200)
    description: str = Field(..., min_length=20)
    photos: list[str] = Field(default_factory=list)
    price: float | None = Field(None, ge=0)
    external_id: str | None = Field(None, max_length=100)
    external_url: str | None = None


class PublicationCreate(PublicationBase):
    pass


class PublicationUpdate(BaseModel):
    expediente_id: int | None = Field(None, gt=0)
    platform: str | None = Field(None, max_length=50)
    title: str | None = Field(None, min_length=5, max_length=200)
    description: str | None = Field(None, min_length=20)
    photos: list[str] | None = None
    price: float | None = Field(None, ge=0)
    external_id: str | None = Field(None, max_length=100)
    external_url: str | None = None


class PublicationResponse(PublicationBase):
    id: int
    status: str = Field(
        default="draft",
        pattern=r"^(draft|pending_approval|approved|published|expired|removed|failed)$",
    )
    published_at: datetime.datetime | None = None
    expires_at: datetime.datetime | None = None
    created_at: datetime.datetime
    updated_at: datetime.datetime
    approval_id: UUID | None = None

    @field_validator("photos", mode="before")
    @classmethod
    def _parse_photos(cls, v):
        if isinstance(v, str):
            import json

            try:
                return json.loads(v)
            except (json.JSONDecodeError, TypeError):
                return []
        if v is None:
            return []
        return v


# =============================================================================
# COMERCIAL / LEADS
# =============================================================================


class LeadBase(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., pattern=r"^[^@]+@[^@]+\.[^@]+$")
    phone: str = Field(..., min_length=5, max_length=50)
    country: str = Field(..., pattern=r"^[A-Z]{2}$")
    city: str | None = Field(None, max_length=100)
    language: str = Field(default="es", pattern=r"^[a-z]{2}$")
    source: str = Field(..., max_length=50)
    source_campaign: str | None = Field(None, max_length=100)
    source_keyword: str | None = Field(None, max_length=100)
    utm_params: dict[str, str] | None = None


class LeadCreate(LeadBase):
    pass


class LeadUpdate(BaseModel):
    status: str | None = Field(
        None,
        pattern=r"^(new|contacted|qualified|proposal_sent|negotiation|won|lost|nurturing)$",
    )
    interested_expediente_ids: list[int] | None = None
    budget_min: float | None = Field(None, ge=0)
    budget_max: float | None = Field(None, ge=0)
    timeline: str | None = Field(None, max_length=50)
    housing_type: str | None = Field(None, max_length=50)
    hours_alone: int | None = Field(None, ge=0, le=24)
    has_children: bool | None = None
    children_ages: list[int] | None = None
    has_dogs: bool | None = None
    current_dogs: list[str] | None = None
    has_cats: bool | None = None
    experience_level: str | None = Field(None, max_length=50)
    show_experience: bool | None = None


class LeadResponse(LeadBase):
    id: int
    status: str = "new"
    score: int = 0
    temperature: str = "cold"
    assigned_closer_id: int | None = None
    last_contact: datetime.datetime | None = None
    next_action: str | None = None
    next_action_due: datetime.datetime | None = None
    created_at: datetime.datetime
    updated_at: datetime.datetime


# =============================================================================
# APROBACIONES
# =============================================================================


class ApprovalRequestBase(BaseModel):
    action: str = Field(..., max_length=100)
    resource_type: str = Field(..., max_length=50)
    resource_id: str = Field(..., max_length=100)
    reason: str = Field(..., min_length=10)
    current_state: dict[str, Any] = Field(default_factory=dict)
    proposed_state: dict[str, Any] = Field(default_factory=dict)
    risks: str | None = None
    evidence: list[str] | None = None
    expires_at: datetime.datetime | None = None


class ApprovalRequestCreate(ApprovalRequestBase):
    pass


class ApprovalDecision(BaseModel):
    approved: bool
    comment: str | None = Field(None, max_length=1000)


class ApprovalResponse(ApprovalRequestBase):
    id: UUID
    status: str = Field(default="pending", pattern=r"^(pending|approved|rejected|expired|cancelled)$")
    requested_by: str
    requested_at: datetime.datetime
    reviewed_by: str | None = None
    reviewed_at: datetime.datetime | None = None
    review_comment: str | None = None


# =============================================================================
# TAREAS / COLA
# =============================================================================


class TaskBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    priority: str = Field(default="medium", pattern=r"^(low|medium|high)$")
    status: str = Field(default="pending", pattern=r"^(pending|in_progress|completed|failed)$")
    assigned_to: int | None = None
    due_date: datetime.date | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    priority: str | None = Field(None, pattern=r"^(low|medium|high)$")
    status: str | None = Field(None, pattern=r"^(pending|in_progress|completed|failed)$")
    assigned_to: int | None = None
    due_date: datetime.date | None = None
    metadata: dict[str, Any] | None = None


class TaskResponse(TaskBase):
    id: int
    created_at: datetime.datetime
    updated_at: datetime.datetime
    created_by: int = 1
    updated_by: int = 1


# =============================================================================
# PERROS (DOGS) - NUEVOS MODELOS DE DOMINIO
# =============================================================================


class BreedBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    average_weight_kg: float | None = Field(None, gt=0)
    average_height_cm: float | None = Field(None, gt=0)
    life_expectancy_years: int | None = Field(None, gt=0)
    temperament: str | None = None
    good_with_children: bool | None = None
    good_with_other_dogs: bool | None = None
    energy_level: str | None = Field(None, pattern=r"^(low|medium|high)$")
    grooming_needs: str | None = Field(None, pattern=r"^(low|medium|high)$")


class BreedCreate(BreedBase):
    pass


class BreedUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    average_weight_kg: float | None = Field(None, gt=0)
    average_height_cm: float | None = Field(None, gt=0)
    life_expectancy_years: int | None = Field(None, gt=0)
    temperament: str | None = None
    good_with_children: bool | None = None
    good_with_other_dogs: bool | None = None
    energy_level: str | None = Field(None, pattern=r"^(low|medium|high)$")
    grooming_needs: str | None = Field(None, pattern=r"^(low|medium|high)$")


class BreedResponse(BreedBase):
    id: int
    created_at: datetime.datetime
    updated_at: datetime.datetime


class LitterBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    breed_id: int = Field(..., gt=0)
    mother_id: int = Field(..., gt=0)
    father_id: int | None = Field(None, gt=0)
    birth_date: datetime.date
    size: int = Field(..., gt=0)
    registration_number: str | None = Field(None, max_length=50)


class LitterCreate(LitterBase):
    pass


class LitterUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    breed_id: int | None = Field(None, gt=0)
    mother_id: int | None = Field(None, gt=0)
    father_id: int | None = Field(None, gt=0)
    birth_date: datetime.date | None = None
    size: int | None = Field(None, gt=0)
    registration_number: str | None = Field(None, max_length=50)


class LitterResponse(LitterBase):
    id: int
    created_at: datetime.datetime
    updated_at: datetime.datetime


class DogMediaBase(BaseModel):
    file_path: str = Field(..., max_length=500)
    file_hash: str = Field(..., min_length=32, max_length=128)  # SHA-256 or similar
    mime_type: str = Field(..., max_length=100)
    width: int | None = Field(None, gt=0)
    height: int | None = Field(None, gt=0)
    duration_seconds: float | None = Field(None, gt=0)  # for videos
    media_type: str = Field(..., pattern=r"^(photo|video)$")
    purpose: str = Field(..., pattern=r"^(original|processed|social|listing)$")
    dog_id: int = Field(..., gt=0)
    uploaded_by: int = Field(..., gt=0)


class DogMediaCreate(DogMediaBase):
    pass


class DogMediaUpdate(BaseModel):
    file_path: str | None = Field(None, max_length=500)
    file_hash: str | None = Field(None, min_length=32, max_length=128)
    mime_type: str | None = Field(None, max_length=100)
    width: int | None = Field(None, gt=0)
    height: int | None = Field(None, gt=0)
    duration_seconds: float | None = Field(None, gt=0)
    media_type: str | None = Field(None, pattern=r"^(photo|video)$")
    purpose: str | None = Field(None, pattern=r"^(original|processed|social|listing)$")
    dog_id: int | None = Field(None, gt=0)
    uploaded_by: int | None = Field(None, gt=0)


class DogMediaResponse(DogMediaBase):
    id: int
    created_at: datetime.datetime


class DogHealthBase(BaseModel):
    vet_check_date: datetime.date | None = None
    weight_kg: float | None = Field(None, gt=0)
    temperature_celsius: float | None = Field(None, ge=35, le=42)
    heart_rate_bpm: int | None = Field(None, gt=0)
    respiratory_rate: int | None = Field(None, gt=0)
    stool_condition: str | None = Field(None, pattern=r"^(normal|soft|diarrhea|constipated)$")
    urine_condition: str | None = Field(None, pattern=r"^(normal|cloudy|bloody)$")
    appetite: str | None = Field(None, pattern=r"^(poor|fair|good|excellent)$")
    energy_level: str | None = Field(None, pattern=r"^(low|medium|high)$")
    notes: str | None = None
    next_check_date: datetime.date | None = None


class DogHealthCreate(DogHealthBase):
    pass


class DogHealthUpdate(BaseModel):
    vet_check_date: datetime.date | None = None
    weight_kg: float | None = Field(None, gt=0)
    temperature_celsius: float | None = Field(None, ge=35, le=42)
    heart_rate_bpm: int | None = Field(None, gt=0)
    respiratory_rate: int | None = Field(None, gt=0)
    stool_condition: str | None = Field(None, pattern=r"^(normal|soft|diarrhea|constipated)$")
    urine_condition: str | None = Field(None, pattern=r"^(normal|cloudy|bloody)$")
    appetite: str | None = Field(None, pattern=r"^(poor|fair|good|excellent)$")
    energy_level: str | None = Field(None, pattern=r"^(low|medium|high)$")
    notes: str | None = None
    next_check_date: datetime.date | None = None


class DogHealthResponse(DogHealthBase):
    id: int
    dog_id: int = Field(..., gt=0)
    recorded_at: datetime.datetime


class DogStatusHistoryBase(BaseModel):
    status: str = Field(..., pattern=r"^(draft|available|reserved|sold|inactive)$")
    changed_by: int = Field(..., gt=0)
    change_reason: str | None = None


class DogStatusHistoryCreate(DogStatusHistoryBase):
    pass


class DogStatusHistoryResponse(DogStatusHistoryBase):
    id: int
    dog_id: int = Field(..., gt=0)
    changed_at: datetime.datetime


# =============================================================================
# PERRO PRINCIPAL (DOG)
# =============================================================================


class DogBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    breed_id: int = Field(..., gt=0)
    litter_id: int | None = Field(None, gt=0)
    sex: str = Field(..., pattern=r"^[MH]$")
    birth_date: datetime.date
    color: str = Field(..., max_length=50)
    microchip: str | None = Field(None, pattern=r"^\d{15}$")
    sire_name: str | None = Field(None, max_length=200)  # father name
    dam_name: str | None = Field(None, max_length=200)  # mother name
    pedigree: str | None = Field(None, max_length=100)
    vet_status: str = Field(default="healthy", max_length=50)
    purchase_price: float = Field(default=0.0, ge=0)
    sale_price: float = Field(default=0.0, ge=0)
    associated_costs: float = Field(default=0.0, ge=0)
    # Reference to ExpedienteAnimal for Dolibarr sync (optional)
    expediente_id: int | None = Field(None, gt=0)


class DogCreate(DogBase):
    pass


class DogUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    breed_id: int | None = Field(None, gt=0)
    litter_id: int | None = Field(None, gt=0)
    sex: str | None = Field(None, pattern=r"^[MH]$")
    birth_date: datetime.date | None = None
    color: str | None = Field(None, max_length=50)
    microchip: str | None = Field(None, pattern=r"^\d{15}$")
    vet_status: str | None = Field(None, max_length=50)
    sire_name: str | None = Field(None, max_length=200)
    dam_name: str | None = Field(None, max_length=200)
    pedigree: str | None = Field(None, max_length=100)
    purchase_price: float | None = Field(None, ge=0)
    sale_price: float | None = Field(None, ge=0)
    associated_costs: float | None = Field(None, ge=0)
    expediente_id: int | None = Field(None, gt=0)


class DogResponse(DogBase):
    id: int
    internal_id: str = Field(..., max_length=50)  # e.g., DOG-2026-000001
    created_at: datetime.datetime
    updated_at: datetime.datetime
    created_by: int = 1
    updated_by: int = 1
    # Computed or related fields (optional, for API responses)
    breed: BreedResponse | None = None
    litter: LitterResponse | None = None
    media: list[DogMediaResponse] = Field(default_factory=list)
    health_records: list[DogHealthResponse] = Field(default_factory=list)
    status_history: list[DogStatusHistoryResponse] = Field(default_factory=list)
