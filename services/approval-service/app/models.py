"""Approval Service Database Models."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


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


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"


class ApprovalRequest(AsyncAttrs, Base):
    __tablename__ = "approval_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Action details
    action = Column(
        Enum(ApprovalAction, values_callable=lambda obj: [e.value for e in obj]), nullable=False, index=True
    )
    action_type = Column(String(100), nullable=True)
    reason = Column(Text, nullable=False)
    current_state = Column(JSONB, default={}, nullable=False)
    proposed_state = Column(JSONB, default={}, nullable=False)
    risk_level = Column(String(20), default="medium", nullable=False)
    risk_factors = Column(JSONB, default=[], nullable=False)
    evidence_urls = Column(JSONB, default=[], nullable=False)
    evidence_notes = Column(Text, nullable=True)

    # Requester
    requested_by = Column(String(100), nullable=False, index=True)
    requested_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Expiration
    expires_at = Column(DateTime, nullable=False, index=True)
    auto_approve_at = Column(DateTime, nullable=True)
    auto_reject_at = Column(DateTime, nullable=True)

    # Status
    status = Column(
        Enum(ApprovalStatus, values_callable=lambda obj: [e.value for e in obj]),
        default=ApprovalStatus.PENDING,
        nullable=False,
        index=True,
    )
    priority = Column(
        Enum(ApprovalPriority, values_callable=lambda obj: [e.value for e in obj]),
        default=ApprovalPriority.MEDIUM,
        nullable=False,
    )

    # Resolution
    approved_by = Column(String(100), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    approval_comment = Column(Text, nullable=True)
    rejection_reason = Column(Text, nullable=True)

    # Execution
    execution_result = Column(JSONB, nullable=True)
    execution_error = Column(Text, nullable=True)
    task_id = Column(String(100), nullable=True, index=True)

    # Idempotency
    idempotency_key = Column(String(100), unique=True, nullable=True, index=True)

    # Related task
    task_id_ref = Column(String(100), nullable=True, index=True)

    # Metadata
    approval_metadata = Column(JSONB, default={}, nullable=False)

    # Relationships
    comments = relationship("ApprovalComment", back_populates="approval", lazy="selectin")
    history = relationship("ApprovalHistory", back_populates="approval", lazy="selectin")

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Indexes
    __table_args__ = (
        Index("ix_approval_status_priority", "status", "priority"),
        Index("ix_approval_requested_by", "requested_by"),
        Index("ix_approval_expires_at", "expires_at"),
        Index("ix_approval_idempotency", "idempotency_key"),
    )


class ApprovalComment(AsyncAttrs, Base):
    __tablename__ = "approval_comments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    approval_id = Column(UUID(as_uuid=True), ForeignKey("approval_requests.id", ondelete="CASCADE"), nullable=False)
    author_id = Column(String(100), nullable=False)
    author_name = Column(String(200), nullable=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    approval = relationship("ApprovalRequest", back_populates="comments")


class ApprovalHistory(AsyncAttrs, Base):
    __tablename__ = "approval_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    approval_id = Column(UUID(as_uuid=True), ForeignKey("approval_requests.id", ondelete="CASCADE"), nullable=False)
    from_status = Column(String(50), nullable=False)
    to_status = Column(String(50), nullable=False)
    changed_by = Column(String(100), nullable=False)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    approval = relationship("ApprovalRequest", back_populates="history")


class ApprovalRule(AsyncAttrs, Base):
    """Configuration for approval rules."""

    __tablename__ = "approval_rules"
    __allow_unmapped__ = True

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    action = Column(
        Enum(ApprovalAction, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        unique=True,
        index=True,
    )
    required = Column(Boolean, default=True, nullable=False)
    min_approvers = Column(Integer, default=1, nullable=False)
    allowed_roles = Column(JSONB, default=[], nullable=False)
    auto_approve_if = Column(JSONB, nullable=True)
    auto_reject_if = Column(JSONB, nullable=True)
    max_amount = Column(Numeric(15, 2), nullable=True)
    min_approvals = Column(Integer, default=1, nullable=False)
    require_comment = Column(Boolean, default=True, nullable=False)
    expiry_hours = Column(Integer, default=24, nullable=False)
    auto_approve_hours = Column(Integer, nullable=True)
    auto_reject_hours = Column(Integer, nullable=True)
    priority = Column(String(20), default="medium", nullable=False)
    escalation_hours = Column(Integer, nullable=True)
    escalation_to = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    @classmethod
    def get_default_rules(cls) -> list[dict]:
        """Get default approval rules."""
        return [
            {
                "action": "publish",
                "required": True,
                "min_approvers": 1,
                "allowed_roles": ["supervisor", "admin"],
                "priority": "high",
                "expiry_hours": 8,
                "auto_reject_hours": 24,
            },
            {
                "action": "price_change",
                "required": True,
                "min_approvers": 1,
                "allowed_roles": ["supervisor", "admin"],
                "priority": "high",
                "expiry_hours": 8,
                "auto_reject_hours": 24,
            },
            {
                "action": "discount",
                "required": True,
                "min_approvers": 1,
                "allowed_roles": ["supervisor", "admin"],
                "max_amount": 500,
                "priority": "high",
                "expiry_hours": 8,
            },
            {
                "action": "confirm_reservation",
                "required": True,
                "min_approvers": 1,
                "allowed_roles": ["supervisor", "admin"],
                "priority": "high",
                "expiry_hours": 8,
            },
            {
                "action": "validate_invoice",
                "required": True,
                "min_approvers": 1,
                "allowed_roles": ["accounting", "admin"],
                "priority": "high",
                "expiry_hours": 8,
            },
            {
                "action": "rectify_invoice",
                "required": True,
                "min_approvers": 1,
                "allowed_roles": ["accounting", "admin"],
                "priority": "high",
                "expiry_hours": 8,
            },
            {
                "action": "cancel_invoice",
                "required": True,
                "min_approvers": 1,
                "allowed_roles": ["accounting", "admin"],
                "priority": "critical",
                "expiry_hours": 2,
            },
            {
                "action": "present_taxes",
                "required": True,
                "min_approvers": 1,
                "allowed_roles": ["accounting", "admin"],
                "priority": "critical",
                "expiry_hours": 2,
            },
            {
                "action": "make_payment",
                "required": True,
                "min_approvers": 1,
                "allowed_roles": ["accounting", "admin"],
                "priority": "high",
                "expiry_hours": 8,
            },
            {
                "action": "modify_chart_accounts",
                "required": True,
                "min_approvers": 1,
                "allowed_roles": ["accounting", "admin"],
                "priority": "critical",
                "expiry_hours": 2,
            },
            {
                "action": "modify_tax_rates",
                "required": True,
                "min_approvers": 1,
                "allowed_roles": ["accounting", "admin"],
                "priority": "critical",
                "expiry_hours": 2,
            },
            {
                "action": "modify_fiscal_data",
                "required": True,
                "min_approvers": 1,
                "allowed_roles": ["accounting", "admin"],
                "priority": "critical",
                "expiry_hours": 2,
            },
            {
                "action": "launch_paid_campaign",
                "required": True,
                "min_approvers": 1,
                "allowed_roles": ["marketing", "admin"],
                "priority": "medium",
                "expiry_hours": 24,
            },
            {
                "action": "update_production",
                "required": True,
                "min_approvers": 1,
                "allowed_roles": ["tech_lead", "admin"],
                "priority": "critical",
                "expiry_hours": 2,
            },
            {
                "action": "delete_data",
                "required": True,
                "min_approvers": 2,
                "allowed_roles": ["admin"],
                "priority": "critical",
                "expiry_hours": 1,
            },
            {
                "action": "bulk_export",
                "required": True,
                "min_approvers": 1,
                "allowed_roles": ["admin", "dpo"],
                "priority": "medium",
                "expiry_hours": 24,
            },
        ]
