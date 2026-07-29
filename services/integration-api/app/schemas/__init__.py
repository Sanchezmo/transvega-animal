"""
Esquemas Pydantic para validación de datos de entrada/salida.
"""
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import date, datetime
from uuid import UUID


# =============================================================================
# ESQUEMAS BASE
# =============================================================================

class BaseSchema(BaseModel):
    """Esquema base con configuración común."""
    
    class Config:
        from_attributes = True
        populate_by_name = True
        use_enum_values = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            date: lambda v: v.isoformat(),
            UUID: lambda v: str(v),
        }


class PaginationParams(BaseModel):
    """Parámetros de paginación estándar."""
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
    
    @property
    def page(self) -> int:
        return (self.offset // self.limit) + 1


class PaginatedResponse(BaseModel):
    """Respuesta paginada estándar."""
    success: bool = True
    data: List[Any]
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


class ThirdPartyResponse(ThirdPartyBase):
    id: int
    ref: str
    ref_ext: Optional[str] = None
    canvas: Optional[str] = None
    datec: datetime
    datem: datetime
    fk_user_author: int = 1
    fk_user_modif: int = 1


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
    buy_price: float = Field(default=0.0, ge=0)
    weight: float = Field(default=0.0, ge=0)
    weight_units: int = Field(default=1, ge=1)
    status: int = Field(default=1, ge=0, le=1)
    type: int = Field(default=0, ge=0, le=2)
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
    buy_price: Optional[float] = Field(None, ge=0)
    weight: Optional[float] = Field(None, ge=0)
    weight_units: Optional[int] = Field(None, ge=1)
    status: Optional[int] = Field(None, ge=0, le=1)
    type: Optional[int] = Field(None, ge=0, le=2)
    fk_product_type: Optional[int] = None


class ProductResponse(ProductBase):
    id: int
    ref_ext: Optional[str] = None
    datec: datetime
    datem: datetime


# =============================================================================
# EXPEDIENTES ANIMALES
# =============================================================================

class VaccineRecord(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    date: date
    batch: Optional[str] = Field(None, max_length=50)
    vet: Optional[str] = Field(None, max_length=100)
    next_due: Optional[date] = None


class DewormingRecord(BaseModel):
    product: str = Field(..., min_length=1, max_length=100)
    date: date
    next_due: Optional[date] = None
    vet: Optional[str] = Field(None, max_length=100)


class CertificateRecord(BaseModel):
    type: str = Field(..., max_length=50)  # veterinary_health, genetic, pedigree, etc.
    date: date
    issuer: Optional[str] = Field(None, max_length=100)
    document_url: Optional[str] = None
    expires_at: Optional[date] = None


class IncidentRecord(BaseModel):
    date: date
    type: str = Field(..., max_length=50)
    description: str
    severity: str = Field(default="low", pattern=r"^(low|medium|high|critical)$")
    resolved: bool = False
    resolution_date: Optional[date] = None
    resolution_notes: Optional[str] = None


class PostSaleFollowupRecord(BaseModel):
    date: date
    type: str = Field(..., max_length=50)  # call, visit, email, vet_report
    notes: str
    next_action: Optional[str] = None
    next_action_date: Optional[date] = None


class ExpedienteAnimalBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    species: str = Field(default="perro", max_length=50)
    breed: str = Field(..., min_length=1, max_length=100)
    sex: str = Field(..., pattern=r"^[MH]$")
    birth_date: date
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
        pattern=r"^(draft|pending_docs|pending_review|available|published|reserved|paid|preparing_transport|in_transport|delivered|post_sale|unavailable|archived)$"
    )
    client_id: Optional[int] = None
    reservation_id: Optional[int] = None
    order_id: Optional[int] = None
    invoice_id: Optional[int] = None
    transport_id: Optional[int] = None
    expected_delivery_date: Optional[date] = None
    actual_delivery_date: Optional[date] = None
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
        pattern=r"^(draft|pending_docs|pending_review|available|published|reserved|paid|preparing_transport|in_transport|delivered|post_sale|unavailable|archived)$"
    )
    client_id: Optional[int] = None
    expected_delivery_date: Optional[date] = None
    actual_delivery_date: Optional[date] = None


class ExpedienteAnimalResponse(ExpedienteAnimalBase):
    id: int
    internal_id: str
    created_at: datetime
    updated_at: datetime
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
    date: date = Field(default_factory=date.today)
    lines: List[InvoiceLineCreate] = Field(..., min_length=1)
    status: int = Field(default=0, ge=0, le=2)
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
    datec: datetime
    datem: datetime
    fk_user_author: int = 1
    fk_user_modif: int = 1


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


class PublicationResponse(PublicationBase):
    id: int
    status: str = Field(default="draft", pattern=r"^(draft|pending_approval|approved|published|expired|removed|failed)$")
    published_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    approval_id: Optional[UUID] = None


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
    last_contact: Optional[datetime] = None
    next_action: Optional[str] = None
    next_action_due: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


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
    expires_at: Optional[datetime] = None


class ApprovalRequestCreate(ApprovalRequestBase):
    pass


class ApprovalDecision(BaseModel):
    approved: bool
    comment: Optional[str] = Field(None, max_length=1000)


class ApprovalResponse(ApprovalRequestBase):
    id: UUID
    status: str = Field(default="pending", pattern=r"^(pending|approved|rejected|expired|cancelled)$")
    requested_by: str
    requested_at: datetime
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    review_comment: Optional[str] = None


# =============================================================================
# TAREAS / COLA
# =============================================================================

class TaskBase(BaseModel):
    task_type: str = Field(..., max_length=100)
    priority: int = Field(default=5, ge=1, le=10)
    agent_id: Optional[str] = None
    input_data: Dict[str, Any] = Field(default_factory=dict)
    scheduled_at: Optional[datetime] = None
    timeout_seconds: int = Field(default=3600, ge=60, le=86400)
    max_attempts: int = Field(default=3, ge=1, le=10)
    requires_approval: bool = False
    idempotency_key: Optional[str] = Field(None, max_length=100)
    resource_type: Optional[str] = Field(None, max_length=100)
    resource_id: Optional[str] = Field(None, max_length=100)
    correlation_id: Optional[UUID] = None
    tags: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


class TaskCreate(TaskBase):
    pass


class TaskResponse(TaskBase):
    id: UUID
    status: str = Field(default="pending", pattern=r"^(pending|processing|waiting_approval|completed|error_temp|error_perm|cancelled)$")
    attempt: int = 0
    last_error: Optional[str] = None
    output_data: Optional[Dict[str, Any]] = None
    error_data: Optional[Dict[str, Any]] = None
    progress_percent: int = 0
    progress_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


# =============================================================================
# AUDITORÍA
# =============================================================================

class AuditLogResponse(BaseModel):
    id: UUID
    created_at: datetime
    agent_name: str
    agent_id: str
    action: str
    resource_type: str
    resource_id: str
    success: bool
    duration_ms: int
    request_data: Dict[str, Any]
    response_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


# =============================================================================
# RESPUESTAS ESTÁNDAR
# =============================================================================

class SuccessResponse(BaseModel):
    success: bool = True
    message: Optional[str] = None
    data: Optional[Any] = None


class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    message: str
    details: Optional[Dict[str, Any]] = None
    request_id: Optional[str] = None