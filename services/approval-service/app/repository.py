"""Repository layer for approval operations."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import ApprovalHistory, ApprovalRequest, ApprovalStatus
from app.schemas import ApprovalRequestCreate


class ApprovalRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, data: ApprovalRequestCreate, requester_id: str) -> dict:
        """Create a new approval request."""
        from app.models import ApprovalRequest

        approval = ApprovalRequest(
            action=data.action,
            action_type=data.action_type,
            reason=data.reason,
            current_state=data.current_state,
            proposed_state=data.proposed_state,
            risk_level=data.risk_level,
            risk_factors=data.risk_factors,
            evidence_urls=data.evidence_urls,
            evidence_notes=data.evidence_notes,
            requested_by=data.requested_by,
            expires_at=data.expires_at,
            priority=data.priority,
            idempotency_key=data.idempotency_key,
            task_id=data.task_id,
            metadata=data.metadata,
        )

        self.session.add(approval)
        await self.session.flush()
        await self.session.refresh(approval)

        # Create initial history entry
        history = ApprovalHistory(
            approval_id=approval.id,
            from_status=None,
            to_status=ApprovalStatus.PENDING,
            changed_by=data.requested_by,
            comment="Solicitud de aprobación creada",
            metadata=data.metadata,
        )
        self.session.add(history)
        await self.session.flush()

        return await self.to_dict(approval)

    async def get_by_id(self, approval_id: UUID) -> dict | None:
        """Get approval by ID with relationships."""
        result = await self.session.execute(
            select(ApprovalRequest)
            .options(selectinload(ApprovalRequest.comments), selectinload(ApprovalRequest.history))
            .where(ApprovalRequest.id == approval_id)
        )
        approval = result.scalar_one_or_none()
        return await self.to_dict(approval) if approval else None

    async def get_pending_for_approver(self, limit: int = 100, offset: int = 0) -> list[dict]:
        """Get pending approvals for approver panel."""
        result = await self.session.execute(
            select(ApprovalRequest)
            .where(ApprovalRequest.status == "pending")
            .order_by(desc(ApprovalRequest.priority), desc(ApprovalRequest.requested_at))
            .limit(limit)
            .offset(offset)
        )
        approvals = result.scalars().all()
        return [await self.to_dict(a) for a in approvals]

    async def get_pending_by_user(self, user_id: str, limit: int = 100, offset: int = 0) -> list[dict]:
        """Get pending approvals for a specific user."""
        result = await self.session.execute(
            select(ApprovalRequest)
            .where(ApprovalRequest.requested_by == user_id, ApprovalRequest.status == "pending")
            .order_by(desc(ApprovalRequest.priority), desc(ApprovalRequest.requested_at))
            .limit(limit)
            .offset(offset)
        )
        approvals = result.scalars().all()
        return [await self.to_dict(a) for a in approvals]

    async def approve(self, approval_id: UUID, approver_id: str, decision: dict) -> dict:
        """Approve a pending request."""
        result = await self.session.execute(select(ApprovalRequest).where(ApprovalRequest.id == approval_id))
        approval = result.scalar_one_or_none()

        if not approval:
            return {"success": False, "error": "Aprobación no encontrada"}

        if approval.status != "pending":
            return {"success": False, "error": f"Aprobación ya {approval.status}"}

        if datetime.utcnow() > approval.expires_at:
            approval.status = "expired"
            await self.session.flush()
            return {"success": False, "error": "Aprobación expirada"}

        approved = decision.get("approved", True)
        comment = decision.get("comment", "")

        if not approved and not comment:
            return {"success": False, "error": "Comentario requerido al rechazar"}

        approval.status = "approved" if approved else "rejected"
        approval.approved_by = approver_id
        approval.approved_at = datetime.utcnow()
        approval.approval_comment = comment
        approval.rejection_reason = "" if approved else comment

        # Add history
        history = ApprovalHistory(
            approval_id=approval.id,
            from_status="pending",
            to_status=approval.status,
            changed_by=approver_id,
            comment=comment,
        )
        self.session.add(history)
        await self.session.flush()

        return {
            "success": True,
            "approval_id": str(approval.id),
            "status": approval.status,
            "message": "Aprobación procesada",
        }

    async def get_stats(self) -> dict:
        """Get approval statistics."""
        from datetime import date

        today = date.today()

        pending = await self.session.execute(
            select(func.count(ApprovalRequest.id)).where(ApprovalRequest.status == "pending")
        )

        approved_today = await self.session.execute(
            select(func.count(ApprovalRequest.id)).where(
                and_(ApprovalRequest.status == "approved", func.date(ApprovalRequest.approved_at) == today)
            )
        )

        rejected_today = await self.session.execute(
            select(func.count(ApprovalRequest.id)).where(
                and_(ApprovalRequest.status == "rejected", func.date(ApprovalRequest.approved_at) == today)
            )
        )

        by_action = await self.session.execute(
            select(ApprovalRequest.action, func.count(ApprovalRequest.id)).group_by(ApprovalRequest.action)
        )

        by_priority = await self.session.execute(
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
        result = await self.session.execute(
            select(ApprovalRequest).where(
                ApprovalRequest.status == "pending", ApprovalRequest.expires_at < datetime.utcnow()
            )
        )
        expired_approvals = result.scalars().all()

        expired_count = 0
        for approval in expired_approvals:
            approval.status = "expired"
            history = ApprovalHistory(
                approval_id=approval.id,
                from_status="pending",
                to_status="expired",
                changed_by="system",
                comment="Expirado automáticamente",
            )
            self.session.add(history)
            expired_count += 1

        return {"expired_count": expired_count}

    async def get_by_idempotency_key(self, key: str) -> dict | None:
        """Check if a request with this idempotency key exists."""
        result = await self.session.execute(select(ApprovalRequest).where(ApprovalRequest.idempotency_key == key))
        approval = result.scalar_one_or_none()
        return await self.to_dict(approval) if approval else None

    async def to_dict(self, approval) -> dict:
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
            "status": approval.status.value if hasattr(approval.status, "value") else approval.status,
            "approved_by": approval.approved_by,
            "approved_at": approval.approved_at.isoformat() if approval.approved_at else None,
            "approval_comment": approval.approval_comment,
            "rejection_reason": approval.rejection_reason,
            "execution_result": approval.execution_result,
            "execution_error": approval.execution_error,
            "idempotency_key": approval.idempotency_key,
            "task_id": str(approval.task_id) if approval.task_id else None,
            "metadata": approval.metadata,
            "created_at": approval.created_at.isoformat(),
            "updated_at": approval.updated_at.isoformat() if approval.updated_at else None,
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
