"""
Telegram Conversation Manager - Gestión centralizada de sesiones y workflows.
Persistencia en Redis para supervivencia a reinicios.
"""

import json
import uuid
from datetime import datetime, timedelta
from typing import Any

import structlog
from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.database import get_redis_client

logger = structlog.get_logger()

settings = get_settings()

# TTL por defecto para sesiones (24 horas)
DEFAULT_SESSION_TTL_HOURS = 24
DEFAULT_SESSION_TTL_SECONDS = DEFAULT_SESSION_TTL_HOURS * 3600

# Prefijos de claves Redis
SESSION_KEY_PREFIX = "telegram:session:"
WORKFLOW_KEY_PREFIX = "telegram:workflow:"
PENDING_MEDIA_KEY_PREFIX = "telegram:pending_media:"


class TelegramConversationManager:
    """
    Gestor centralizado de conversaciones de Telegram.

    Responsabilidades:
    - Crear, obtener, actualizar, eliminar sesiones
    - Persistencia en Redis con TTL
    - Gestión de workflow activo y step
    - Contexto persistente por sesión
    - Gestión de pending_media para recuperación en 2 turnos
    - Expiración automática y limpieza
    """

    def __init__(self, redis: Redis | None = None):
        self._redis = redis
        self._own_redis = redis is None

    async def _get_redis(self) -> Redis:
        """Obtener cliente Redis."""
        if self._redis is None:
            self._redis = await get_redis_client()
        return self._redis

    async def close(self):
        """Cerrar conexión Redis si la creamos nosotros."""
        if self._own_redis and self._redis:
            await self._redis.close()
            self._redis = None

    # =========================================================================
    # Claves Redis
    # =========================================================================

    def _session_key(self, user_id: int, chat_id: int) -> str:
        """Clave Redis para sesión: telegram:session:{user_id}:{chat_id}"""
        return f"{SESSION_KEY_PREFIX}{user_id}:{chat_id}"

    def _workflow_key(self, user_id: int, chat_id: int) -> str:
        """Clave Redis para workflow: telegram:workflow:{user_id}:{chat_id}"""
        return f"{WORKFLOW_KEY_PREFIX}{user_id}:{chat_id}"

    def _pending_media_key(self, user_id: int, chat_id: int) -> str:
        """Clave Redis para pending_media: telegram:pending_media:{user_id}:{chat_id}"""
        return f"{PENDING_MEDIA_KEY_PREFIX}{user_id}:{chat_id}"

    # =========================================================================
    # Sesiones
    # =========================================================================

    async def get_session(self, user_id: int, chat_id: int) -> dict[str, Any] | None:
        """Obtener sesión existente."""
        redis = await self._get_redis()
        key = self._session_key(user_id, chat_id)
        data = await redis.get(key)
        if data:
            session = json.loads(data)
            # Verificar expiración
            if session.get("expires_at"):
                expires_at = datetime.fromisoformat(session["expires_at"])
                if datetime.utcnow() > expires_at:
                    await self.delete_session(session["telegram_user_id"], session["telegram_chat_id"])
                    return None
            return session
        return None

    async def create_session(
        self,
        user_id: int,
        chat_id: int,
        workflow_type: str = "none",
        workflow_step: str = "awaiting_workflow_selection",
        context: dict | None = None,
        ttl_hours: int | None = None,
    ) -> dict[str, Any]:
        """Crear nueva sesión."""
        redis = await self._get_redis()

        now = datetime.utcnow()
        ttl_h = ttl_hours or DEFAULT_SESSION_TTL_HOURS
        expires_at = now + timedelta(hours=ttl_h)

        session = {
            "session_id": str(uuid.uuid4()),
            "telegram_user_id": user_id,
            "telegram_chat_id": chat_id,
            "workflow_type": workflow_type,
            "workflow_step": workflow_step,
            "context": context or {},
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "last_update_id": None,
            "last_message_id": None,
        }

        key = self._session_key(user_id, chat_id)
        ttl_seconds = ttl_h * 3600
        await redis.setex(key, ttl_seconds, json.dumps(session))

        logger.info(
            "session_created",
            user_id=user_id,
            chat_id=chat_id,
            workflow_type=workflow_type,
            session_id=session["session_id"],
        )

        return session

    async def update_session(
        self,
        user_id: int,
        chat_id: int,
        workflow_type: str | None = None,
        workflow_step: str | None = None,
        context: dict | None = None,
        expires_at: datetime | None = None,
        last_update_id: int | None = None,
        last_message_id: int | None = None,
    ) -> dict[str, Any] | None:
        """Actualizar sesión existente."""
        redis = await self._get_redis()
        key = self._session_key(user_id, chat_id)

        existing = await redis.get(key)
        if not existing:
            return None

        session = json.loads(existing)

        # Actualizar campos
        if workflow_type is not None:
            session["workflow_type"] = workflow_type
        if workflow_step is not None:
            session["workflow_step"] = workflow_step
        if context is not None:
            session["context"] = context
        if expires_at is not None:
            session["expires_at"] = expires_at.isoformat()
        if last_update_id is not None:
            session["last_update_id"] = last_update_id
        if last_message_id is not None:
            session["last_message_id"] = last_message_id

        session["updated_at"] = datetime.utcnow().isoformat()

        # Calcular TTL restante
        if session.get("expires_at"):
            expires_at_dt = datetime.fromisoformat(session["expires_at"])
            remaining = expires_at_dt - datetime.utcnow()
            if remaining.total_seconds() <= 0:
                await self.delete_session(user_id, chat_id)
                return None
            ttl_seconds = int(remaining.total_seconds())
        else:
            ttl_seconds = DEFAULT_SESSION_TTL_SECONDS

        await redis.setex(key, ttl_seconds, json.dumps(session))

        logger.debug(
            "session_updated",
            user_id=user_id,
            chat_id=chat_id,
            workflow_type=session.get("workflow_type"),
            workflow_step=session.get("workflow_step"),
        )

        return session

    async def delete_session(self, user_id: int, chat_id: int) -> bool:
        """Eliminar sesión."""
        redis = await self._get_redis()
        key = self._session_key(user_id, chat_id)
        result = await redis.delete(key)
        if result:
            logger.info("session_deleted", user_id=user_id, chat_id=chat_id)
        return bool(result)

    async def get_or_create_session(
        self,
        user_id: int,
        chat_id: int,
        default_workflow_type: str = "none",
        default_workflow_step: str = "awaiting_workflow_selection",
    ) -> dict[str, Any]:
        """Obtener sesión existente o crear nueva."""
        session = await self.get_session(user_id, chat_id)
        if session:
            # Verificar si expiró
            if session.get("expires_at"):
                expires_at = datetime.fromisoformat(session["expires_at"])
                if datetime.utcnow() > expires_at:
                    await self.delete_session(user_id, chat_id)
                else:
                    return session

        # Crear nueva
        return await self.create_session(
            user_id=user_id,
            chat_id=chat_id,
            workflow_type="none",
            workflow_step="awaiting_workflow_selection",
        )

    # =========================================================================
    # Workflow State
    # =========================================================================

    async def set_workflow(
        self,
        user_id: int,
        chat_id: int,
        workflow_type: str,
        workflow_step: str,
        context: dict | None = None,
    ) -> dict[str, Any]:
        """Establecer workflow activo."""
        return await self.update_session(
            user_id=user_id,
            chat_id=chat_id,
            workflow_type=workflow_type,
            workflow_step=workflow_step,
            context=context,
        )

    async def get_workflow(self, user_id: int, chat_id: int) -> dict | None:
        """Obtener estado actual del workflow."""
        session = await self.get_session(user_id, chat_id)
        if not session:
            return None
        return {
            "workflow_type": session.get("workflow_type"),
            "workflow_step": session.get("workflow_step"),
            "context": session.get("context", {}),
        }

    async def clear_workflow(self, user_id: int, chat_id: int) -> bool:
        """Limpiar workflow activo (volver a estado inicial)."""
        session = await self.get_session(user_id, chat_id)
        if not session:
            return False

        # Resetear a estado inicial pero mantener sesión
        return (
            await self.update_session(
                user_id=user_id,
                chat_id=chat_id,
                workflow_type="none",
                workflow_step="awaiting_workflow_selection",
                context={},
            )
            is not None
        )

    async def complete_workflow(self, user_id: int, chat_id: int) -> bool:
        """Marcar workflow como completado y limpiar estado."""
        session = await self.get_session(user_id, chat_id)
        if not session:
            return False

        return (
            await self.update_session(
                user_id=user_id,
                chat_id=chat_id,
                workflow_type="none",
                workflow_step="awaiting_workflow_selection",
                context={},
            )
            is not None
        )

    async def cancel_workflow(self, user_id: int, chat_id: int) -> bool:
        """Cancelar workflow activo y limpiar contexto."""
        return await self.clear_workflow(user_id, chat_id)

    # =========================================================================
    # Contexto
    # =========================================================================

    async def update_context(self, user_id: int, chat_id: int, context_updates: dict) -> dict | None:
        """Actualizar contexto del workflow (merge)."""
        session = await self.get_session(user_id, chat_id)
        if not session:
            return None

        current_context = session.get("context", {})
        current_context.update(context_updates)

        return await self.update_session(user_id=user_id, chat_id=chat_id, context=current_context)

    async def get_context(self, user_id: int, chat_id: int) -> dict:
        """Obtener contexto actual."""
        session = await self.get_session(user_id, chat_id)
        if not session:
            return {}
        return session.get("context", {})

    async def clear_context(self, user_id: int, chat_id: int) -> bool:
        """Limpiar contexto del workflow."""
        return await self.update_session(user_id=user_id, chat_id=chat_id, context={}) is not None

    # =========================================================================
    # Pending Media (para recuperación en 2 turnos)
    # =========================================================================

    async def set_pending_media(self, user_id: int, chat_id: int, pending_media: dict) -> bool:
        """Guardar pending_media con TTL independiente."""
        redis = await self._get_redis()
        key = self._pending_media_key(user_id, chat_id)
        ttl_seconds = 3600  # 1 hora para pending media
        await redis.setex(key, ttl_seconds, json.dumps(pending_media))
        return True

    async def get_pending_media(self, user_id: int, chat_id: int) -> dict | None:
        """Obtener pending_media si existe."""
        redis = await self._get_redis()
        key = self._pending_media_key(user_id, chat_id)
        data = await redis.get(key)
        if data:
            return json.loads(data)
        return None

    async def clear_pending_media(self, user_id: int, chat_id: int) -> bool:
        """Limpiar pending_media."""
        redis = await self._get_redis()
        key = self._pending_media_key(user_id, chat_id)
        result = await redis.delete(key)
        return bool(result)

    # =========================================================================
    # Utilidades
    # =========================================================================

    async def touch_session(self, user_id: int, chat_id: int) -> bool:
        """Actualizar timestamp de última actividad."""
        session = await self.get_session(user_id, chat_id)
        if not session:
            return False

        session["updated_at"] = datetime.utcnow().isoformat()
        key = self._session_key(user_id, chat_id)
        redis = await self._get_redis()

        if session.get("expires_at"):
            expires_at_dt = datetime.fromisoformat(session["expires_at"])
            remaining = expires_at_dt - datetime.utcnow()
            if remaining.total_seconds() <= 0:
                await self.delete_session(session["telegram_user_id"], session["telegram_chat_id"])
                return False
            ttl_seconds = int(remaining.total_seconds())
        else:
            ttl_seconds = DEFAULT_SESSION_TTL_SECONDS

        await redis.setex(key, ttl_seconds, json.dumps(session))
        return True

    async def is_session_active(self, user_id: int, chat_id: int) -> bool:
        """Verificar si hay una sesión activa (no expirada)."""
        session = await self.get_session(user_id, chat_id)
        return session is not None

    async def get_active_workflow_type(self, user_id: int, chat_id: int) -> str | None:
        """Obtener tipo de workflow activo."""
        session = await self.get_session(user_id, chat_id)
        if not session:
            return None
        return session.get("workflow_type")

    async def get_active_workflow_step(self, user_id: int, chat_id: int) -> str | None:
        """Obtener step actual del workflow."""
        session = await self.get_session(user_id, chat_id)
        if not session:
            return None
        return session.get("workflow_step")

    # =========================================================================
    # Limpieza
    # =========================================================================

    async def cleanup_expired_sessions(self) -> int:
        """Limpiar sesiones expiradas (scan + delete)."""
        redis = await self._get_redis()
        deleted = 0
        pattern = f"{SESSION_KEY_PREFIX}*"
        async for key in redis.scan_iter(match=pattern):
            data = await redis.get(key)
            if data:
                session = json.loads(data)
                if session.get("expires_at"):
                    expires_at = datetime.fromisoformat(session["expires_at"])
                    if datetime.utcnow() > expires_at:
                        await redis.delete(key)
                        deleted += 1
        if deleted:
            logger.info("expired_sessions_cleaned", count=deleted)
        return deleted


# Instancia global
conversation_manager: TelegramConversationManager | None = None


async def get_conversation_manager() -> TelegramConversationManager:
    """Dependency injection para ConversationManager."""
    global conversation_manager
    if conversation_manager is None:
        conversation_manager = TelegramConversationManager()
    return conversation_manager


async def close_conversation_manager():
    """Cerrar el manager global."""
    global conversation_manager
    if conversation_manager:
        await conversation_manager.close()
        conversation_manager = None
