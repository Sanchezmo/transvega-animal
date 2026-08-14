"""
Esquemas Pydantic para validación de datos de entrada/salida.
"""
from pydantic import BaseModel, Field, validator, field_validator
from typing import Optional, List, Dict, Any, TypeVar, Generic
import datetime
from uuid import UUID


# =============================================================================
# ESQUEMAS BASE
# =============================================================================

T = TypeVar('T')


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
    data: List[T]
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
    name_alias: Optional[str] = Field(None, max_length=200)
    email: Optional[str] = Field(None, pattern=r"^[^@]+@[^@]+\.[^@]+$")
    phone: Optional[str] = Field(None, max_length=50)
    address: Optional[str] = Field(None, max_length=500)
    zip: Optional[str] = Field(None, max_length=20)
    town: Optional[str] = Field(None, max_length=100)
    country_id: Optional[int] = None
    country_code: Optional[str] = Field(None, pattern=r"^[A-Z]{2}$")
    state_id: Optional[int] = None
    client: int = Field(default=1, ge=0, le=1)
    supplier: int = Field(default=0, ge=0, le=1)
    status: int = Field(default=1, ge=0, le=1)
    vat_number: Optional[str] = Field(None, max_length=50)
    default_lang: Optional[str] = Field(default="es_ES", pattern=r"^[a-z]{2}_[A-Z]{2}$")
    code_client: Optional[str] = Field(None, max_length=24, description="Código cliente (requerido por Dolibarr para clientes)")
    code_fournisseur: Optional[str] = Field(None, max_length=24, description="Código proveedor (requerido por Dolibarr para proveedores, formato SU...)")


class ThirdPartyCreate(ThirdPartyBase):
    pass


class ThirdPartyUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    name_alias: Optional[str] = Field(None, max_length=200)
    email: Optional[str] = Field(None, pattern=r"^[^@]+@[^@]+\.[^@]+$")
    phone: Optional[str] = Field(None, max_length=50)
    address: Optional[str] = Field(None, max_length=500)
    zip: Optional[str] = Field(None, max_length=20)
    town: Optional[str] = Field(None, max_length=100)
    country_id: Optional[int] = None
    country_code: Optional[str] = Field(None, pattern=r"^[A-Z]{2}$")
    state_id: Optional[int] = None
    client: Optional[int] = Field(None, ge=0, le=1)
    supplier: Optional[int] = Field(None, ge=0, le=1)
    status: Optional[int] = Field(None, ge=0, le=1)
    vat_number: Optional[str] = Field(None, max_length=50)
    default_lang: Optional[str] = Field(None, pattern=r"^[a-z]{2}_[A-Z]{2}$")
    code_client: Optional[str] = Field(None, max_length=24, description="Código cliente (requerido por Dolibarr para clientes)")


class ThirdPartyResponse(ThirdPartyBase):
    id: int
    ref: str
    ref_ext: Optional[str] = None
    canvas: Optional[str] = None
    datec: Optional[datetime.datetime] = None
    datem: Optional[datetime.datetime] = None
    fk_user_author: Optional[int] = None
    fk_user_modif: Optional[int] = None
    country_code: Optional[str] = None


# =============================================================================
# PRODUCTOS/SERVICIOS
# =============================================================================

class ProductBase(BaseModel):
    ref: str = Field(..., min_length=1, max_length=50)
    label: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    price: float = Field(default=0.0, ge=0)
    price_ttc: float = Field(default=0.0, ge=0)
    tva_tx: float = Field(default=21.0, ge=0, le=100)
    prix_achat: float = Field(default=0.0, ge=0)
    poids: float = Field(default=0.0, ge=0)
    poids_unites: int = Field(default=1, ge=1)
    statut: int = Field(default=1, ge=0, le=1)
    type: int = Field(default=0, ge=0, le=2)  # renamed from 'product_type' to match Dolibarr field
    fk_product_type: Optional[int] = None


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    ref: Optional[str] = Field(None, min_length=1, max_length=50)
    label: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    price: Optional[float] = Field(None, ge=0)
    price_ttc: Optional[float] = Field(None, ge=0)
    tva_tx: Optional[float] = Field(None, ge=0, le=100)
    prix_achat: Optional[float] = Field(None, ge=0)
    poids: Optional[float] = Field(None, ge=0)
    poids_unites: Optional[int] = Field(None, ge=1)
    statut: Optional[int] = Field(None, ge=0, le=1)
    type: Optional[int] = Field(None, ge=0, le=2)  # renamed
    fk_product_type: Optional[int] = None


class ProductResponse(ProductBase):
    id: int
    ref_ext: Optional[str] = None
    datec: datetime.datetime
    datem: datetime.datetime


# =============================================================================
# EXPEDIENTES ANIMALES
# =============================================================================

class VaccineRecord(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    date: datetime.date
    batch: Optional[str] = Field(None, max_length=50)
    vet: Optional[str] = Field(None, max_length=100)
    next_due: Optional[datetime.date] = None


class DewormingRecord(BaseModel):
    product: str = Field(..., min_length=1, max_length=100)
    date: datetime.date
    next_due: Optional[datetime.date] = None
    vet: Optional[str] = Field(None, max_length=100)


class CertificateRecord(BaseModel):
    cert_type: str = Field(..., max_length=50)  # renamed from 'type'
    date: datetime.date
    issuer: Optional[str] = Field(None, max_length=100)
    document_url: Optional[str] = None
    expires_at: Optional[datetime.date] = None


class IncidentRecord(BaseModel):
    date: datetime.date
    incident_type: str = Field(..., max_length=50)  # renamed from 'type'
    description: str
    severity: str = Field(default="low", pattern=r"^(low|medium|high|critical)$")
    resolved: bool = False
    resolution_date: Optional[datetime.date] = None
    resolution_notes: Optional[str] = None


class PostSaleFollowupRecord(BaseModel):
    date: datetime.date
    followup_type: str = Field(..., max_length=50)  # renamed from 'type'
    notes: str
    next_action: Optional[str] = None
    next_action_date: Optional[datetime.date] = None


class ExpedienteAnimalBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    species: str = Field(default="perro", max_length=50)
    breed: str = Field(..., min_length=1, max_length=100)
    sex: str = Field(..., pattern=r"^[MH]$")
    birth_date: datetime.date
    color: str = Field(..., max_length=50)
    weight_kg: float = Field(..., gt=0, le=100)
    microchip: str = Field(..., pattern=r"^\d{15}$")
    breeder_id: Optional[int] = None
    breeder_registration: Optional[str] = Field(None, max_length=50)
    zoological_nucleus: Optional[str] = Field(None, max_length=50)
    country_origin: str = Field(default="ES", pattern=r"^[A-Z]{2}$")
    place_origin: Optional[str] = Field(None, max_length=100)
    sire_name: Optional[str] = Field(None, max_length=200)
    dam_name: Optional[str] = Field(None, max_length=200)
    pedigree: Optional[str] = Field(None, max_length=100)
    vet_status: str = Field(default="healthy", max_length=50)
    vaccines: List[VaccineRecord] = Field(default_factory=list)
    deworming: List[DewormingRecord] = Field(default_factory=list)
    passport: Optional[str] = Field(None, max_length=50)
    certificates: List[CertificateRecord] = Field(default_factory=list)
    photos: List[str] = Field(default_factory=list)
    videos: List[str] = Field(default_factory=list)
    purchase_price: float = Field(default=0.0, ge=0)
    sale_price: float = Field(default=0.0, ge=0)
    associated_costs: float = Field(default=0.0, ge=0)
    commercial_status: str = Field(
        default="draft",
        pattern=r"^(draft|pending_docs|pending_review|available|published|reserved|paid|preparing_transport|in_transport|delivered|post_sale|unavailable|archived)$",
    )
    client_id: Optional[int] = None
    reservation_id: Optional[int] = None
    order_id: Optional[int] = None
    invoice_id: Optional[int] = None
    transport_id: Optional[int] = None
    expected_delivery_date: Optional[datetime.date] = None
    actual_delivery_date: Optional[datetime.date] = None
    incidents: List[IncidentRecord] = Field(default_factory=list)
    post_sale_followup: List[PostSaleFollowupRecord] = Field(default_factory=list)


class ExpedienteAnimalCreate(ExpedienteAnimalBase):
    pass


class ExpedienteAnimalUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    breed: Optional[str] = Field(None, min_length=1, max_length=100)
    color: Optional[str] = Field(None, max_length=50)
    weight_kg: Optional[float] = Field(None, gt=0, le=100)
    vet_status: Optional[str] = Field(None, max_length=50)
    vaccines: Optional[List[VaccineRecord]] = None
    deworming: Optional[List[DewormingRecord]] = None
    certificates: Optional[List[CertificateRecord]] = None
    photos: Optional[List[str]] = None
    videos: Optional[List[str]] = None
    sale_price: Optional[float] = Field(None, ge=0)
    associated_costs: Optional[float] = Field(None, ge=0)
    commercial_status: Optional[str] = Field(
        None,
        pattern=r"^(draft|pending_docs|pending_review|available|published|reserved|paid|preparing_transport|in_transport|delivered|post_sale|unavailable|archived)$",
    )
    client_id: Optional[int] = None
    expected_delivery_date: Optional[datetime.date] = None
    actual_delivery_date: Optional[datetime.date] = None


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
    product_id: Optional[int] = None
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
    lines: List[InvoiceLineCreate] = Field(..., min_length=1)
    payment_term_id: Optional[int] = None
    cond_reglement_id: Optional[int] = None
    mode_reglement_id: Optional[int] = None
    note_private: Optional[str] = None
    note_public: Optional[str] = None


class InvoiceCreate(InvoiceBase):
    pass


class InvoiceUpdate(BaseModel):
    status: Optional[int] = Field(None, ge=0, le=2)
    payment_term_id: Optional[int] = None
    cond_reglement_id: Optional[int] = None
    mode_reglement_id: Optional[int] = None
    note_private: Optional[str] = None
    note_public: Optional[str] = None


class InvoiceResponse(InvoiceBase):
    id: int
    ref: str
    total_ht: float
    total_tva: float
    total_ttc: float
    lines: List[InvoiceLineResponse]
    datec: datetime.datetime
    datem: datetime.datetime
    fk_user_author: int = 1
    fk_user_modif: int = 1


# =============================================================================
# FACTURAS PROVEEDOR (COMPRAS)
# =============================================================================

class SupplierInvoiceLineBase(BaseModel):
    product_id: Optional[int] = None
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
    lines: List[SupplierInvoiceLineCreate] = Field(..., min_length=1)
    payment_term_id: Optional[int] = None
    cond_reglement_id: Optional[int] = None
    mode_reglement_id: Optional[int] = None
    note_private: Optional[str] = None
    note_public: Optional[str] = None
    ref_supplier: Optional[str] = Field(None, max_length=50, description="Referencia del proveedor")


class SupplierInvoiceCreate(SupplierInvoiceBase):
    pass


class SupplierInvoiceUpdate(BaseModel):
    status: Optional[int] = Field(None, ge=0, le=2)
    payment_term_id: Optional[int] = None
    cond_reglement_id: Optional[int] = None
    mode_reglement_id: Optional[int] = None
    note_private: Optional[str] = None
    note_public: Optional[str] = None
    ref_supplier: Optional[str] = Field(None, max_length=50)


class SupplierInvoiceResponse(SupplierInvoiceBase):
    id: int
    ref: str
    total_ht: float
    total_tva: float
    total_ttc: float
    lines: List[SupplierInvoiceLineResponse]
    datec: datetime.datetime
    datem: datetime.datetime
    fk_user_author: int = 1
    fk_user_modif: int = 1
    status: int = 0  # 0=draft, 1=validated, 2=cancelled


# =============================================================================
# PEDIDOS PROVEEDOR (ÓRDENES DE COMPRA)
# =============================================================================

class SupplierOrderLineBase(BaseModel):
    product_id: Optional[int] = None
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
    lines: List[SupplierOrderLineCreate] = Field(..., min_length=1)
    payment_term_id: Optional[int] = None
    cond_reglement_id: Optional[int] = None
    mode_reglement_id: Optional[int] = None
    note_private: Optional[str] = None
    note_public: Optional[str] = None
    ref_supplier: Optional[str] = Field(None, max_length=50)


class SupplierOrderCreate(SupplierOrderBase):
    pass


class SupplierOrderUpdate(BaseModel):
    status: Optional[int] = Field(None, ge=0, le=2)
    payment_term_id: Optional[int] = None
    cond_reglement_id: Optional[int] = None
    mode_reglement_id: Optional[int] = None
    note_private: Optional[str] = None
    note_public: Optional[str] = None
    ref_supplier: Optional[str] = Field(None, max_length=50)


class SupplierOrderResponse(SupplierOrderBase):
    id: int
    ref: str
    total_ht: float
    total_tva: float
    total_ttc: float
    lines: List[SupplierOrderLineResponse]
    datec: datetime.datetime
    datem: datetime.datetime
    fk_user_author: int = 1
    fk_user_modif: int = 1
    status: int = 0


# =============================================================================
# PROPUESTAS PROVEEDOR
# =============================================================================

class SupplierProposalBase(BaseModel):
    thirdparty_id: int = Field(..., gt=0)
    date: datetime.date = Field(default_factory=datetime.date.today)
    lines: List[SupplierOrderLineCreate] = Field(..., min_length=1)
    payment_term_id: Optional[int] = None
    cond_reglement_id: Optional[int] = None
    note_private: Optional[str] = None
    note_public: Optional[str] = None
    ref_supplier: Optional[str] = Field(None, max_length=50)


class SupplierProposalCreate(SupplierProposalBase):
    pass


class SupplierProposalUpdate(BaseModel):
    status: Optional[int] = Field(None, ge=0, le=2)
    note_private: Optional[str] = None
    note_public: Optional[str] = None
    ref_supplier: Optional[str] = Field(None, max_length=50)


class SupplierProposalResponse(SupplierProposalBase):
    id: int
    ref: str
    total_ht: float
    total_tva: float
    total_ttc: float
    lines: List[SupplierOrderLineResponse]
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
    photos: List[str] = Field(default_factory=list)
    price: Optional[float] = Field(None, ge=0)
    external_id: Optional[str] = Field(None, max_length=100)
    external_url: Optional[str] = None


class PublicationCreate(PublicationBase):
    pass

class PublicationUpdate(BaseModel):
    expediente_id: Optional[int] = Field(None, gt=0)
    platform: Optional[str] = Field(None, max_length=50)
    title: Optional[str] = Field(None, min_length=5, max_length=200)
    description: Optional[str] = Field(None, min_length=20)
    photos: Optional[List[str]] = None
    price: Optional[float] = Field(None, ge=0)
    external_id: Optional[str] = Field(None, max_length=100)
    external_url: Optional[str] = None



class PublicationResponse(PublicationBase):
    id: int
    status: str = Field(default="draft", pattern=r"^(draft|pending_approval|approved|published|expired|removed|failed)$")
    published_at: Optional[datetime.datetime] = None
    expires_at: Optional[datetime.datetime] = None
    created_at: datetime.datetime
    updated_at: datetime.datetime
    approval_id: Optional[UUID] = None

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
    city: Optional[str] = Field(None, max_length=100)
    language: str = Field(default="es", pattern=r"^[a-z]{2}$")
    source: str = Field(..., max_length=50)
    source_campaign: Optional[str] = Field(None, max_length=100)
    source_keyword: Optional[str] = Field(None, max_length=100)
    utm_params: Optional[Dict[str, str]] = None


class LeadCreate(LeadBase):
    pass


class LeadUpdate(BaseModel):
    status: Optional[str] = Field(None, pattern=r"^(new|contacted|qualified|proposal_sent|negotiation|won|lost|nurturing)$")
    interested_expediente_ids: Optional[List[int]] = None
    budget_min: Optional[float] = Field(None, ge=0)
    budget_max: Optional[float] = Field(None, ge=0)
    timeline: Optional[str] = Field(None, max_length=50)
    housing_type: Optional[str] = Field(None, max_length=50)
    hours_alone: Optional[int] = Field(None, ge=0, le=24)
    has_children: Optional[bool] = None
    children_ages: Optional[List[int]] = None
    has_dogs: Optional[bool] = None
    current_dogs: Optional[List[str]] = None
    has_cats: Optional[bool] = None
    experience_level: Optional[str] = Field(None, max_length=50)
    show_experience: Optional[bool] = None


class LeadResponse(LeadBase):
    id: int
    status: str = "new"
    score: int = 0
    temperature: str = "cold"
    assigned_closer_id: Optional[int] = None
    last_contact: Optional[datetime.datetime] = None
    next_action: Optional[str] = None
    next_action_due: Optional[datetime.datetime] = None
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
    current_state: Dict[str, Any] = Field(default_factory=dict)
    proposed_state: Dict[str, Any] = Field(default_factory=dict)
    risks: Optional[str] = None
    evidence: Optional[List[str]] = None
    expires_at: Optional[datetime.datetime] = None


class ApprovalRequestCreate(ApprovalRequestBase):
    pass


class ApprovalDecision(BaseModel):
    approved: bool
    comment: Optional[str] = Field(None, max_length=1000)


class ApprovalResponse(ApprovalRequestBase):
    id: UUID
    status: str = Field(default="pending", pattern=r"^(pending|approved|rejected|expired|cancelled)$")
    requested_by: str
    requested_at: datetime.datetime
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime.datetime] = None
    review_comment: Optional[str] = None


# =============================================================================
# TAREAS / COLA
# =============================================================================

class TaskBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    priority: str = Field(default="medium", pattern=r"^(low|medium|high)$")
    status: str = Field(default="pending", pattern=r"^(pending|in_progress|completed|failed)$")
    assigned_to: Optional[int] = None
    due_date: Optional[datetime.date] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    priority: Optional[str] = Field(None, pattern=r"^(low|medium|high)$")
    status: Optional[str] = Field(None, pattern=r"^(pending|in_progress|completed|failed)$")
    assigned_to: Optional[int] = None
    due_date: Optional[datetime.date] = None
    metadata: Optional[Dict[str, Any]] = None


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
    description: Optional[str] = None
    average_weight_kg: Optional[float] = Field(None, gt=0)
    average_height_cm: Optional[float] = Field(None, gt=0)
    life_expectancy_years: Optional[int] = Field(None, gt=0)
    temperament: Optional[str] = None
    good_with_children: Optional[bool] = None
    good_with_other_dogs: Optional[bool] = None
    energy_level: Optional[str] = Field(None, pattern=r"^(low|medium|high)$")
    grooming_needs: Optional[str] = Field(None, pattern=r"^(low|medium|high)$")


class BreedCreate(BreedBase):
    pass


class BreedUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    average_weight_kg: Optional[float] = Field(None, gt=0)
    average_height_cm: Optional[float] = Field(None, gt=0)
    life_expectancy_years: Optional[int] = Field(None, gt=0)
    temperament: Optional[str] = None
    good_with_children: Optional[bool] = None
    good_with_other_dogs: Optional[bool] = None
    energy_level: Optional[str] = Field(None, pattern=r"^(low|medium|high)$")
    grooming_needs: Optional[str] = Field(None, pattern=r"^(low|medium|high)$")


class BreedResponse(BreedBase):
    id: int
    created_at: datetime.datetime
    updated_at: datetime.datetime


class LitterBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    breed_id: int = Field(..., gt=0)
    mother_id: int = Field(..., gt=0)
    father_id: Optional[int] = Field(None, gt=0)
    birth_date: datetime.date
    size: int = Field(..., gt=0)
    registration_number: Optional[str] = Field(None, max_length=50)


class LitterCreate(LitterBase):
    pass


class LitterUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    breed_id: Optional[int] = Field(None, gt=0)
    mother_id: Optional[int] = Field(None, gt=0)
    father_id: Optional[int] = Field(None, gt=0)
    birth_date: Optional[datetime.date] = None
    size: Optional[int] = Field(None, gt=0)
    registration_number: Optional[str] = Field(None, max_length=50)


class LitterResponse(LitterBase):
    id: int
    created_at: datetime.datetime
    updated_at: datetime.datetime


class DogMediaBase(BaseModel):
    file_path: str = Field(..., max_length=500)
    file_hash: str = Field(..., min_length=32, max_length=128)  # SHA-256 or similar
    mime_type: str = Field(..., max_length=100)
    width: Optional[int] = Field(None, gt=0)
    height: Optional[int] = Field(None, gt=0)
    duration_seconds: Optional[float] = Field(None, gt=0)  # for videos
    media_type: str = Field(..., pattern=r"^(photo|video)$")
    purpose: str = Field(..., pattern=r"^(original|processed|social|listing)$")
    dog_id: int = Field(..., gt=0)
    uploaded_by: int = Field(..., gt=0)


class DogMediaCreate(DogMediaBase):
    pass


class DogMediaUpdate(BaseModel):
    file_path: Optional[str] = Field(None, max_length=500)
    file_hash: Optional[str] = Field(None, min_length=32, max_length=128)
    mime_type: Optional[str] = Field(None, max_length=100)
    width: Optional[int] = Field(None, gt=0)
    height: Optional[int] = Field(None, gt=0)
    duration_seconds: Optional[float] = Field(None, gt=0)
    media_type: Optional[str] = Field(None, pattern=r"^(photo|video)$")
    purpose: Optional[str] = Field(None, pattern=r"^(original|processed|social|listing)$")
    dog_id: Optional[int] = Field(None, gt=0)
    uploaded_by: Optional[int] = Field(None, gt=0)


class DogMediaResponse(DogMediaBase):
    id: int
    created_at: datetime.datetime


class DogHealthBase(BaseModel):
    vet_check_date: Optional[datetime.date] = None
    weight_kg: Optional[float] = Field(None, gt=0)
    temperature_celsius: Optional[float] = Field(None, ge=35, le=42)
    heart_rate_bpm: Optional[int] = Field(None, gt=0)
    respiratory_rate: Optional[int] = Field(None, gt=0)
    stool_condition: Optional[str] = Field(None, pattern=r"^(normal|soft|diarrhea|constipated)$")
    urine_condition: Optional[str] = Field(None, pattern=r"^(normal|cloudy|bloody)$")
    appetite: Optional[str] = Field(None, pattern=r"^(poor|fair|good|excellent)$")
    energy_level: Optional[str] = Field(None, pattern=r"^(low|medium|high)$")
    notes: Optional[str] = None
    next_check_date: Optional[datetime.date] = None


class DogHealthCreate(DogHealthBase):
    pass


class DogHealthUpdate(BaseModel):
    vet_check_date: Optional[datetime.date] = None
    weight_kg: Optional[float] = Field(None, gt=0)
    temperature_celsius: Optional[float] = Field(None, ge=35, le=42)
    heart_rate_bpm: Optional[int] = Field(None, gt=0)
    respiratory_rate: Optional[int] = Field(None, gt=0)
    stool_condition: Optional[str] = Field(None, pattern=r"^(normal|soft|diarrhea|constipated)$")
    urine_condition: Optional[str] = Field(None, pattern=r"^(normal|cloudy|bloody)$")
    appetite: Optional[str] = Field(None, pattern=r"^(poor|fair|good|excellent)$")
    energy_level: Optional[str] = Field(None, pattern=r"^(low|medium|high)$")
    notes: Optional[str] = None
    next_check_date: Optional[datetime.date] = None


class DogHealthResponse(DogHealthBase):
    id: int
    dog_id: int = Field(..., gt=0)
    recorded_at: datetime.datetime


class DogStatusHistoryBase(BaseModel):
    status: str = Field(..., pattern=r"^(draft|available|reserved|sold|inactive)$")
    changed_by: int = Field(..., gt=0)
    change_reason: Optional[str] = None


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
    litter_id: Optional[int] = Field(None, gt=0)
    sex: str = Field(..., pattern=r"^[MH]$")
    birth_date: datetime.date
    color: str = Field(..., max_length=50)
    microchip: str = Field(..., pattern=r"^\d{15}$")
    sire_name: Optional[str] = Field(None, max_length=200)  # father name
    dam_name: Optional[str] = Field(None, max_length=200)  # mother name
    pedigree: Optional[str] = Field(None, max_length=100)
    vet_status: str = Field(default="healthy", max_length=50)
    purchase_price: float = Field(default=0.0, ge=0)
    sale_price: float = Field(default=0.0, ge=0)
    associated_costs: float = Field(default=0.0, ge=0)
    # Reference to ExpedienteAnimal for Dolibarr sync (optional)
    expediente_id: Optional[int] = Field(None, gt=0)


class DogCreate(DogBase):
    pass


class DogUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    breed_id: Optional[int] = Field(None, gt=0)
    litter_id: Optional[int] = Field(None, gt=0)
    sex: Optional[str] = Field(None, pattern=r"^[MH]$")
    birth_date: Optional[datetime.date] = None
    color: Optional[str] = Field(None, max_length=50)
    vet_status: Optional[str] = Field(None, max_length=50)
    sire_name: Optional[str] = Field(None, max_length=200)
    dam_name: Optional[str] = Field(None, max_length=200)
    pedigree: Optional[str] = Field(None, max_length=100)
    purchase_price: Optional[float] = Field(None, ge=0)
    sale_price: Optional[float] = Field(None, ge=0)
    associated_costs: Optional[float] = Field(None, ge=0)
    expediente_id: Optional[int] = Field(None, gt=0)


class DogResponse(DogBase):
    id: int
    internal_id: str = Field(..., max_length=50)  # e.g., DOG-2026-000001
    created_at: datetime.datetime
    updated_at: datetime.datetime
    created_by: int = 1
    updated_by: int = 1
    # Computed or related fields (optional, for API responses)
    breed: Optional[BreedResponse] = None
    litter: Optional[LitterResponse] = None
    media: List[DogMediaResponse] = Field(default_factory=list)
    health_records: List[DogHealthResponse] = Field(default_factory=list)
    status_history: List[DogStatusHistoryResponse] = Field(default_factory=list)

