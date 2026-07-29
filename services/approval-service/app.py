"""
Servicio de Aprobaciones - Sistema de aprobación humana para acciones sensibles.
"""
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from uuid import uuid4
import structlog

logger = structlog.get_logger()


class ApprovalService:
    """
    Servicio de Aprobaciones Humanas.
    
    Gestiona el flujo completo de aprobaciones para acciones sensibles:
    - Publicar anuncios
    - Cambiar precios
    - Aplicar descuentos
    - Confirmar reservas
    - Validar facturas
    - Emitir rectificativas
    - Anular facturas
    - Presentar impuestos
    - Realizar pagos
    - Modificar plan contable
    - Modificar tipos impositivos
    - Modificar datos fiscales
    - Lanzar campañas pagadas
    - Actualizar producción
    - Borrar datos
    - Exportar grandes volúmenes
    """
    
    def __init__(self, config: Dict):
        self.config = config
        self.approvals: Dict[str, Dict] = {}  # En memoria - en prod: BD
        self.notification_webhook = config.get("NOTIFICATION_WEBHOOK_URL")
        self.notification_secret = config.get("NOTIFICATION_WEBHOOK_SECRET")
    
    async def request_approval(self, data: Dict) -> Dict:
        """Crear solicitud de aprobación."""
        approval_id = str(uuid4())
        
        # Validar acción permitida
        allowed_actions = [
            "publish", "price_change", "discount", "confirm_reservation",
            "validate_invoice", "rectify_invoice", "cancel_invoice",
            "present_taxes", "make_payment", "modify_chart_accounts",
            "modify_tax_rates", "modify_fiscal_data", "launch_paid_campaign",
            "update_production", "delete_data", "bulk_export",
        ]
        
        action = data.get("action")
        if action not in allowed_actions:
            return {"success": False, "error": f"Acción no permitida: {action}"}
        
        # Determinar prioridad y expiración
        priority_map = {
            "publish": "high",
            "price_change": "high",
            "discount": "medium",
            "confirm_reservation": "high",
            "validate_invoice": "high",
            "rectify_invoice": "high",
            "cancel_invoice": "critical",
            "present_taxes": "critical",
            "make_payment": "high",
            "modify_chart_accounts": "critical",
            "modify_tax_rates": "critical",
            "modify_fiscal_data": "critical",
            "launch_paid_campaign": "medium",
            "update_production": "critical",
            "delete_data": "critical",
            "bulk_export": "medium",
        }
        
        priority = priority_map.get(data.get("action"), "medium")
        
        # Expiración según prioridad
        expiry_hours = {"critical": 2, "high": 8, "medium": 24, "low": 72}
        expires_at = datetime.now() + timedelta(hours=expiry_hours.get(priority, 24))
        
        approval = {
            "id": str(uuid4()),
            "action": action,
            "action_type": data.get("action_type"),
            "reason": data.get("reason", ""),
            "current_state": data.get("current_state", {}),
            "proposed_state": data.get("proposed_state", {}),
            "risk_level": data.get("risk_level", "medium"),
            "risk_factors": data.get("risk_factors", []),
            "evidence_urls": data.get("evidence_urls", []),
            "evidence_notes": data.get("evidence_notes", ""),
            "requested_by": data.get("requester_id"),
            "requested_at": datetime.now().isoformat(),
            "expires_at": expires_at.isoformat(),
            "auto_approve_at": None,
            "auto_reject_at": None,
            "status": "pending",
            "priority": priority,
            "notifications_sent": False,
            "metadata": data.get("metadata", {}),
            "idempotency_key": data.get("idempotency_key"),
        }
        
        self.approvals[approval["id"]] = approval
        
        # Notificar a aprobadores
        await self._notify_approvers(approval)
        
        return {
            "success": True,
            "approval_id": approval["id"],
            "status": "pending",
            "expires_at": expires_at.isoformat(),
            "message": "Solicitud de aprobación creada",
        }
    
    async def approve(self, approval_id: str, decision: Dict) -> Dict:
        """Aprobar solicitud."""
        approval = self.approvals.get(approval_id)
        if not approval:
            return {"success": False, "error": "Aprobación no encontrada"}
        
        if approval["status"] != "pending":
            return {"success": False, "error": f"Aprobación ya {approval['status']}"}
        
        if datetime.now() > datetime.fromisoformat(approval["expires_at"]):
            approval["status"] = "expired"
            return {"success": False, "error": "Aprobación expirada"}
        
        approved = decision.get("approved", True)
        comment = decision.get("comment", "")
        
        if not approved and not comment:
            return {"success": False, "error": "Comentario requerido al rechazar"}
        
        approval["status"] = "approved" if approved else "rejected"
        approval["approved_by"] = decision.get("approver_id")
        approval["approved_at"] = datetime.now().isoformat()
        approval["approval_comment"] = comment
        approval["rejection_reason"] = "" if approved else comment
        
        # Ejecutar acción aprobada
        if approved:
            result = await self._execute_approved_action(approval)
            approval["execution_result"] = result
        
        # Notificar al solicitante
        await self._notify_requester(approval)
        
        return {
            "success": True,
            "approval_id": approval_id,
            "status": approval["status"],
            "message": "Aprobación procesada",
        }
    
    async def reject(self, approval_id: str, decision: Dict) -> Dict:
        """Rechazar solicitud."""
        decision["approved"] = False
        return await self.approve(approval_id, decision)
    
    async def cancel(self, approval_id: str, requester_id: str) -> Dict:
        """Cancelar solicitud propia (solo si pendiente)."""
        approval = self.approvals.get(approval_id)
        if not approval:
            return {"success": False, "error": "Aprobación no encontrada"}
        
        if approval["status"] != "pending":
            return {"success": False, "error": "Solo se pueden cancelar solicitudes pendientes"}
        
        if approval["requested_by"] != requester_id:
            return {"success": False, "error": "Solo el solicitante puede cancelar"}
        
        approval["status"] = "cancelled"
        approval["cancelled_at"] = datetime.now().isoformat()
        approval["cancelled_by"] = requester_id
        
        return {"success": True, "message": "Solicitud cancelada"}
    
    async def get_pending(self, user_id: str = None) -> List[Dict]:
        """Obtener aprobaciones pendientes."""
        approvals = [a for a in self.approvals.values() if a["status"] == "pending"]
        
        # Filtrar por usuario si se proporciona
        if user_id:
            approvals = [a for a in approvals if a.get("requested_by") == user_id]
        
        # Ordenar por prioridad y fecha
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        approvals.sort(key=lambda x: (priority_order.get(x["priority"], 99), x["created_at"]))
        
        return approvals
    
    async def get_my_pending(self, user_id: str) -> List[Dict]:
        """Obtener mis aprobaciones pendientes."""
        return await self.get_pending(user_id)
    
    async def get_stats(self) -> Dict:
        """Estadísticas de aprobaciones."""
        today = datetime.now().date().isoformat()
        
        stats = {
            "pending": 0,
            "approved_today": 0,
            "rejected_today": 0,
            "avg_resolution_hours": 0,
            "by_action": {},
            "by_priority": {},
        }
        
        for a in self.approvals.values():
            if a["status"] == "pending":
                stats["pending"] += 1
            if a["status"] == "approved" and a.get("approved_at", "").startswith(today):
                stats["approved_today"] += 1
            if a["status"] == "rejected" and a.get("approved_at", "").startswith(today):
                stats["rejected_today"] += 1
            
            stats["by_action"][a["action"]] = stats["by_action"].get(a["action"], 0) + 1
            stats["by_priority"][a["priority"]] = stats["by_priority"].get(a["priority"], 0) + 1
        
        return {"success": True, "stats": stats}
    
    async def _execute_approved_action(self, approval: Dict) -> Dict:
        """Ejecutar acción aprobada (llamar al servicio correspondiente)."""
        action = approval["action"]
        
        # Mapeo de acciones a servicios/métodos
        action_map = {
            "publish": ("publishing", "publish"),
            "price_change": ("products", "change_price"),
            "discount": ("sales", "apply_discount"),
            "confirm_reservation": ("sales", "confirm_reservation"),
            "validate_invoice": ("invoicing", "validate_invoice"),
            "rectify_invoice": ("invoicing", "create_rectification"),
            "cancel_invoice": ("invoicing", "cancel_invoice"),
            "present_taxes": ("tax", "submit_taxes"),
            "make_payment": ("banking", "make_payment"),
            "modify_chart_accounts": ("accounting", "modify_chart"),
            "modify_tax_rates": ("tax", "modify_rates"),
            "modify_fiscal_data": ("accounting", "modify_fiscal_data"),
            "launch_paid_campaign": ("marketing", "launch_campaign"),
            "update_production": ("technical", "deploy_production"),
            "delete_data": ("technical", "delete_data"),
            "bulk_export": ("technical", "export_data"),
        }
        
        service, method = action_map.get(action, (None, None))
        
        if not service or not method:
            return {"success": False, "error": f"Acción no mapeada: {action}"}
        
        # TODO: Llamar al servicio correspondiente via message queue / HTTP
        # Por ahora simulamos éxito
        logger.info("executing_approved_action", action=action, service=service, method=method)
        
        return {"success": True, "service": service, "method": method, "simulated": True}
    
    async def _notify_approvers(self, approval: Dict):
        """Notificar a aprobadores."""
        # TODO: Enviar notificación por Telegram/Slack/Email
        # Canales según prioridad:
        # - critical: Telegram + Slack + SMS + Llamada
        # - high: Telegram + Slack
        # - medium: Slack + Email
        # - low: Email
        
        logger.info("approval_notification_sent", approval_id=approval["id"], priority=approval["priority"])
    
    async def _notify_requester(self, approval: Dict):
        """Notificar al solicitante del resultado."""
        logger.info("requester_notified", approval_id=approval["id"], status=approval["status"])
    
    async def check_expired(self):
        """Verificar y expirar aprobaciones vencidas (ejecutar periódicamente)."""
        now = datetime.now()
        expired = 0
        
        for approval in self.approvals.values():
            if approval["status"] == "pending" and datetime.fromisoformat(approval["expires_at"]) < datetime.now():
                approval["status"] = "expired"
                expired += 1
                # Notificar al solicitante
                await self._notify_requester(approval)
        
        return {"expired_count": expired}
    
    def get_approval(self, approval_id: str) -> Optional[Dict]:
        """Obtener aprobación por ID."""
        return self.approvals.get(approval_id)


# Instancia global
_approval_service = None


def get_approval_service(config: Optional[Dict] = None) -> ApprovalService:
    global _approval_service
    if _approval_service is None:
        _approval_service = ApprovalService(config or {})
    return _approval_service


async def start_approval_service(config: Optional[Dict] = None):
    global _approval_service
    _approval_service = ApprovalService(config or {})
    await _approval_service.start()
    return _approval_service


async def stop_approval_service():
    global _approval_service
    if _approval_service:
        await _approval_service.stop()
        _approval_service = None