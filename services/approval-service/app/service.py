"""Approval Service - Core business logic for approval workflows."""

from datetime import datetime, timedelta
from uuid import uuid4

import structlog
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import async_session_maker
from app.models import ApprovalHistory, ApprovalPriority, ApprovalRequest, ApprovalStatus

logger = structlog.get_logger()


class ApprovalService:
    """Service for managing approval workflows."""

    VALID_TRANSITIONS = {
        "pending": ["approved", "rejected", "expired", "cancelled"],
        "approved": ["executing"],
        "executing": ["completed", "failed"],
        "rejected": [],
        "expired": [],
        "cancelled": [],
        "completed": [],
        "failed": [],
    }

    PRIORITY_EXPIRY_HOURS = {
        "critical": 2,
        "high": 8,
        "medium": 24,
        "low": 72,
    }

    def __init__(self):
        self.approval_rules = self._load_default_rules()

    def _load_default_rules(self) -> list[dict]:
        """Load default approval rules."""
        return [
            {
                "action": "publish",
                "required": True,
                "min_approvers": 1,
                "roles": ["supervisor", "admin"],
                "priority": "high",
                "expiry_hours": 8,
            },
            {
                "action": "price_change",
                "required": True,
                "min_approvers": 1,
                "roles": ["supervisor", "admin"],
                "priority": "high",
                "expiry_hours": 8,
            },
            {
                "action": "discount",
                "required": True,
                "min_approvers": 1,
                "roles": ["supervisor", "admin"],
                "max_amount": 500,
                "priority": "high",
                "expiry_hours": 8,
            },
            {
                "action": "confirm_reservation",
                "required": True,
                "min_approvers": 1,
                "roles": ["supervisor", "admin"],
                "priority": "high",
                "expiry_hours": 8,
            },
            {
                "action": "validate_invoice",
                "required": True,
                "min_approvers": 1,
                "roles": ["accounting", "admin"],
                "priority": "high",
                "expiry_hours": 8,
            },
            {
                "action": "rectify_invoice",
                "required": True,
                "min_approvers": 1,
                "roles": ["accounting", "admin"],
                "priority": "high",
                "expiry_hours": 8,
            },
            {
                "action": "cancel_invoice",
                "required": True,
                "min_approvers": 1,
                "roles": ["accounting", "admin"],
                "priority": "critical",
                "expiry_hours": 2,
            },
            {
                "action": "present_taxes",
                "required": True,
                "min_approvers": 1,
                "roles": ["accounting", "admin"],
                "priority": "critical",
                "expiry_hours": 2,
            },
            {
                "action": "make_payment",
                "required": True,
                "min_approvers": 1,
                "roles": ["accounting", "admin"],
                "priority": "high",
                "expiry_hours": 8,
            },
            {
                "action": "modify_chart_accounts",
                "required": True,
                "min_approvers": 1,
                "roles": ["accounting", "admin"],
                "priority": "critical",
                "expiry_hours": 2,
            },
            {
                "action": "modify_tax_rates",
                "required": True,
                "min_approvers": 1,
                "roles": ["accounting", "admin"],
                "priority": "critical",
                "expiry_hours": 2,
            },
            {
                "action": "modify_fiscal_data",
                "required": True,
                "min_approvers": 1,
                "roles": ["accounting", "admin"],
                "priority": "critical",
                "expiry_hours": 2,
            },
            {
                "action": "launch_paid_campaign",
                "required": True,
                "min_approvers": 1,
                "roles": ["marketing", "admin"],
                "priority": "medium",
                "expiry_hours": 24,
            },
            {
                "action": "update_production",
                "required": True,
                "min_approvers": 1,
                "roles": ["tech_lead", "admin"],
                "priority": "critical",
                "expiry_hours": 2,
            },
            {
                "action": "delete_data",
                "required": True,
                "min_approvers": 2,
                "roles": ["admin"],
                "priority": "critical",
                "expiry_hours": 1,
            },
            {
                "action": "bulk_export",
                "required": True,
                "min_approvers": 1,
                "roles": ["admin", "dpo"],
                "priority": "medium",
                "expiry_hours": 24,
            },
        ]

    def _get_rule(self, action: str) -> dict | None:
        """Get approval rule for an action."""
        for rule in self.approval_rules:
            if rule["action"] == action:
                return rule
        return None

    def _validate_transition(self, from_status: str, to_status: str) -> bool:
        """Validate if a status transition is allowed."""
        allowed = self.VALID_TRANSITIONS.get(from_status, [])
        return to_status in allowed

    async def _get_session(self) -> AsyncSession:
        """Get database session."""
        return async_session_maker()

    async def _find_by_idempotency_key(self, key: str) -> object | None:
        """Find approval by idempotency key."""
        async with async_session_maker() as session:
            result = await session.execute(select(ApprovalRequest).where(ApprovalRequest.idempotency_key == key))
            return result.scalar_one_or_none()

    async def request_approval(self, data: dict, requester_id: str) -> dict:
        """Create a new approval request."""
        # Validate action
        action = data.get("action")
        rule = self._get_rule(action)
        if not rule:
            return {"success": False, "error": f"Unknown action: {action}"}

        # Validate required fields
        required_fields = ["action", "reason", "current_state", "proposed_state", "requested_by", "expires_at"]
        for field in required_fields:
            if not data.get(field):
                return {"success": False, "error": f"Missing required field: {field}"}

        # Validate transition
        if not self._validate_transition("pending", "pending"):
            return {"success": False, "error": "Invalid initial state"}

        # Check idempotency
        idempotency_key = data.get("idempotency_key")
        if idempotency_key:
            existing = await self._find_by_idempotency_key(idempotency_key)
            if existing:
                return {
                    "success": True,
                    "approval_id": str(existing.id),
                    "status": existing.status.value,
                    "message": "Request already exists",
                    "duplicate": True,
                }

        # Calculate expiration
        priority = data.get("priority", "medium")
        expires_hours = self.PRIORITY_EXPIRY_HOURS.get(priority, 24)
        expires_at = datetime.utcnow() + timedelta(hours=expires_hours)

        # Create approval request
        async with async_session_maker() as session:
            approval = ApprovalRequest(
                id=uuid4(),
                action=data["action"],
                action_type=data.get("action_type"),
                reason=data["reason"],
                current_state=data["current_state"],
                proposed_state=data["proposed_state"],
                risk_level=data.get("risk_level", "medium"),
                risk_factors=data.get("risk_factors", []),
                evidence_urls=data.get("evidence_urls", []),
                evidence_notes=data.get("evidence_notes"),
                requested_by=data["requested_by"],
                expires_at=expires_at,
                priority=ApprovalPriority(priority),
                idempotency_key=data.get("idempotency_key"),
                task_id=data.get("task_id"),
                metadata=data.get("metadata", {}),
                status=ApprovalStatus.PENDING,
            )

            session.add(approval)
            await session.flush()

            # Create initial history entry
            history = ApprovalHistory(
                id=uuid4(),
                approval_id=approval.id,
                from_status=None,
                to_status="pending",
                changed_by=data["requested_by"],
                comment="Solicitud de aprobación creada",
                metadata=data.get("metadata", {}),
            )
            session.add(history)
            await session.commit()
            await session.refresh(approval)

            approval_id = str(approval.id)

        logger.info(
            "approval_requested",
            approval_id=approval_id,
            action=action,
            requester=data["requested_by"],
        )

        return {
            "success": True,
            "approval_id": approval_id,
            "status": "pending",
            "expires_at": expires_at.isoformat(),
            "message": "Solicitud de aprobación creada correctamente",
        }

    async def get_pending(self, limit: int = 100, offset: int = 0, user_id: str | None = None) -> list[dict]:
        """Get pending approvals."""
        async with async_session_maker() as session:
            query = (
                select(ApprovalRequest)
                .where(ApprovalRequest.status == ApprovalStatus.PENDING)
                .order_by(desc(ApprovalRequest.priority), desc(ApprovalRequest.requested_at))
                .limit(limit)
                .offset(offset)
            )

            if user_id:
                query = query.where(ApprovalRequest.requested_by == user_id)

            result = await session.execute(query)
            approvals = result.scalars().all()

            return [
                {
                    "id": str(a.id),
                    "action": a.action.value,
                    "action_type": a.action_type,
                    "reason": a.reason,
                    "current_state": a.current_state,
                    "proposed_state": a.proposed_state,
                    "risk_level": a.risk_level,
                    "risk_factors": a.risk_factors,
                    "requested_by": a.requested_by,
                    "requested_at": a.requested_at.isoformat(),
                    "expires_at": a.expires_at.isoformat() if a.expires_at else None,
                    "priority": a.priority.value,
                    "status": a.status.value,
                    "idempotency_key": a.idempotency_key,
                }
                for a in approvals
            ]

    async def get_approval(self, approval_id: str) -> dict | None:
        """Get approval by ID."""
        async with async_session_maker() as session:
            result = await session.execute(
                select(ApprovalRequest)
                .where(ApprovalRequest.id == approval_id)
                .options(selectinload(ApprovalRequest.comments), selectinload(ApprovalRequest.history))
            )
            approval = result.scalar_one_or_none()
            return await self._approval_to_dict(approval) if approval else None

    async def approve(self, approval_id: str, decision: dict, approver_id: str) -> dict:
        """Approve a pending request."""
        async with async_session_maker() as session:
            result = await session.execute(
                select(ApprovalRequest)
                .where(ApprovalRequest.id == approval_id)
                .options(selectinload(ApprovalRequest.history))
            )
            approval = result.scalar_one_or_none()

            if not approval:
                return {"success": False, "error": "Aprobación no encontrada"}

            if approval.status != ApprovalStatus.PENDING:
                return {"success": False, "error": f"Aprobación ya {approval.status.value}"}

            if datetime.utcnow() > approval.expires_at:
                approval.status = ApprovalStatus.EXPIRED
                await session.commit()
                return {"success": False, "error": "Aprobación expirada"}

            # Validate transition
            if not self._validate_transition(approval.status.value, "approved"):
                return {"success": False, "error": "Transición de estado inválida"}

            # Update approval
            approval.status = ApprovalStatus.APPROVED
            approval.approved_by = approver_id
            approval.approved_at = datetime.utcnow()
            approval.approval_comment = decision.get("comment", "")

            # Add history
            history = ApprovalHistory(
                id=uuid4(),
                approval_id=approval.id,
                from_status="pending",
                to_status="approved",
                changed_by=approver_id,
                comment=decision.get("comment", ""),
            )
            session.add(history)
            await session.commit()
            await session.refresh(approval)

        logger.info(
            "approval_approved",
            approval_id=approval_id,
            approver=approver_id,
        )

        return {
            "success": True,
            "approval_id": approval_id,
            "status": "approved",
            "message": "Aprobación procesada correctamente",
        }

    async def reject(self, approval_id: str, decision: dict, rejecter_id: str) -> dict:
        """Reject a pending request."""
        async with async_session_maker() as session:
            result = await session.execute(
                select(ApprovalRequest)
                .where(ApprovalRequest.id == approval_id)
                .options(selectinload(ApprovalRequest.history))
            )
            approval = result.scalar_one_or_none()

            if not approval:
                return {"success": False, "error": "Aprobación no encontrada"}

            if approval.status != ApprovalStatus.PENDING:
                return {"success": False, "error": f"Aprobación ya {approval.status.value}"}

            if not decision.get("comment"):
                return {"success": False, "error": "Comentario requerido al rechazar"}

            if not self._validate_transition(approval.status.value, "rejected"):
                return {"success": False, "error": "Transición de estado inválida"}

            approval.status = ApprovalStatus.REJECTED
            approval.approved_by = rejecter_id
            approval.approved_at = datetime.utcnow()
            approval.rejection_reason = decision.get("comment", "")

            history = ApprovalHistory(
                id=uuid4(),
                approval_id=approval.id,
                from_status="pending",
                to_status="rejected",
                changed_by=rejecter_id,
                comment=decision.get("comment", ""),
            )
            session.add(history)
            await session.commit()

        return {
            "success": True,
            "approval_id": approval_id,
            "status": "rejected",
            "message": "Aprobación rechazada",
        }

    async def cancel(self, approval_id: str, requester_id: str) -> dict:
        """Cancel own pending request."""
        async with async_session_maker() as session:
            result = await session.execute(
                select(ApprovalRequest)
                .where(ApprovalRequest.id == approval_id)
                .options(selectinload(ApprovalRequest.history))
            )
            approval = result.scalar_one_or_none()

            if not approval:
                return {"success": False, "error": "Aprobación no encontrada"}

            if approval.status != ApprovalStatus.PENDING:
                return {"success": False, "error": "Solo se pueden cancelar solicitudes pendientes"}

            if approval.requested_by != requester_id:
                return {"success": False, "error": "Solo el solicitante puede cancelar"}

            approval.status = ApprovalStatus.CANCELLED
            approval.cancelled_at = datetime.utcnow()
            approval.cancelled_by = requester_id

            history = ApprovalHistory(
                id=uuid4(),
                approval_id=approval.id,
                from_status="pending",
                to_status="cancelled",
                changed_by=requester_id,
                comment="Cancelado por el solicitante",
            )
            session.add(history)
            await session.commit()

        return {"success": True, "message": "Solicitud cancelada"}

    async def get_approval(self, approval_id: str) -> dict | None:
        """Get approval by ID."""
        async with async_session_maker() as session:
            result = await session.execute(
                select(ApprovalRequest)
                .where(ApprovalRequest.id == approval_id)
                .options(selectinload(ApprovalRequest.comments), selectinload(ApprovalRequest.history))
            )
            approval = result.scalar_one_or_none()
            return await self._approval_to_dict(approval) if approval else None

    async def _approval_to_dict(self, approval) -> dict:
        """Convert approval model to dict."""
        if not approval:
            return None

        return {
            "id": str(approval.id),
            "action": approval.action.value,
            "action_type": approval.action_type,
            "reason": approval.reason,
            "current_state": approval.current_state,
            "proposed_state": approval.proposed_state,
            "risk_level": approval.risk_level,
            "risk_factors": approval.risk_factors,
            "evidence_urls": approval.evidence_urls,
            "evidence_notes": approval.evidence_notes,
            "requested_by": approval.requested_by,
            "requested_at": approval.requested_at.isoformat(),
            "expires_at": approval.expires_at.isoformat() if approval.expires_at else None,
            "priority": approval.priority.value,
            "status": approval.status.value,
            "approved_by": approval.approved_by,
            "approved_at": approval.approved_at.isoformat() if approval.approved_at else None,
            "approval_comment": approval.approval_comment,
            "rejection_reason": approval.rejection_reason,
            "execution_result": approval.execution_result,
            "execution_error": approval.execution_error,
            "idempotency_key": approval.idempotency_key,
            "task_id": str(approval.task_id) if approval.task_id else None,
            "metadata": approval.metadata,
            "comments": [
                {
                    "id": str(c.id),
                    "author_id": c.author_id,
                    "author_name": c.author_name,
                    "content": c.content,
                    "created_at": c.created_at.isoformat(),
                }
                for c in approval.comments
            ],
            "history": [
                {
                    "id": str(h.id),
                    "from_status": h.from_status,
                    "to_status": h.to_status,
                    "changed_by": h.changed_by,
                    "comment": h.comment,
                    "created_at": h.created_at.isoformat(),
                }
                for h in approval.history
            ],
        }

    async def get_my_pending(self, user_id: str, limit: int = 100, offset: int = 0) -> list[dict]:
        """Get pending approvals for a specific user."""
        async with async_session_maker() as session:
            result = await session.execute(
                select(ApprovalRequest)
                .where(ApprovalRequest.status == ApprovalStatus.PENDING)
                .where(ApprovalRequest.requested_by == user_id)
                .order_by(desc(ApprovalRequest.priority), desc(ApprovalRequest.requested_at))
                .limit(limit)
                .offset(offset)
            )
            approvals = result.scalars().all()

            return [await self._approval_to_dict(a) for a in approvals]

    async def get_pending_for_approver(self, limit: int = 100, offset: int = 0) -> list[dict]:
        """Get pending approvals for approver panel."""
        async with async_session_maker() as session:
            result = await session.execute(
                select(ApprovalRequest)
                .where(ApprovalRequest.status == ApprovalStatus.PENDING)
                .order_by(desc(ApprovalRequest.priority), desc(ApprovalRequest.requested_at))
                .limit(limit)
                .offset(offset)
            )
            approvals = result.scalars().all()

            return [await self._approval_to_dict(a) for a in approvals]

    async def get_stats(self) -> dict:
        """Get approval statistics."""
        async with async_session_maker() as session:
            today = date.today()

            # Pending count
            pending = await session.execute(
                select(func.count(ApprovalRequest.id)).where(ApprovalRequest.status == ApprovalStatus.PENDING)
            )

            # Approved today
            approved_today = await session.execute(
                select(func.count(ApprovalRequest.id)).where(
                    and_(
                        ApprovalRequest.status == ApprovalStatus.APPROVED,
                        func.date(ApprovalRequest.approved_at) == today,
                    )
                )
            )

            # Rejected today
            rejected_today = await session.execute(
                select(func.count(ApprovalRequest.id)).where(
                    and_(
                        ApprovalRequest.status == ApprovalStatus.REJECTED,
                        func.date(ApprovalRequest.approved_at) == today,
                    )
                )
            )

            # By action
            by_action = await session.execute(
                select(ApprovalRequest.action, func.count(ApprovalRequest.id)).group_by(ApprovalRequest.action)
            )

            # By priority
            by_priority = await session.execute(
                select(ApprovalRequest.priority, func.count(ApprovalRequest.id)).group_by(ApprovalRequest.priority)
            )

            return {
                "pending": pending.scalar() or 0,
                "approved_today": approved_today.scalar() or 0,
                "rejected_today": rejected_today.scalar() or 0,
                "by_action": {a.action.value: c for a, c in by_action.all()},
                "by_priority": {p.priority.value: c for p, c in by_priority.all()},
            }

    async def check_expired(self) -> dict:
        """Check and expire overdue approvals."""
        async with async_session_maker() as session:
            result = await session.execute(
                select(ApprovalRequest).where(
                    and_(
                        ApprovalRequest.status == ApprovalStatus.PENDING, ApprovalRequest.expires_at < datetime.utcnow()
                    )
                )
            )
            expired_approvals = result.scalars().all()

            expired_count = 0
            for approval in expired_approvals:
                approval.status = ApprovalStatus.EXPIRED
                history = ApprovalHistory(
                    id=uuid4(),
                    approval_id=approval.id,
                    from_status="pending",
                    to_status="expired",
                    changed_by="system",
                    comment="Expirado automáticamente",
                )
                session.add(history)
                expired_count += 1

            await session.commit()

        return {"expired_count": expired_count}
