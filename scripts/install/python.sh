#!/usr/bin/env bash
# scripts/install/python.sh
# Crea virtualenv Python e instala dependencias (idempotente)
# Uso: ./scripts/install/python.sh

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
PYTHON_VERSION="${PYTHON_VERSION:-3.11}"

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

check_python() {
    log_step "Verificando Python ${PYTHON_VERSION}..."

    if ! command -v "python${PYTHON_VERSION}" >/dev/null 2>&1; then
        log_error "python${PYTHON_VERSION} no encontrado"
        log_info "Instalar con: apt-get install python${PYTHON_VERSION} python${PYTHON_VERSION}-venv python${PYTHON_VERSION}-dev"
        exit 1
    fi

    local version
    version=$(python${PYTHON_VERSION} --version)
    log_info "Python: ${version}"
}

create_venv() {
    log_step "Creando virtualenv en ${VENV_DIR}..."

    if [[ -d "$VENV_DIR" ]]; then
        log_info "Virtualenv ya existe"
        # Verificar versión Python
        local venv_python
        venv_python=$("$VENV_DIR/bin/python" --version 2>&1 | awk '{print $2}' | cut -d. -f1,2)
        if [[ "$venv_python" != "$PYTHON_VERSION" ]]; then
            log_warn "Virtualenv usa Python ${venv_python}, esperado ${PYTHON_VERSION}. Recreando..."
            rm -rf "$VENV_DIR"
        else
            return 0
        fi
    fi

    python${PYTHON_VERSION} -m venv "$VENV_DIR"
    log_info "Virtualenv creado"
}

upgrade_pip() {
    log_step "Actualizando pip/setuptools/wheel..."

    "$VENV_DIR/bin/pip" install --upgrade pip setuptools wheel -q
    log_info "pip actualizado"
}

install_requirements() {
    log_step "Instalando dependencias Python..."

    local req_files=(
        "${PROJECT_ROOT}/services/integration-api/requirements.txt"
        "${PROJECT_ROOT}/services/approval-service/requirements.txt"
        "${PROJECT_ROOT}/services/task-queue/requirements.txt"
    )

    for req in "${req_files[@]}"; do
        if [[ -f "$req" ]]; then
            log_info "Instalando desde: ${req}"
            "$VENV_DIR/bin/pip" install -r "$req" -q
        else
            log_warn "No encontrado: ${req}"
        fi
    done

    # Instalar playwright para worker (navegador headless)
    log_info "Instalando Playwright..."
    "$VENV_DIR/bin/pip" install playwright -q
    "$VENV_DIR/bin/playwright" install chromium --with-deps 2>/dev/null || {
        log_warn "Playwright install chromium falló (ejecutar manualmente: .venv/bin/playwright install chromium --with-deps)"
    }

    log_info "Dependencias instaladas"
}

verify_imports() {
    log_step "Verificando imports críticos..."

    local test_script="
import sys
sys.path.insert(0, '${PROJECT_ROOT}')
sys.path.insert(0, '${PROJECT_ROOT}/services/integration-api')
sys.path.insert(0, '${PROJECT_ROOT}/services/task-queue')
sys.path.insert(0, '${PROJECT_ROOT}/adapters')
sys.path.insert(0, '${PROJECT_ROOT}/agents')

try:
    import fastapi
    import uvicorn
    import pydantic
    import pydantic_settings
    import sqlalchemy
    import asyncpg
    import redis
    import celery
    import httpx
    import structlog
    import cryptography
    import jwt
    print('✓ Core dependencies OK')
except ImportError as e:
    print(f'✗ Import error: {e}')
    sys.exit(1)

try:
    from app.core.config import get_settings
    settings = get_settings()
    print(f'✓ Settings loaded: {settings.APP_NAME}')
except Exception as e:
    print(f'✗ Settings error: {e}')
    sys.exit(1)

try:
    from tasks.celery_app import celery_app
    print('✓ Celery app loaded')
except Exception as e:
    print(f'✗ Celery error: {e}')
    sys.exit(1)
"

    if "$VENV_DIR/bin/python" -c "$test_script"; then
        log_info "Todos los imports verificados"
    else
        log_error "Falló verificación de imports"
        return 1
    fi

    return 0
}

create_activate_script() {
    log_step "Creando script de activación helper..."

    cat > "${PROJECT_ROOT}/activate.sh" <<'EOF'
#!/usr/bin/env bash
# Helper para activar virtualenv Transvega
# Uso: source activate.sh

VENV_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.venv"

if [[ -f "${VENV_DIR}/bin/activate" ]]; then
    source "${VENV_DIR}/bin/activate"
    export PYTHONPATH="${VENV_DIR}/../:${VENV_DIR}/../services/integration-api:${VENV_DIR}/../services/task-queue:${VENV_DIR}/../adapters:${VENV_DIR}/../agents"
    echo "✅ Transvega virtualenv activado"
    echo "PYTHONPATH: ${PYTHONPATH}"
else
    echo "❌ Virtualenv no encontrado en ${VENV_DIR}"
    return 1
fi
EOF

    chmod +x "${PROJECT_ROOT}/activate.sh"
    log_info "Helper creado: ${PROJECT_ROOT}/activate.sh"
}

main() {
    log_info "=== Instalador Python Virtualenv ==="
    log_info "Directorio: ${VENV_DIR}"
    log_info "Python: ${PYTHON_VERSION}"
    echo ""

    check_python
    create_venv
    upgrade_pip
    install_requirements

    if verify_imports; then
        create_activate_script
        log_info "✅ Virtualenv Python configurado correctamente"
        echo ""
        echo "Para activar:"
        echo "  source ${PROJECT_ROOT}/activate.sh"
        echo ""
        echo "Python: ${VENV_DIR}/bin/python"
        echo "Pip:    ${VENV_DIR}/bin/pip"
    else
        log_error "❌ Error en verificación de imports"
        exit 1
    fi
}

main "$@"