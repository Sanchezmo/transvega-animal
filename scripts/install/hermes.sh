#!/usr/bin/env bash
# scripts/install/hermes.sh
# Prepara Hermes (API + Worker + Approvals) para ejecución nativa (idempotente)
# Uso: ./scripts/install/hermes.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

# Cargar .env
if [[ -f "${PROJECT_ROOT}/.env" ]]; then
    set -a
    source "${PROJECT_ROOT}/.env"
    set +a
fi

# Configuración
VENV_DIR="${PROJECT_ROOT}/.venv"

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }
log_step()  { echo -e "${BLUE}[STEP]${NC} $*"; }

verify_venv() {
    log_step "Verificando virtualenv..."

    if [[ ! -f "${VENV_DIR}/bin/python" ]]; then
        log_error "Virtualenv no encontrado en ${VENV_DIR}"
        log_info "Ejecutar primero: ./scripts/install/python.sh"
        exit 1
    fi

    log_info "Virtualenv OK: ${VENV_DIR}"
}

verify_project_structure() {
    log_step "Verificando estructura del proyecto..."

    local required_paths=(
        "${PROJECT_ROOT}/services/integration-api/app/main.py"
        "${PROJECT_ROOT}/services/integration-api/app/core/config.py"
        "${PROJECT_ROOT}/services/task-queue/app/celery_app.py"
        "${PROJECT_ROOT}/services/approval-service/app.py"
        "${PROJECT_ROOT}/adapters/dolibarr/client.py"
        "${PROJECT_ROOT}/agents"
    )

    local missing=0
    for path in "${required_paths[@]}"; do
        if [[ -e "$path" ]]; then
            log_info "  ✓ ${path#${PROJECT_ROOT}/}"
        else
            log_error "  ✗ ${path#${PROJECT_ROOT}/} (NO ENCONTRADO)"
            missing=1
        fi
    done

    if [[ $missing -eq 1 ]]; then
        log_error "Faltan archivos críticos del proyecto"
        exit 1
    fi
}

create_data_dirs() {
    log_step "Creando directorios de datos..."

    local dirs=(
        "${PROJECT_ROOT}/hermes_data"
        "${PROJECT_ROOT}/hermes_logs"
        "${PROJECT_ROOT}/invoice_worker_logs"
        "${PROJECT_ROOT}/data/invoices"
        "${PROJECT_ROOT}/data/dogs"
    )

    for dir in "${dirs[@]}"; do
        mkdir -p "$dir"
    done

    # Permisos para usuario actual (no root)
    chown -R "$(id -u):$(id -g)" "${PROJECT_ROOT}/hermes_data" "${PROJECT_ROOT}/hermes_logs" "${PROJECT_ROOT}/invoice_worker_logs" 2>/dev/null || true

    log_info "Directorios de datos creados"
}

verify_config_loading() {
    log_step "Verificando carga de configuración..."

    # Test que Settings carga correctamente desde .env
    local test_script="
import os
os.environ['ENV_FILE'] = '${PROJECT_ROOT}/.env'
import sys
sys.path.insert(0, '${PROJECT_ROOT}')
sys.path.insert(0, '${PROJECT_ROOT}/services/integration-api')
sys.path.insert(0, '${PROJECT_ROOT}/services/task-queue')
sys.path.insert(0, '${PROJECT_ROOT}/adapters')
sys.path.insert(0, '${PROJECT_ROOT}/agents')

from app.core.config import get_settings
settings = get_settings()

# Verificar variables críticas
checks = [
    ('AUDIT_DB_HOST', settings.AUDIT_DB_HOST),
    ('AUDIT_DB_PASSWORD', bool(settings.AUDIT_DB_PASSWORD)),
    ('REDIS_HOST', settings.REDIS_HOST),
    ('REDIS_PASSWORD', bool(settings.REDIS_PASSWORD)),
    ('DOLIBARR_API_URL', settings.DOLIBARR_API_URL),
    ('DOLIBARR_API_KEY', bool(settings.DOLIBARR_API_KEY)),
    ('JWT_SECRET_KEY', bool(settings.JWT_SECRET_KEY)),
    ('FERNET_KEY', bool(settings.FERNET_KEY)),
    ('OLLAMA_ENDPOINT', settings.OLLAMA_ENDPOINT),
    ('OLLAMA_MODEL', settings.OLLAMA_MODEL),
]

all_ok = True
for name, value in checks:
    if value:
        print(f'  ✓ {name}')
    else:
        print(f'  ✗ {name} (VACÍO/INVÁLIDO)')
        all_ok = False

if not all_ok:
    sys.exit(1)
print('✓ Configuración válida')
"

    if "${VENV_DIR}/bin/python" -c "$test_script"; then
        log_info "Configuración carga correctamente"
    else
        log_error "Error cargando configuración - verifica .env"
        return 1
    fi
}

verify_database_connections() {
    log_step "Verificando conexiones a bases de datos..."

    # PostgreSQL (audit)
    if "${VENV_DIR}/bin/python" -c "
import asyncio
import sys
sys.path.insert(0, '${PROJECT_ROOT}')
sys.path.insert(0, '${PROJECT_ROOT}/services/integration-api')
from app.core.config import get_settings
from sqlalchemy.ext.asyncio import create_async_engine
settings = get_settings()
url = f'postgresql+asyncpg://{settings.AUDIT_DB_USER}:{settings.AUDIT_DB_PASSWORD}@{settings.AUDIT_DB_HOST}:{settings.AUDIT_DB_PORT}/{settings.AUDIT_DB_NAME}'
engine = create_async_engine(url)
async def test():
    async with engine.connect() as conn:
        await conn.execute(text('SELECT 1'))
    await engine.dispose()
import sqlalchemy
from sqlalchemy import text
asyncio.run(test())
print('✓ PostgreSQL audit OK')
" 2>/dev/null; then
        log_info "PostgreSQL (audit): Conexión OK"
    else
        log_warn "PostgreSQL (audit): No accesible (ejecutar ./scripts/install/postgresql.sh primero)"
    fi

    # Redis
    if "${VENV_DIR}/bin/python" -c "
import sys
sys.path.insert(0, '${PROJECT_ROOT}')
sys.path.insert(0, '${PROJECT_ROOT}/services/integration-api')
from app.core.config import get_settings
import redis
settings = get_settings()
r = redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, password=settings.REDIS_PASSWORD or None, decode_responses=True)
r.ping()
print('✓ Redis OK')
" 2>/dev/null; then
        log_info "Redis: Conexión OK"
    else
        log_warn "Redis: No accesible (ejecutar ./scripts/install/redis.sh primero)"
    fi

    # MariaDB (Dolibarr) - test con mysql client
    if mysql -h"${DOLIBARR_DB_HOST:-127.0.0.1}" -P"${DOLIBARR_DB_PORT:-3306}" -u"${DOLIBARR_DB_USER:-dolibarr}" -p"${DOLIBARR_DB_PASSWORD}" -e "SELECT 1" >/dev/null 2>&1; then
        log_info "MariaDB (Dolibarr): Conexión OK"
    else
        log_warn "MariaDB (Dolibarr): No accesible (ejecutar ./scripts/install/mariadb.sh primero)"
    fi
}

verify_ollama() {
    log_step "Verificando Ollama..."

    if curl -sf "${OLLAMA_ENDPOINT:-http://127.0.0.1:11434}/api/tags" >/dev/null 2>&1; then
        local model
        model=$(curl -sf "${OLLAMA_ENDPOINT:-http://127.0.0.1:11434}/api/tags" | jq -r '.models[].name' | grep "^${OLLAMA_MODEL:-transvega-local}$" || echo "")
        if [[ -n "$model" ]]; then
            log_info "Ollama: Modelo ${OLLAMA_MODEL:-transvega-local} disponible"
        else
            log_warn "Ollama: Modelo ${OLLAMA_MODEL:-transvega-local} no encontrado"
        fi
    else
        log_warn "Ollama: No accesible en ${OLLAMA_ENDPOINT:-http://127.0.0.1:11434} (ejecutar ./scripts/install/ollama.sh primero)"
    fi
}

create_log_dirs() {
    log_step "Creando directorios de logs para systemd..."

    mkdir -p /var/log/transvega
    chown "$(id -u):$(id -g)" /var/log/transvega 2>/dev/null || true

    log_info "Directorio logs: /var/log/transvega"
}

main() {
    log_info "=== Preparador Hermes Nativo ==="
    log_info "Proyecto: ${PROJECT_ROOT}"
    log_info "Virtualenv: ${VENV_DIR}"
    echo ""

    verify_venv
    verify_project_structure
    create_data_dirs
    create_log_dirs

    if verify_config_loading; then
        verify_database_connections
        verify_ollama
        log_info "✅ Hermes preparado para ejecución nativa"
        echo ""
        echo "Próximos pasos:"
        echo "  1. ./scripts/configure/services.sh  # Instalar systemd services"
        echo "  2. systemctl start hermes hermes-worker approvals"
        echo "  3. make status  # Verificar health checks"
    else
        log_error "❌ Error en verificación de configuración"
        exit 1
    fi
}

main "$@"