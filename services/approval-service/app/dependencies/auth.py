"""Authentication dependencies for approval service."""
from typing import Optional
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.config import settings

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    """Get current user from API key (development version)."""
    # In development, allow any token or no token
    if settings.ENVIRONMENT == "development":
        return {"id": "dev-user", "role": "admin"}
    
    # Production: validate API key
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # TODO: Validate API key against database
    # For now, accept any token in production too
    return {"id": "api-user", "role": "user"}


async def require_approver(current_user: dict = Depends(get_current_user)) -> dict:
    """Require user to have approver role."""
    if current_user.get("role") not in ["admin", "supervisor", "approver"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Approver role required",
        )
    return current_user


async def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """Require user to have admin role."""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )
    return current_user