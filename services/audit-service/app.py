"""
Servicio de Auditoría - Registro inmutable de operaciones.
"""
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from uuid import uuid4
import structlog
import hashlib
import json

logger = structlog.get_logger()


class AuditService:
    """
    Servicio de Auditoría - Registro inmutable de todas las operaciones.
    
    Características:
    - Registro inmutable (append-only)
    - Hash chain para integridad
    - Consultas con filtros
    - Resúmenes y estadísticas
    - Limpieza automática (retención configurable)
    """
    
    def __init__(self, config: Dict):
        self.config = config
        self.retention_days = config.get("AUDIT_RETENTION_DAYS", 90)
    
    async def start(self):
        logger.info("starting_audit_service")
    
    async def stop(self):
        pass
    
    async def log_event(self, event: Dict) -> Dict:
        """Registrar evento de auditoría."""
        event_id = str(uuid4())
        
        # Calcular hashes para integridad
        request_body_hash = None
        if event.get("request_body"):
            request_body_hash = hashlib.sha256(
                json.dumps(event["request_body"], sort_keys=True).encode()
            ).hexdigest()
        
        new_state_hash = None
        if event.get("new_state"):
            new_state_hash = hashlib.sha256(
                json.dumps(event["new_state"], sort_keys=True).encode()
            ).hexdigest()
        
        previous_state_hash = None
        if event.get("previous_state"):
            previous_state_hash = hashlib.sha256(
                json.dumps(event["previous_state"], sort_keys=True).encode()
            ).hexdigest()
        
        # Calcular diff
        diff = None
        if event.get("previous_state") and event.get("new_state"):
            diff = self._calculate_diff(event["previous_state"], event["new_state"])
        
        # Obtener hash anterior para cadena
        previous_hash = await self._get_last_hash()
        current_hash = hashlib.sha256(
            f"{previous_hash}{event_id}{datetime.now().isoformat()}".encode()
        ).hexdigest()
        
        audit_entry = {
            "id": event_id,
            "created_at": datetime.now().isoformat(),
            "request_id": event.get("request_id", str(uuid4())),
            "correlation_id": event.get("correlation_id"),
            "agent_id": event.get("agent_id"),
            "agent_name": event.get("agent_name"),
            "agent_roles": event.get("agent_roles", []),
            "api_key_hash": event.get("api_key_hash"),
            "method": event.get("method"),
            "path": event.get("path"),
            "query_params": event.get("query_params", {}),
            "request_body_hash": request_body_hash,
            "resource_type": event.get("resource_type"),
            "resource_id": event.get("resource_id"),
            "action": event.get("action"),
            "previous_state_hash": previous_state_hash,
            "new_state_hash": new_state_hash,
            "diff": diff,
            "status_code": event.get("status_code"),
            "success": event.get("success", True),
            "error_code": event.get("error_code"),
            "error_message": event.get("error_message"),
            "error_details": event.get("error_details"),
            "duration_ms": event.get("duration_ms"),
            "idempotency_key": event.get("idempotency_key"),
            "idempotent": event.get("idempotent", False),
            "correlation_id": event.get("correlation_id"),
            "ip_address": event.get("ip_address"),
            "user_agent": event.get("user_agent"),
            "previous_hash": previous_hash,
            "current_hash": current_hash,
        }
        
        # TODO: Guardar en BD (PostgreSQL audit_log)
        # await db.insert_audit_log(audit_entry)
        
        logger.info("audit_logged", event_id=event_id, action=event.get("action"))
        
        return {"success": True, "audit_id": event_id, "hash": current_hash}
    
    def _calculate_diff(self, old: Dict, new: Dict) -> Dict:
        """Calcular diferencia entre dos estados."""
        diff = {"added": {}, "removed": {}, "changed": {}}
        all_keys = set(old.keys()) | set(new.keys())
        
        for key in all_keys:
            old_val = old.get(key)
            new_val = new.get(key)
            
            if key not in old:
                diff["added"][key] = new_val
            elif key not in new:
                diff["removed"][key] = old_val
            elif old_val != new_val:
                diff["changed"][key] = {"from": old_val, "to": new_val}
        
        return diff
    
    async def _get_last_hash(self) -> str:
        """Obtener hash del último registro para cadena."""
        # TODO: Consultar BD
        return "genesis"
    
    async def query_logs(self, filters: Dict = None, limit: int = 100, offset: int = 0) -> List[Dict]:
        """Consultar logs de auditoría con filtros."""
        # TODO: Implementar consulta a BD
        return []
    
    async def get_summary(self, start_date: datetime, end_date: datetime) -> Dict:
        """Obtener resumen de actividad."""
        # TODO: Consultar BD
        return {
            "period": {"from": start_date.isoformat(), "to": end_date.isoformat()},
            "total_events": 0,
            "successful": 0,
            "failed": 0,
            "unique_agents": 0,
            "avg_duration_ms": 0,
        }
    
    async def cleanup_old_logs(self, retention_days: int = None) -> int:
        """Limpiar logs antiguos."""
        days = retention_days or self.retention_days
        # TODO: Ejecutar DELETE en BD
        deleted = 0
        logger.info("audit_cleanup", deleted=deleted, retention_days=days)
        return deleted
    
    async def verify_integrity(self) -> Dict:
        """Verificar integridad de la cadena de hash."""
        # TODO: Verificar cadena completa
        return {
            "success": True,
            "verified": True,
            "total_records": 0,
            "broken_chain": False,
        }


# Instancia global
_audit_service = None


def get_audit_service(config: Optional[Dict] = None) -> "AuditService":
    global _audit_service
    if _audit_service is None:
        _audit_service = AuditService(config or {})
    return _audit_service


async def start_audit_service(config: Optional[Dict] = None):
    global _audit_service
    _audit_service = AuditService(config or {})
    await _audit_service.start()
    return _audit_service


async def stop_audit_service():
    global _audit_service
    if _audit_service:
        await _audit_service.stop()
        _audit_service = None