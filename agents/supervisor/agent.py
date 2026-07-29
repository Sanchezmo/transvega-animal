"""
Agente Supervisor - Coordinador principal del sistema multi-agente.
"""
import asyncio
import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from uuid import uuid4
from enum import Enum
import structlog

logger = structlog.get_logger()


class AgentRole(str):
    SUPERVISOR = "supervisor"
    PRODUCTS = "products"
    COMPLIANCE = "compliance"
    PUBLISHING = "publishing"
    SALES = "sales"
    INVOICING = "invoicing"
    PURCHASES = "purchases"
    BANKING = "banking"
    ACCOUNTING = "accounting"
    TAX = "tax"
    MARKETING = "marketing"
    TECHNICAL = "technical"


class TaskPriority(int):
    LOW = 1
    NORMAL = 5
    HIGH = 8
    CRITICAL = 10


class AgentStatus(str):
    IDLE = "idle"
    BUSY = "busy"
    ERROR = "error"
    OFFLINE = "offline"


class ConflictType(str):
    DUPLICATE_TASK = "duplicate_task"
    RESOURCE_CONFLICT = "resource_conflict"
    STATE_CONFLICT = "state_conflict"
    PERMISSION_CONFLICT = "permission_conflict"
    DATA_INCONSISTENCY = "data_inconsistency"


class SupervisorAgent:
    """
    Agente Supervisor - Coordinador central del sistema multi-agente.
    
    Responsabilidades:
    - Recibir eventos y asignar tareas
    - Aplicar reglas de autorización
    - Detectar conflictos
    - Evitar duplicados
    - Registrar decisiones
    - Escalar excepciones
    - Detener acciones anómalas
    - Generar resumen diario
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.agent_id = "supervisor"
        self.agent_name = "Supervisor"
        self.status = AgentStatus.IDLE
        
        # Registro de agentes
        self.agents: Dict[str, Dict] = {}
        
        # Cola de tareas pendientes
        self.task_queue: asyncio.Queue = asyncio.Queue()
        
        # Historial de decisiones
        self.decision_log: List[Dict] = []
        
        # Conflictos detectados
        self.conflicts: List[Dict] = []
        
        # Reglas de autorización
        self.authorization_rules = self._load_authorization_rules()
        
        # Configuración
        self.max_concurrent_tasks_per_agent = config.get("max_concurrent_tasks", 5)
        self.task_timeout = config.get("task_timeout", 3600)
        self.duplicate_detection_window = config.get("duplicate_window", 300)  # 5 min
        
        # Estadísticas
        self.stats = {
            "tasks_assigned": 0,
            "tasks_completed": 0,
            "tasks_failed": 0,
            "conflicts_detected": 0,
            "conflicts_resolved": 0,
            "approvals_requested": 0,
            "approvals_approved": 0,
            "approvals_rejected": 0,
        }
    
    def _load_authorization_rules(self) -> Dict:
        """Cargar reglas de autorización desde configuración."""
        return {
            "products": {
                "create": ["products", "supervisor", "admin"],
                "update": ["products", "supervisor", "admin"],
                "delete": ["supervisor", "admin"],
                "publish": ["products", "supervisor", "admin"],  # Requiere aprobación
                "price_change": ["products", "supervisor", "admin"],  # Requiere aprobación
            },
            "compliance": {
                "validate": ["compliance", "supervisor", "admin"],
                "override": ["supervisor", "admin"],
            },
            "publishing": {
                "create_draft": ["publishing", "products", "supervisor", "admin"],
                "publish": ["publishing", "supervisor", "admin"],  # Requiere aprobación
                "unpublish": ["publishing", "products", "supervisor", "admin"],
                "renew": ["publishing", "products", "supervisor", "admin"],
            },
            "sales": {
                "create_lead": ["sales", "supervisor", "admin"],
                "qualify_lead": ["sales", "supervisor", "admin"],
                "create_reservation": ["sales", "supervisor", "admin"],  # Requiere aprobación si >50%
                "create_order": ["sales", "supervisor", "admin"],
                "create_quote": ["sales", "supervisor", "admin"],
            },
            "invoicing": {
                "create_draft": ["invoicing", "accounting", "supervisor", "admin"],
                "validate": ["invoicing", "accounting", "supervisor", "admin"],  # Requiere aprobación
                "cancel": ["invoicing", "accounting", "supervisor", "admin"],  # Requiere aprobación
                "rectify": ["invoicing", "accounting", "supervisor", "admin"],  # Requiere aprobación
                "register_payment": ["invoicing", "accounting", "supervisor", "admin"],
            },
            "purchases": {
                "create_draft": ["purchases", "accounting", "supervisor", "admin"],
                "validate": ["purchases", "accounting", "supervisor", "admin"],
            },
            "banking": {
                "import_movements": ["banking", "accounting", "supervisor", "admin"],
                "reconcile": ["banking", "accounting", "supervisor", "admin"],
            },
            "accounting": {
                "propose_entry": ["accounting", "supervisor", "admin"],
                "validate_entry": ["accounting", "supervisor", "admin"],
            },
            "tax": {
                "prepare_return": ["tax", "accounting", "supervisor", "admin"],
                "submit_return": ["tax", "accounting", "supervisor", "admin"],  # Requiere aprobación
            },
            "marketing": {
                "create_campaign": ["marketing", "supervisor", "admin"],
                "launch_campaign": ["marketing", "supervisor", "admin"],  # Requiere aprobación
                "modify_budget": ["marketing", "supervisor", "admin"],  # Requiere aprobación
            },
            "technical": {
                "monitor": ["technical", "supervisor", "admin"],
                "backup": ["technical", "supervisor", "admin"],
                "update_staging": ["technical", "supervisor", "admin"],
                "update_production": ["technical", "supervisor", "admin"],  # Requiere aprobación
            },
            "supervisor": {
                "manage_agents": ["supervisor", "admin"],
                "override_decision": ["admin"],
                "emergency_stop": ["supervisor", "admin"],
            },
        }
    
    async def start(self):
        """Iniciar agente supervisor."""
        logger.info("starting_supervisor", agent_id=self.agent_id)
        self.status = AgentStatus.IDLE
        
        # Iniciar workers
        asyncio.create_task(self._process_task_queue())
        asyncio.create_task(self._monitor_agents())
        asyncio.create_task(self._cleanup_old_tasks())
        
        logger.info("supervisor_started")
    
    async def stop(self):
        """Detener agente supervisor."""
        logger.info("stopping_supervisor")
        self.status = AgentStatus.OFFLINE
    
    def register_agent(self, agent_id: str, agent_info: Dict):
        """Registrar un agente en el sistema."""
        self.agents[agent_id] = {
            **agent_info,
            "status": AgentStatus.IDLE,
            "registered_at": datetime.now().isoformat(),
            "last_heartbeat": datetime.now().isoformat(),
            "current_tasks": [],
            "completed_tasks": 0,
            "failed_tasks": 0,
        }
        logger.info("agent_registered", agent_id=agent_id, agent_name=agent_info.get("name"))
    
    def unregister_agent(self, agent_id: str):
        """Desregistrar un agente."""
        if agent_id in self.agents:
            del self.agents[agent_id]
            logger.info("agent_unregistered", agent_id=agent_id)
    
    async def agent_heartbeat(self, agent_id: str, status: str = AgentStatus.IDLE, 
                             current_task: Optional[str] = None):
        """Recibir heartbeat de un agente."""
        if agent_id in self.agents:
            self.agents[agent_id]["last_heartbeat"] = datetime.now().isoformat()
            self.agents[agent_id]["status"] = status
            if current_task:
                if current_task not in self.agents[agent_id]["current_tasks"]:
                    self.agents[agent_id]["current_tasks"].append(current_task)
            else:
                self.agents[agent_id]["current_tasks"] = []
    
    async def submit_task(self, task: Dict) -> Dict:
        """
        Enviar tarea para procesamiento.
        
        Aplica:
        - Detección de duplicados
        - Verificación de permisos
        - Detección de conflictos
        - Asignación a agente apropiado
        """
        task_id = task.get("task_id", str(uuid4()))
        task_type = task.get("task_type", "unknown")
        agent_id = task.get("agent_id")
        required_roles = task.get("required_roles", [])
        idempotency_key = task.get("idempotency_key")
        
        # 1. Verificar duplicados por idempotency_key
        if idempotency_key:
            duplicate = await self._check_duplicate(idempotency_key)
            if duplicate:
                logger.warning("duplicate_task_detected", task_id=task_id, 
                             idempotency_key=idempotency_key)
                self.stats["tasks_failed"] += 1
                return {
                    "success": False,
                    "error": "DUPLICATE_TASK",
                    "message": "Tarea duplicada detectada",
                    "existing_task_id": duplicate["task_id"],
                }
        
        # 2. Verificar permisos del agente
        if agent_id and not self._check_permissions(agent_id, task_type, required_roles):
            logger.warning("permission_denied", agent_id=agent_id, task_type=task_type)
            return {
                "success": False,
                "error": "PERMISSION_DENIED",
                "message": f"Agente {agent_id} no tiene permisos para {task_type}",
            }
        
        # 3. Detectar conflictos
        conflicts = await self._detect_conflicts(task)
        if conflicts:
            logger.warning("conflicts_detected", task_id=task_id, conflicts=conflicts)
            self.stats["conflicts_detected"] += 1
            
            # Si hay conflictos críticos, requerir resolución manual
            critical_conflicts = [c for c in conflicts if c.get("severity") == "critical"]
            if critical_conflicts:
                return {
                    "success": False,
                    "error": "CONFLICT_DETECTED",
                    "message": "Conflictos críticos detectados, requiere resolución manual",
                    "conflicts": critical_conflicts,
                }
        
        # 4. Verificar si requiere aprobación humana
        requires_approval = self._requires_approval(task_type, task.get("action"))
        if requires_approval:
            approval_id = await self._request_approval(task)
            return {
                "success": True,
                "message": "Tarea requiere aprobación humana",
                "task_id": task_id,
                "approval_id": approval_id,
                "status": "waiting_approval",
            }
        
        # 5. Asignar a agente
        assigned_agent = await self._assign_agent(task_type, agent_id)
        if not assigned_agent:
            return {
                "success": False,
                "error": "NO_AGENT_AVAILABLE",
                "message": f"No hay agente disponible para {task_type}",
            }
        
        # 6. Encolar tarea
        task["task_id"] = task_id
        task["assigned_agent"] = assigned_agent
        task["status"] = "queued"
        task["created_at"] = datetime.now().isoformat()
        task["idempotency_key"] = idempotency_key
        
        await self.task_queue.put(task)
        
        # Actualizar estadísticas
        self.stats["tasks_assigned"] += 1
        self.agents[assigned_agent]["current_tasks"].append(task_id)
        
        # Log de decisión
        self._log_decision({
            "timestamp": datetime.now().isoformat(),
            "decision": "task_assigned",
            "task_id": task_id,
            "task_type": task_type,
            "assigned_agent": assigned_agent,
            "requires_approval": requires_approval,
            "conflicts": conflicts,
        })
        
        logger.info("task_assigned", task_id=task_id, agent=assigned_agent, 
                   task_type=task_type, requires_approval=requires_approval)
        
        return {
            "success": True,
            "task_id": task_id,
            "assigned_agent": assigned_agent,
            "status": "queued",
        }
    
    async def _check_duplicate(self, idempotency_key: str) -> Optional[Dict]:
        """Verificar si ya existe una tarea con la misma clave de idempotencia."""
        # TODO: Implementar búsqueda en BD/Redis
        return None
    
    def _check_permissions(self, agent_id: str, task_type: str, required_roles: List[str]) -> bool:
        """Verificar si el agente tiene permisos para la tarea."""
        if agent_id not in self.agents:
            return False
        
        agent_roles = self.agents[agent_id].get("roles", [])
        task_rules = self.authorization_rules.get(task_type, {})
        
        # Verificar roles requeridos
        for role in required_roles:
            if role not in agent_roles:
                return False
        
        # Verificar reglas específicas de la tarea
        if "roles" in task_rules:
            allowed = False
            for rule_role in task_rules["roles"]:
                if rule_role in agent_roles:
                    allowed = True
                    break
            if not allowed:
                return False
        
        return True
    
    async def _detect_conflicts(self, task: Dict) -> List[Dict]:
        """Detectar conflictos potenciales."""
        conflicts = []
        
        task_type = task.get("task_type")
        resource_id = task.get("resource_id")
        resource_type = task.get("resource_type")
        
        if not resource_id:
            return conflicts
        
        # Verificar si otro agente está trabajando en el mismo recurso
        for agent_id, agent_info in self.agents.items():
            for current_task_id in agent_info.get("current_tasks", []):
                # TODO: Obtener info de la tarea actual y comparar recursos
                pass
        
        # Verificar estado del recurso en Dolibarr
        # TODO: Consultar estado actual
        
        return conflicts
    
    def _requires_approval(self, task_type: str, action: str) -> bool:
        """Determinar si una acción requiere aprobación humana."""
        approval_required = {
            "products": ["publish", "price_change", "delete"],
            "publishing": ["publish", "unpublish"],
            "sales": ["confirm_reservation", "apply_discount"],
            "invoicing": ["validate", "cancel", "rectify"],
            "purchases": ["validate"],
            "tax": ["submit_return"],
            "marketing": ["launch_campaign", "modify_budget"],
            "technical": ["update_production", "restart_service"],
            "supervisor": ["emergency_stop", "override_decision"],
        }
        
        return action in approval_required.get(task_type, [])
    
    async def _request_approval(self, task: Dict) -> str:
        """Solicitar aprobación humana."""
        approval_id = str(uuid4())
        
        # TODO: Enviar a servicio de aprobaciones
        # await approval_service.request(...)
        
        self.stats["approvals_requested"] += 1
        return approval_id
    
    async def _assign_agent(self, task_type: str, preferred_agent: Optional[str]) -> Optional[str]:
        """Asignar mejor agente para la tarea."""
        # Si hay agente preferido y está disponible
        if preferred_agent and preferred_agent in self.agents:
            agent = self.agents[preferred_agent]
            if agent["status"] == AgentStatus.IDLE:
                if len(agent["current_tasks"]) < self.max_concurrent_tasks_per_agent:
                    return preferred_agent
        
        # Buscar agente disponible con el rol adecuado
        task_rules = self.authorization_rules.get(task_type, {})
        required_roles = task_rules.get("roles", [task_type])
        
        best_agent = None
        min_tasks = float('inf')
        
        for agent_id, agent_info in self.agents.items():
            if agent_info["status"] != AgentStatus.IDLE:
                continue
            
            if len(agent_info["current_tasks"]) >= self.max_concurrent_tasks_per_agent:
                continue
            
            agent_roles = agent_info.get("roles", [])
            has_role = any(role in agent_roles for role in required_roles)
            
            if not has_role:
                continue
            
            current_load = len(agent_info["current_tasks"])
            if current_load < min_tasks:
                min_tasks = current_load
                best_agent = agent_id
        
        return best_agent
    
    async def _process_task_queue(self):
        """Procesar cola de tareas."""
        while self.status != AgentStatus.OFFLINE:
            try:
                task = await asyncio.wait_for(self.task_queue.get(), timeout=1.0)
                await self._execute_task(task)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("error_processing_task", error=str(e))
    
    async def _execute_task(self, task: Dict):
        """Ejecutar tarea asignada."""
        task_id = task["task_id"]
        assigned_agent = task["assigned_agent"]
        
        # Actualizar estado
        if assigned_agent in self.agents:
            self.agents[assigned_agent]["status"] = AgentStatus.BUSY
        
        task["status"] = "processing"
        task["started_at"] = datetime.now().isoformat()
        
        # TODO: Enviar tarea al agente via mensaje/cola
        # await self._send_to_agent(assigned_agent, task)
        
        # Por ahora simular completación
        await asyncio.sleep(1)
        
        # Marcar completada
        task["status"] = "completed"
        task["completed_at"] = datetime.now().isoformat()
        
        if assigned_agent in self.agents:
            self.agents[assigned_agent]["status"] = AgentStatus.IDLE
            if task_id in self.agents[assigned_agent]["current_tasks"]:
                self.agents[assigned_agent]["current_tasks"].remove(task_id)
            self.agents[assigned_agent]["completed_tasks"] += 1
        
        self.stats["tasks_completed"] += 1
        
        logger.info("task_completed", task_id=task_id, agent=assigned_agent)
    
    async def _monitor_agents(self):
        """Monitorear salud de agentes."""
        while self.status != AgentStatus.OFFLINE:
            await asyncio.sleep(30)
            
            now = datetime.now()
            for agent_id, agent_info in self.agents.items():
                last_hb = datetime.fromisoformat(agent_info["last_heartbeat"])
                if (now - last_hb).total_seconds() > 60:
                    if agent_info["status"] != AgentStatus.OFFLINE:
                        logger.warning("agent_offline", agent_id=agent_id)
                        agent_info["status"] = AgentStatus.OFFLINE
                        
                        # Re-encolar tareas del agente offline
                        for task_id in agent_info["current_tasks"]:
                            # TODO: Re-encolar tarea
                            pass
    
    async def _cleanup_old_tasks(self):
        """Limpiar tareas antiguas."""
        while self.status != AgentStatus.OFFLINE:
            await asyncio.sleep(3600)  # Cada hora
            # TODO: Limpiar tareas completadas antiguas
    
    def _log_decision(self, decision: Dict):
        """Registrar decisión en log de auditoría."""
        self.decision_log.append(decision)
        # Mantener solo últimas 10000 decisiones
        if len(self.decision_log) > 10000:
            self.decision_log = self.decision_log[-10000:]
    
    def get_status(self) -> Dict:
        """Obtener estado del supervisor."""
        return {
            "agent_id": self.agent_id,
            "status": self.status,
            "registered_agents": len(self.agents),
            "agents": {k: {**v, "current_tasks": len(v["current_tasks"])} 
                      for k, v in self.agents.items()},
            "queue_size": self.task_queue.qsize(),
            "stats": self.stats,
            "uptime": "TODO",
        }
    
    def get_agent_status(self, agent_id: str) -> Optional[Dict]:
        """Obtener estado de un agente específico."""
        return self.agents.get(agent_id)
    
    def get_daily_summary(self) -> Dict:
        """Generar resumen diario."""
        return {
            "date": datetime.now().date().isoformat(),
            "stats": self.stats,
            "agents": {k: {"completed": v["completed_tasks"], "failed": v["failed_tasks"]} 
                      for k, v in self.agents.items()},
            "decisions_today": len([d for d in self.decision_log 
                                   if d["timestamp"].startswith(datetime.now().date().isoformat())]),
            "conflicts_today": self.stats["conflicts_detected"],
        }


# Instancia global para uso en workers
_supervisor_instance: Optional[SupervisorAgent] = None


def get_supervisor(config: Optional[Dict] = None) -> SupervisorAgent:
    """Obtener instancia singleton del supervisor."""
    global _supervisor_instance
    if _supervisor_instance is None:
        _supervisor_instance = SupervisorAgent(config or {})
    return _supervisor_instance


async def start_supervisor(config: Optional[Dict] = None):
    """Iniciar supervisor."""
    supervisor = get_supervisor(config)
    await supervisor.start()
    return supervisor


async def stop_supervisor():
    """Detener supervisor."""
    global _supervisor_instance
    if _supervisor_instance:
        await _supervisor_instance.stop()
        _supervisor_instance = None