#!/usr/bin/env bash
# scripts/configure/hermes.sh
# Configura variables de entorno para Hermes systemd services
# Uso: ./scripts/configure/hermes.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

if [[ -f "${PROJECT_ROOT}/.env" ]]; then
    set -a
    source "${PROJECT_ROOT}/.env"
    set +a
fi

VENV_DIR="${PROJECT_ROOT}/.venv"

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
        log_error "Virtualenv no encontrado: ${VENV_DIR}"
        log_info "Ejecutar: ./scripts/install/python.sh"
        return 1
    fi

    log_info "Virtualenv OK: ${VENV_DIR}"
}

verify_imports() {
    log_step "Verificando imports en virtualenv..."

    local test_script="
import sys
sys.path.insert(0, '${PROJECT_ROOT}')
sys.path.insert(0, '${PROJECT_ROOT}/services/integration-api')
sys.path.insert(0, '${PROJECT_ROOT}/services/task-queue')
sys.path.insert(0, '${PROJECT_ROOT}/adapters')
sys.path.insert(0, '${PROJECT_ROOT}/agents')

try:
    from app.main import app
    print('✓ FastAPI app import OK')
except Exception as e:
    print(f'✗ FastAPI app import FAIL: {e}')
    sys.exit(1)

try:
    from tasks.celery_app import celery_app
    print('✓ Celery app import OK')
except Exception as e:
    print(f'✗ Celery app import FAIL: {e}')
    sys.exit(1)

try:
    from app.core.config import get_settings
    settings = get_settings()
    print(f'✓ Settings OK: {settings.APP_NAME} v{settings.APP_VERSION}')
except Exception as e:
    print(f'✗ Settings FAIL: {e}')
    sys.exit(1)
"

    if "${VENV_DIR}/bin/python" -c "$test_script"; then
        log_info "Todos los imports verificados"
    else
        log_error "Falló verificación de imports"
        return 1
    fi
}

verify_env_vars() {
    log_step "Verificando variables de entorno críticas..."

    local required=(
        "AUDIT_DB_PASSWORD"
        "REDIS_PASSWORD"
        "JWT_SECRET_KEY"
        "FERNET_KEY"
        "DOLIBARR_API_KEY"
        "OLLAMA_ENDPOINT"
    )

    local missing=()
    for var in "${required[@]}"; do
        if [[ -z "${!var:-}" ]]; then
            missing+=("$var")
        fi
    done

    if [[ ${#missing[@]} -gt 0 ]]; then
        log_warn "Variables vacías en .env:"
        for var in "${missing[@]}"; do
            log_warn "  - $var"
        done
        return 1
    fi

    log_info "Variables críticas presentes"
}

create_systemd_env() {
    log_step "Creando archivo de entorno para systemd..."

    local env_file="/etc/transvega/hermes.env"
    mkdir -p "$(dirname "$env_file")"

    cat > "$env_file" <<EOF
# Entorno para servicios Hermes systemd
# Generado por scripts/configure/hermes.sh

PROJECT_ROOT=${PROJECT_ROOT}
VENV_DIR=${VENV_DIR}
PYTHONPATH=${PROJECT_ROOT}:${PROJECT_ROOT}/services/integration-api:${PROJECT_ROOT}/services/task-queue:${PROJECT_ROOT}/adapters:${PROJECT_ROOT}/agents

# Base de datos
AUDIT_DB_HOST=${AUDIT_DB_HOST:-127.0.0.1}
AUDIT_DB_PORT=${AUDIT_DB_PORT:-5432}
AUDIT_DB_NAME=${AUDIT_DB_NAME:-audit}
AUDIT_DB_USER=${AUDIT_DB_USER:-audit}
AUDIT_DB_PASSWORD=${AUDIT_DB_PASSWORD}

# Redis
REDIS_HOST=${REDIS_HOST:-127.0.0.1}
REDIS_PORT=${REDIS_PORT:-6379}
REDIS_PASSWORD=${REDIS_PASSWORD}

# Dolibarr
DOLIBARR_API_URL=${DOLIBARR_API_URL:-http://127.0.0.1:8080/api/index.php}
DOLIBARR_API_KEY=${DOLIBARR_API_KEY}

# Seguridad
JWT_SECRET_KEY=${JWT_SECRET_KEY}
FERNET_KEY=${FERNET_KEY}

# Ollama
OLLAMA_ENDPOINT=${OLLAMA_ENDPOINT:-http://127.0.0.1:11434}
OLLAMA_MODEL=${OLLAMA_MODEL:-transvega-local}

# API
API_HOST=0.0.0.0
API_PORT=${API_PORT:-8000}
API_WORKERS=1

# Approvals
APPROVALS_HOST=127.0.0.1
APPROVALS_PORT=${APPROVALS_PORT:-8002}

# Celery
CELERY_BROKER_URL=redis://:${REDIS_PASSWORD}@${REDIS_HOST:-127.0.0.1}:${REDIS_PORT:-6379}/0
CELERY_RESULT_BACKEND=redis://:${REDIS_PASSWORD}@${REDIS_HOST:-127.0.0.1}:${REDIS_PORT:-6379}/2
CELERY_WORKER_CONCURRENCY=${CELERY_WORKER_CONCURRENCY:-4}
EOF

    chmod 640 "$env_file"
    log_info "Archivo de entorno systemd: ${env_file}"
}

main() {
    log_info "=== Configurador Hermes para Systemd ==="
    echo ""

    if verify_venv && verify_imports && verify_env_vars && create_systemd_env; then
        log_info "✅ Hermes configurado para systemd"
    else
        log_error "❌ Error en configuración"
        exit 1
    fi
}

main "$@"