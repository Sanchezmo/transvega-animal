"""
Dependencias de autenticación y autorización.
"""
from typing import Optional, List
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.exceptions import AuthenticationException, AuthorizationException


security = HTTPBearer(auto_error=False)

# Mapeo de API keys a roles/agentes
AGENT_ROLES = {
    "supervisor": ["supervisor", "admin"],
    "products": ["products", "read"],
    "compliance": ["compliance", "read"],
    "publishing": ["publishing", "read"],
    "sales": ["sales", "read"],
    "invoicing": ["invoicing", "read"],
    "purchases": ["purchases", "read"],
    "banking": ["banking", "read"],
    "accounting": ["accounting", "read"],
    "tax": ["tax", "read"],
    "marketing": ["marketing", "read"],
    "technical": ["technical", "read"],
}


class AgentIdentity:
    """Identidad del agente autenticado."""
    
    def __init__(
        self,
        agent_id: str,
        agent_name: str,
        roles: list[str],
        api_key: str,
    ):
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.roles = roles
        self.api_key = api_key
    
    def has_role(self, role: str) -> bool:
        return role in self.roles or "admin" in self.roles
    
    def has_any_role(self, roles: list[str]) -> bool:
        return any(r in self.roles for r in roles) or "admin" in self.roles


async def get_current_agent(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> AgentIdentity:
    """
    Autentica y valida la identidad del agente via API Key o JWT.
    
    Soporta dos métodos:
    1. API Key en header: Authorization: Bearer ***
    2. JWT token en header: Authorization: Bearer ***
    """
    if not credentials:
        raise AuthenticationException("Credenciales requeridas")
    
    token = credentials.credentials
    
    # Intentar como API Key (formato: tvsk_...)
    if token.startswith("tvsk_"):
        return await _verify_api_key(token)
    
    # Intentar como JWT
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        agent_id = payload.get("sub")
        agent_name = payload.get("agent_name")
        roles = payload.get("roles", [])
        
        if not agent_id or not agent_name:
            raise AuthenticationException("Token JWT inválido")
        
        return AgentIdentity(
            agent_id=agent_id,
            agent_name=agent_name,
            roles=roles,
            api_key="",
        )
    except JWTError:
        raise AuthenticationException("Token inválido o expirado")


async def _verify_api_key(api_key: str) -> AgentIdentity:
    """Verifica API key contra configuración."""
    settings = get_settings()
    
    for agent_name, expected_key in settings.get_agent_api_keys().items():
        if expected_key and api_key == expected_key:
            roles = AGENT_ROLES.get(agent_name, ["read"])
            return AgentIdentity(
                agent_id=f"agent_{agent_name}",
                agent_name=agent_name,
                roles=roles,
                api_key=api_key[:8] + "..." + api_key[-4:],
            )
    
    raise AuthenticationException("API Key inválida")


def require_role(required_roles: List[str]):
    """Dependency factory para requerir roles específicos."""
    async def _check_role(agent: AgentIdentity = Depends(get_current_agent)) -> AgentIdentity:
        if not agent.has_any_role(required_roles):
            raise AuthorizationException(
                f"Se requiere uno de los roles: {required_roles}"
            )
        return agent
    return _check_role


# Dependencias predefinidas para roles comunes
require_supervisor = require_role(["supervisor", "admin"])
require_admin = require_role(["admin"])
require_write = require_role(["write", "admin"])
require_financial = require_role(["invoicing", "accounting", "tax", "admin"])