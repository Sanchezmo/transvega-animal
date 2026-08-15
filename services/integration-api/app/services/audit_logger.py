"""
Servicio de logging de auditoría inmutable.
"""

import hashlib
import json
from datetime import datetime
from typing import Any
from uuid import UUID

import structlog

logger = structlog.get_logger()


class AuditLogger:
    """Registra eventos de auditoría de forma inmutable."""

    def __init__(self, db_pool: Any) -> None:
        self.db_pool = db_pool

    async def log(
        self,
        *,
        request_id: UUID,
        agent_id: str,
        agent_name: str,
        agent_roles: list[str],
        method: str,
        path: str,
        query_params: dict[str, Any],
        request_body: dict[str, Any] | None,
        resource_type: str | None,
        resource_id: str | None,
        action: str,
        previous_state: dict[str, Any] | None,
        new_state: dict[str, Any] | None,
        status_code: int,
        success: bool,
        error_code: str | None = None,
        error_message: str | None = None,
        error_details: dict[str, Any] | None = None,
        duration_ms: float,
        idempotency_key: str | None = None,
        idempotent: bool = False,
        correlation_id: UUID | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        api_key_hash: str | None = None,
    ) -> None:
        """
        Registra un evento de auditoría de forma asíncrona y no bloqueante.
        """
        try:
            # Calcular hashes para integridad
            request_body_hash = None
            if request_body:
                request_body_hash = hashlib.sha256(json.dumps(request_body, sort_keys=True).encode()).hexdigest()

            # Calcular diff si ambos estados existen
            diff = None
            if previous_state and new_state:
                diff = self._calculate_diff(previous_state, new_state)

            query = """
                INSERT INTO audit_log (
                    request_id, correlation_id,
                    agent_id, agent_name, agent_roles, api_key_hash,
                    method, path, query_params, request_body_hash,
                    resource_type, resource_id, action,
                    previous_state, new_state, diff,
                    status_code, success,
                    error_code, error_message, error_details,
                    duration_ms, idempotency_key, idempotent,
                    ip_address, user_agent,
                    created_at
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                    $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22,
                    $23, $24, $25, $26, $26, NOW()
                )
            """

            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    query,
                    str(request_id),
                    str(correlation_id) if correlation_id else None,
                    agent_id,
                    agent_name,
                    json.dumps(agent_roles),
                    api_key_hash,
                    method,
                    path,
                    json.dumps(query_params),
                    request_body_hash,
                    resource_type,
                    resource_id,
                    action,
                    json.dumps(previous_state) if previous_state else None,
                    json.dumps(new_state) if new_state else None,
                    json.dumps(diff) if diff else None,
                    status_code,
                    success,
                    error_code,
                    error_message,
                    json.dumps(error_details) if error_details else None,
                    duration_ms,
                    idempotency_key,
                    idempotent,
                    ip_address,
                    user_agent,
                )

        except Exception as e:
            # No fallar la request principal por error de auditoría
            logger.error(
                "audit_log_failed",
                error=str(e),
                request_id=str(request_id),
                path=path,
            )

    def _calculate_diff(self, old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
        """Calcular diferencia entre dos estados."""
        diff: dict[str, Any] = {
            "added": {},
            "removed": {},
            "changed": {},
        }

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

    async def query_logs(
        self,
        *,
        agent_id: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        action: str | None = None,
        success: bool | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Consultar logs de auditoría con filtros."""
        conditions: list[str] = ["1=1"]
        params: list[Any] = []
        param_num = 1

        if agent_id:
            conditions.append(f"agent_id = ${param_num}")
            params.append(agent_id)
            param_num += 1

        if resource_type:
            conditions.append(f"resource_type = ${param_num}")
            params.append(resource_type)
            param_num += 1

        if resource_id:
            conditions.append(f"resource_id = ${param_num}")
            params.append(resource_id)
            param_num += 1

        if action:
            conditions.append(f"action = ${param_num}")
            params.append(action)
            param_num += 1

        if success is not None:
            conditions.append(f"success = ${param_num}")
            params.append(success)
            param_num += 1

        if start_date:
            conditions.append(f"created_at >= ${param_num}")
            params.append(start_date)
            param_num += 1

        if end_date:
            conditions.append(f"created_at <= ${param_num}")
            params.append(end_date)
            param_num += 1

        where_clause = " AND ".join(conditions)

        query = (
            f"SELECT * FROM audit_log WHERE {where_clause} "
            f"ORDER BY created_at DESC LIMIT ${param_num} OFFSET ${param_num + 1}"
        )  # nosec B608 - Uses parameterized placeholders with asyncpg
        params.extend([limit, offset])

        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [dict(row) for row in rows]

    async def get_summary(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> list[dict[str, Any]]:
        """Obtener resumen de actividad."""
        query = """
            SELECT
                DATE_TRUNC('day', created_at) as day,
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE success) as successful,
                COUNT(*) FILTER (WHERE NOT success) as failed,
                AVG(duration_ms) as avg_duration_ms,
                COUNT(DISTINCT agent_id) as unique_agents,
                COUNT(DISTINCT resource_type) as resource_types
            FROM audit_log
            WHERE created_at >= $1 AND created_at <= $2
            GROUP BY DATE_TRUNC('day', created_at)
            ORDER BY day DESC
        """

        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query, start_date, end_date)
            return [dict(row) for row in rows]

    async def cleanup_old_logs(self, retention_days: int = 90) -> int:
        """Limpiar logs antiguos (solo exitosos, no acciones críticas)."""
        query = """
            DELETE FROM audit_log
            WHERE created_at < NOW() - INTERVAL '1 day' * $1
            AND success = TRUE
            AND action NOT IN ('login', 'logout', 'permission_change', 'approval_decision')
        """

        async with self.db_pool.acquire() as conn:
            result = await conn.execute(query, retention_days)
            # Extraer número de filas afectadas
            return int(result.split()[-1]) if result else 0
