"""Approval routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user, require_approver
from app.schemas import (
    ApprovalListResponse,
    ApprovalRequestCreate,
    ApprovalResponse,
)
from app.service import ApprovalService

router = APIRouter(prefix="/api/v1/approvals", tags=["Approvals"])


async def get_approval_service(db: AsyncSession = Depends(get_db)) -> ApprovalService:
    """Get approval service with database session."""
    return ApprovalService(db)


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_approval(
    data: ApprovalRequestCreate,
    current_user: dict = Depends(get_current_user),
    service: ApprovalService = Depends(get_approval_service),
):
    """Create a new approval request."""
    try:
        result = await service.request_approval(data.model_dump(), current_user["id"])
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=ApprovalListResponse)
async def list_approvals(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    status: str | None = Query(None),
    user_id: str | None = Query(None),
    current_user: dict = Depends(get_current_user),
    service: ApprovalService = Depends(get_approval_service),
):
    """List approval requests (admin/supervisor view)."""
    if current_user["role"] not in ["admin", "supervisor"]:
        raise HTTPException(status_code=403, detail="Not authorized to view all approvals")

    try:
        result = await service.get_pending(limit=limit, offset=offset)
        return {"items": result, "total": len(result), "limit": limit, "offset": offset}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pending", response_model=ApprovalListResponse)
async def list_pending(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(require_approver),
    service: ApprovalService = Depends(get_approval_service),
):
    """List pending approvals for approver panel."""
    try:
        result = await service.get_pending_for_approver(limit, offset)
        return {"items": result, "total": len(result), "limit": limit, "offset": offset}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/my-pending", response_model=ApprovalListResponse)
async def my_pending(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
    service: ApprovalService = Depends(get_approval_service),
):
    """List my pending approval requests."""
    try:
        result = await service.get_my_pending(current_user["id"], limit, offset)
        return {"items": result, "total": len(result), "limit": limit, "offset": offset}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{approval_id}", response_model=ApprovalResponse)
async def get_approval(
    approval_id: UUID,
    current_user: dict = Depends(get_current_user),
    service: ApprovalService = Depends(get_approval_service),
):
    """Get approval by ID."""
    try:
        result = await service.get_approval(str(approval_id))
        if not result:
            raise HTTPException(status_code=404, detail="Approval not found")

        # Check permissions
        if current_user["role"] not in ["admin", "supervisor"] and result.get("requested_by") != current_user["id"]:
            raise HTTPException(status_code=403, detail="Not authorized to view this approval")

        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{approval_id}/approve", response_model=dict)
async def approve(
    approval_id: UUID,
    decision: dict,
    current_user: dict = Depends(require_approver),
    service: ApprovalService = Depends(get_approval_service),
):
    """Approve a pending request."""
    if not decision.get("approved", True):
        raise HTTPException(status_code=400, detail="Use reject endpoint for rejection")

    try:
        result = await service.approve(approval_id, decision, current_user["id"])
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Failed to approve"))
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{approval_id}/reject", response_model=dict)
async def reject(
    approval_id: UUID,
    decision: dict,
    current_user: dict = Depends(require_approver),
    service: ApprovalService = Depends(get_approval_service),
):
    """Reject a pending request."""
    if not decision.get("comment"):
        raise HTTPException(status_code=400, detail="Comment required when rejecting")

    try:
        result = await service.reject(approval_id, decision, current_user["id"])
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Failed to reject"))
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{approval_id}/cancel")
async def cancel_approval(
    approval_id: UUID,
    current_user: dict = Depends(get_current_user),
    service: ApprovalService = Depends(get_approval_service),
):
    """Cancel own pending approval request."""
    try:
        result = await service.cancel(str(approval_id), current_user["id"])
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Failed to cancel"))
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats/summary")
async def get_stats_summary(
    service: ApprovalService = Depends(get_approval_service),
):
    """Get approval statistics summary."""
    try:
        return await service.get_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
