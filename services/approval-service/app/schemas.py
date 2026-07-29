"""Pydantic schemas for approval service."""
from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import UUID
from pydantic import BaseModel, Field
from enum import Enum


class ApprovalAction(str, Enum):
    PUBLISH = "publish"
    PRICE_CHANGE = "price_change"
    DISCOUNT = "discount"
    CONFIRM_RESERVATION = "confirm_reservation"
    VALIDATE_INVOICE = "validate_invoice"
    RECTIFY_INVOICE = "rectify_invoice"
    CANCEL_INVOICE = "cancel_invoice"
    PRESENT_TAXES = "present_taxes"
    MAKE_PAYMENT = "make_payment"
    MODIFY_CHART_ACCOUNTS = "modify_chart_accounts"
    MODIFY_TAX_RATES = "modify_tax_rates"
    MODIFY_FISCAL_DATA = "modify_fiscal_data"
    LAUNCH_PAID_CAMPAIGN = "launch_paid_campaign"
    UPDATE_PRODUCTION = "update_production"
    DELETE_DATA = "delete_data"
    BULK_EXPORT = "bulk_export"


class ApprovalPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ApprovalRiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"


class ApprovalRequestCreate(BaseModel):
    model_config = {"use_enum_values": True}
    
    action: ApprovalAction
    action_type: Optional[str] = None
    reason: str = Field(..., min_length=10, max_length=5000)
    current_state: Dict[str, Any] = Field(default_factory=dict)
    proposed_state: Dict[str, Any] = Field(default_factory=dict)
    risk_level: ApprovalRiskLevel = ApprovalRiskLevel.MEDIUM
    risk_factors: List[str] = Field(default_factory=list)
    evidence_urls: List[str] = Field(default_factory=list)
    evidence_notes: Optional[str] = None
    requested_by: str
    expires_at: datetime
    priority: ApprovalPriority = ApprovalPriority.MEDIUM
    idempotency_key: Optional[str] = None
    task_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ApprovalDecision(BaseModel):
    approved: bool = True
    comment: Optional[str] = None


class ApprovalResponse(BaseModel):
    model_config = {"use_enum_values": True}
    
    id: str
    action: ApprovalAction
    action_type: Optional[str] = None
    reason: str
    current_state: Dict[str, Any] = {}
    proposed_state: Dict[str, Any] = {}
    risk_level: ApprovalRiskLevel
    risk_factors: List[str] = []
    evidence_urls: List[str] = []
    evidence_notes: Optional[str] = None
    requested_by: str
    requested_at: datetime
    expires_at: datetime
    auto_approve_at: Optional[datetime] = None
    auto_reject_at: Optional[datetime] = None
    status: ApprovalStatus
    priority: ApprovalPriority
    notifications_sent: bool = False
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    approval_comment: Optional[str] = None
    rejection_reason: Optional[str] = None
    execution_result: Optional[Dict[str, Any]] = None
    execution_error: Optional[str] = None
    idempotency_key: Optional[str] = None
    task_id: Optional[str] = None
    metadata: Dict[str, Any] = {}
    created_at: datetime
    updated_at: Optional[datetime] = None
    comments: List[Dict[str, Any]] = []
    history: List[Dict[str, Any]] = []


class ApprovalListResponse(BaseModel):
    items: List[ApprovalResponse]
    total: int
    limit: int
    offset: int


class ApprovalCommentCreate(BaseModel):
    comment: str = Field(..., min_length=1, max_length=5000)


class ApprovalCommentResponse(BaseModel):
    id: str
    approval_id: str
    author_id: str
    author_name: str
    content: str
    created_at: datetime


class ApprovalHistoryResponse(BaseModel):
    id: str
    approval_id: str
    from_status: Optional[str] = None
    to_status: str
    changed_by: str
    comment: Optional[str] = None
    created_at: datetime
    metadata: Dict[str, Any] = {}


class ApprovalStats(BaseModel):
    pending: int = 0
    approved_today: int = 0
    rejected_today: int = 0
    avg_resolution_hours: float = 0
    by_action: Dict[str, int] = {}
    by_priority: Dict[str, int] = {}