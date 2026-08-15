"""
Excepciones personalizadas de la aplicación.
"""

from typing import Any


class TransvegaException(Exception):
    """Excepción base de la aplicación."""

    def __init__(
        self,
        message: str,
        error_code: str = "TRANSVEGA_ERROR",
        status_code: int = 500,
        details: dict[str, Any] | None = None,
    ):
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


class ValidationException(TransvegaException):
    """Error de validación de datos de entrada."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            error_code="VALIDATION_ERROR",
            status_code=422,
            details=details,
        )


class AuthenticationException(TransvegaException):
    """Error de autenticación."""

    def __init__(self, message: str = "Credenciales inválidas", details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            error_code="AUTHENTICATION_ERROR",
            status_code=401,
            details=details,
        )


class AuthorizationException(TransvegaException):
    """Error de autorización - permisos insuficientes."""

    def __init__(self, message: str = "Permisos insuficientes", details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            error_code="AUTHORIZATION_ERROR",
            status_code=403,
            details=details,
        )


class NotFoundException(TransvegaException):
    """Recurso no encontrado."""

    def __init__(self, resource: str, identifier: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=f"{resource} no encontrado: {identifier}",
            error_code="NOT_FOUND",
            status_code=404,
            details={"resource": resource, "identifier": identifier, **(details or {})},
        )


class IdempotencyException(TransvegaException):
    """Error de idempotencia - operación duplicada."""

    def __init__(self, key: str, existing_id: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=f"Operación duplicada detectada para clave: {key}",
            error_code="IDEMPOTENCY_CONFLICT",
            status_code=409,
            details={
                "idempotency_key": key,
                "existing_resource_id": existing_id,
                **(details or {}),
            },
        )


class DolibarrException(TransvegaException):
    """Error en comunicación con Dolibarr."""

    def __init__(
        self,
        message: str,
        endpoint: str = "",
        status_code: int = 502,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(
            message=f"Error Dolibarr: {message}",
            error_code="DOLIBARR_ERROR",
            status_code=status_code,
            details={"endpoint": endpoint, **(details or {})},
        )


class ApprovalRequiredException(TransvegaException):
    """Acción requiere aprobación humana."""

    def __init__(self, action: str, approval_id: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=f"Acción '{action}' requiere aprobación humana (ID: {approval_id})",
            error_code="APPROVAL_REQUIRED",
            status_code=409,
            details={"action": action, "approval_id": approval_id, **(details or {})},
        )


class RateLimitException(TransvegaException):
    """Límite de tasa excedido."""

    def __init__(self, limit: int, window: int, retry_after: int):
        super().__init__(
            message=f"Límite de tasa excedido: {limit} requests per {window}s",
            error_code="RATE_LIMIT_EXCEEDED",
            status_code=429,
            details={
                "limit": limit,
                "window_seconds": window,
                "retry_after_seconds": retry_after,
            },
        )


class BusinessRuleException(TransvegaException):
    """Violación de regla de negocio."""

    def __init__(self, rule: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=f"Regla de negocio violada [{rule}]: {message}",
            error_code="BUSINESS_RULE_VIOLATION",
            status_code=422,
            details={"rule": rule, **(details or {})},
        )


class AgentNotFoundException(NotFoundException):
    """Agente no encontrado."""

    def __init__(self, agent_id: str):
        super().__init__(resource="Agent", identifier=agent_id)


class ApprovalNotFoundException(NotFoundException):
    """Aprobación no encontrada."""

    def __init__(self, approval_id: str):
        super().__init__(resource="Approval", identifier=approval_id)


class ExpedienteNotFoundException(NotFoundException):
    """Expediente no encontrado."""

    def __init__(self, expediente_id: str):
        super().__init__(resource="Expediente", identifier=expediente_id)
