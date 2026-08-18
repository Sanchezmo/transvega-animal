"""Pydantic schemas for approval service."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ApprovalAction(StrEnum):
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


class ApprovalPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ApprovalRiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ApprovalStatus(StrEnum):
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
    action_type: str | None = None
    reason: str = Field(..., min_length=10, max_length=5000)
    current_state: dict[str, Any] = Field(default_factory=dict)
    proposed_state: dict[str, Any] = Field(default_factory=dict)
    risk_level: ApprovalRiskLevel = ApprovalRiskLevel.MEDIUM
    risk_factors: list[str] = Field(default_factory=list)
    evidence_urls: list[str] = Field(default_factory=list)
    evidence_notes: str | None = None
    requested_by: str
    expires_at: datetime
    priority: ApprovalPriority = ApprovalPriority.MEDIUM
    idempotency_key: str | None = None
    task_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ApprovalDecision(BaseModel):
    approved: bool = True
    comment: str | None = None


class ApprovalResponse(BaseModel):
    model_config = {"use_enum_values": True}

    id: str
    action: ApprovalAction
    action_type: str | None = None
    reason: str
    current_state: dict[str, Any] = {}
    proposed_state: dict[str, Any] = {}
    risk_level: ApprovalRiskLevel
    risk_factors: list[str] = []
    evidence_urls: list[str] = []
    evidence_notes: str | None = None
    requested_by: str
    requested_at: datetime
    expires_at: datetime
    auto_approve_at: datetime | None = None
    auto_reject_at: datetime | None = None
    status: ApprovalStatus
    priority: ApprovalPriority
    notifications_sent: bool = False
    approved_by: str | None = None
    approved_at: datetime | None = None
    approval_comment: str | None = None
    rejection_reason: str | None = None
    execution_result: dict[str, Any] | None = None
    execution_error: str | None = None
    idempotency_key: str | None = None
    task_id: str | None = None
    metadata: dict[str, Any] = {}
    created_at: datetime
    updated_at: datetime | None = None
    comments: list[dict[str, Any]] = []
    history: list[dict[str, Any]] = []


class ApprovalListResponse(BaseModel):
    items: list[ApprovalResponse]
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
    from_status: str | None = None
    to_status: str
    changed_by: str
    comment: str | None = None
    created_at: datetime
    metadata: dict[str, Any] = {}


class ApprovalStats(BaseModel):
    pending: int = 0
    approved_today: int = 0
    rejected_today: int = 0
    avg_resolution_hours: float = 0
    by_action: dict[str, int] = {}
    by_priority: dict[str, int] = {}
