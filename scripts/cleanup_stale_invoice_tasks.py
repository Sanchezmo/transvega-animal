#!/usr/bin/env python3
"""
Limpieza quirúrgica de tareas de facturas antiguas en Redis.

NO usa FLUSHALL. Solo elimina claves específicas relacionadas con facturas
que puedan causar reprocesamiento tras reinicio.

Uso:
    python scripts/cleanup_stale_invoice_tasks.py --dry-run   # Ver qué se borraría
    python scripts/cleanup_stale_invoice_tasks.py             # Ejecutar limpieza
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Añadir path del proyecto
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.integration-api.app.core.config import get_settings
from services.integration-api.app.core.database import get_redis_client


# Patrones de claves a limpiar (solo facturas)
INVOICE_KEY_PATTERNS = [
    "invoice_result:*",           # Resultados cacheados de procesamiento
    "invoice_processing:*",       # Tracking de procesamiento en curso
    "invoice:file:*",             # Idempotencia por file_hash/file_unique_id
    "celery-task-meta-*",         # Resultados de tareas Celery (solo si son de facturación)
]

# Patrones de colas Celery a inspeccionar/limpiar
CELERY_QUEUES = [
    "high",
    "default", 
    "low",
    "approvals",
    "notifications",
]


async def scan_redis_keys(redis, patterns: list[str]) -> dict[str, list[str]]:
    """Escanea Redis y devuelve claves encontradas por patrón."""
    found = {}
    for pattern in patterns:
        keys = []
        async for key in redis.scan_iter(match=pattern):
            keys.append(key.decode() if isinstance(key, bytes) else key)
        if keys:
            found[pattern] = keys
    return found


async def inspect_celery_queues(redis) -> dict[str, list[dict]]:
    """Inspecciona colas Celery buscando tareas de facturación."""
    queue_tasks = {}
    for queue in CELERY_QUEUES:
        # Celery usa listas Redis para colas: "celery", "high", etc.
        # Las tareas están serializadas como JSON en la lista
        length = await redis.llen(queue)
        if length > 0:
            tasks = []
            # Leer primeros 100 elementos para inspección
            for i in range(min(length, 100)):
                task_data = await redis.lindex(queue, i)
                if task_data:
                    try:
                        import json
                        task = json.loads(task_data)
                        # Filtrar solo tareas de facturación
                        if "facturacion" in task.get("headers", {}).get("task", "") or \
                           "procesar_factura" in task.get("headers", {}).get("task", ""):
                            tasks.append({
                                "index": i,
                                "task": task.get("headers", {}).get("task"),
                                "id": task.get("headers", {}).get("id"),
                                "correlation_id": task.get("headers", {}).get("args", [{}])[0].get("correlation_id") if task.get("headers", {}).get("args") else None,
                            })
                    except Exception:
                        pass
            if tasks:
                queue_tasks[queue] = tasks
    return queue_tasks


async def clean_redis_keys(redis, patterns: list[str], dry_run: bool = True) -> dict[str, int]:
    """Elimina claves Redis coincidentes con patrones."""
    deleted = {}
    for pattern in patterns:
        count = 0
        async for key in redis.scan_iter(match=pattern):
            key_str = key.decode() if isinstance(key, bytes) else key
            if not dry_run:
                await redis.delete(key)
            count += 1
            print(f"  {'[DRY-RUN] Would delete' if dry_run else 'Deleted'}: {key_str}")
        if count > 0:
            deleted[pattern] = count
    return deleted


async def clean_celery_invoice_tasks(redis, dry_run: bool = True) -> dict[str, int]:
    """Elimina tareas de facturación de las colas Celery."""
    deleted = {}
    for queue in CELERY_QUEUES:
        length = await redis.llen(queue)
        if length == 0:
            continue
        
        # Reconstruir cola filtrando tareas de facturación
        remaining = []
        removed = 0
        
        for i in range(length):
            task_data = await redis.lindex(queue, i)
            if task_data:
                try:
                    import json
                    task = json.loads(task_data)
                    task_name = task.get("headers", {}).get("task", "")
                    is_invoice_task = "facturacion" in task_name or "procesar_factura" in task_name
                    
                    if is_invoice_task:
                        correlation_id = task.get("headers", {}).get("args", [{}])[0].get("correlation_id") if task.get("headers", {}).get("args") else "unknown"
                        print(f"  {'[DRY-RUN] Would remove' if dry_run else 'Removed'} from {queue}: {task_name} (correlation_id={correlation_id})")
                        removed += 1
                    else:
                        remaining.append(task_data)
                except Exception:
                    # Si no se puede parsear, mantener
                    remaining.append(task_data)
        
        if removed > 0 and not dry_run:
            # Reconstruir cola sin las tareas eliminadas
            await redis.delete(queue)
            if remaining:
                await redis.rpush(queue, *remaining)
            deleted[queue] = removed
        elif removed > 0:
            deleted[queue] = removed
    
    return deleted


async def main():
    parser = argparse.ArgumentParser(description="Limpieza quirúrgica de tareas de facturas en Redis")
    parser.add_argument("--dry-run", action="store_true", help="Solo mostrar qué se borraría, sin ejecutar")
    parser.add_argument("--include-celery", action="store_true", help="Incluir limpieza de colas Celery")
    args = parser.parse_args()

    settings = get_settings()
    
    # Construir URL Redis
    redis_url = f"redis://:{settings.REDIS_PASSWORD}@{settings.REDIS_HOST}:{settings.REDIS_PORT}/0"
    
    print(f"Conectando a Redis: {settings.REDIS_HOST}:{settings.REDIS_PORT}/0")
    print(f"Modo: {'DRY-RUN (solo inspección)' if args.dry_run else 'EJECUCIÓN REAL'}")
    print("=" * 60)

    redis = await get_redis_client()
    
    try:
        # 1. Escanear claves de facturas
        print("\n📋 ESCANEANDO CLAVES DE FACTURAS EN REDIS...")
        found = await scan_redis_keys(redis, INVOICE_KEY_PATTERNS)
        
        total_keys = sum(len(v) for v in found.values())
        if total_keys == 0:
            print("  No se encontraron claves de facturas.")
        else:
            for pattern, keys in found.items():
                print(f"  {pattern}: {len(keys)} claves")
                for key in keys[:10]:  # Mostrar primeras 10
                    print(f"    - {key}")
                if len(keys) > 10:
                    print(f"    ... y {len(keys) - 10} más")
        
        # 2. Inspeccionar colas Celery
        if args.include_celery:
            print("\n📋 INSPECCIONANDO COLAS CELERY...")
            queue_tasks = await inspect_celery_queues(redis)
            
            total_tasks = sum(len(v) for v in queue_tasks.values())
            if total_tasks == 0:
                print("  No se encontraron tareas de facturación en colas.")
            else:
                for queue, tasks in queue_tasks.items():
                    print(f"  Cola '{queue}': {len(tasks)} tareas de facturación")
                    for task in tasks[:5]:
                        print(f"    - {task['task']} (id={task['id']}, correlation_id={task['correlation_id']})")
        
        # 3. Ejecutar limpieza si no es dry-run
        if not args.dry_run:
            print("\n🧹 EJECUTANDO LIMPIEZA...")
            
            # Limpiar claves de facturas
            deleted_keys = await clean_redis_keys(redis, INVOICE_KEY_PATTERNS, dry_run=False)
            total_deleted_keys = sum(deleted_keys.values())
            print(f"  Claves eliminadas: {total_deleted_keys}")
            
            # Limpiar colas Celery si se pidió
            if args.include_celery:
                deleted_queues = await clean_celery_invoice_tasks(redis, dry_run=False)
                total_deleted_tasks = sum(deleted_queues.values())
                print(f"  Tareas de colas eliminadas: {total_deleted_tasks}")
            
            print("\n✅ Limpieza completada")
        else:
            print("\n🔍 DRY-RUN completado. Ejecuta sin --dry-run para limpiar.")
            if args.include_celery:
                print("   Usa --include-celery para incluir colas Celery.")
    
    finally:
        await redis.close()


if __name__ == "__main__":
    asyncio.run(main())