#!/usr/bin/env bash
# scripts/configure/services.sh
# Instala y configura servicios systemd para Transvega
# Uso: sudo ./scripts/configure/services.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

if [[ -f "${PROJECT_ROOT}/.env" ]]; then
    set -a
    source "${PROJECT_ROOT}/.env"
    set +a
fi

VENV_DIR="${PROJECT_ROOT}/.venv"
PROJECT_USER="${SUDO_USER:-$(logname 2>/dev/null || echo $USER)}"
PROJECT_GROUP="$(id -gn "$PROJECT_USER" 2>/dev/null || echo "$PROJECT_USER")"

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

check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "Requiere root (sudo)"
        exit 1
    fi
}

install_service() {
    local name="$1"
    local template="${PROJECT_ROOT}/config/systemd/${name}.service.template"
    local target="/etc/systemd/system/${name}.service"

    if [[ ! -f "$template" ]]; then
        log_warn "Template no encontrado: ${template} (saltando ${name})"
        return 0
    fi

    log_step "Instalando servicio ${name}..."

    # Sustituir variables en template
    sed \
        -e "s|{{PROJECT_ROOT}}|${PROJECT_ROOT}|g" \
        -e "s|{{VENV_DIR}}|${VENV_DIR}|g" \
        -e "s|{{PROJECT_USER}}|${PROJECT_USER}|g" \
        -e "s|{{PROJECT_GROUP}}|${PROJECT_GROUP}|g" \
        -e "s|{{API_PORT}}|${API_PORT:-8000}|g" \
        -e "s|{{APPROVALS_PORT}}|${APPROVALS_PORT:-8002}|g" \
        -e "s|{{WORKER_CONCURRENCY}}|${CELERY_WORKER_CONCURRENCY:-4}|g" \
        "$template" > "$target"

    systemctl daemon-reload
    systemctl enable "$name" >/dev/null 2>&1
    log_info "Servicio ${name} instalado y habilitado"
}

create_templates() {
    log_step "Creando templates systemd si no existen..."

    mkdir -p "${PROJECT_ROOT}/config/systemd"

    # Hermes API service
    if [[ ! -f "${PROJECT_ROOT}/config/systemd/hermes.service.template" ]]; then
        cat > "${PROJECT_ROOT}/config/systemd/hermes.service.template" <<'EOF'
[Unit]
Description=Transvega Hermes API
After=network.target postgresql.service redis.service mariadb.service ollama.service
Wants=postgresql.service redis.service mariadb.service ollama.service

[Service]
Type=exec
User={{PROJECT_USER}}
Group={{PROJECT_GROUP}}
WorkingDirectory={{PROJECT_ROOT}}
EnvironmentFile={{PROJECT_ROOT}}/.env
Environment=PYTHONPATH={{PROJECT_ROOT}}:{{PROJECT_ROOT}}/services/integration-api:{{PROJECT_ROOT}}/services/task-queue:{{PROJECT_ROOT}}/adapters:{{PROJECT_ROOT}}/agents
ExecStart={{VENV_DIR}}/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port {{API_PORT}} --workers 1
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

# Seguridad
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths={{PROJECT_ROOT}}/hermes_data {{PROJECT_ROOT}}/hermes_logs /var/log/transvega

[Install]
WantedBy=multi-user.target
EOF
    fi

    # Hermes Worker service
    if [[ ! -f "${PROJECT_ROOT}/config/systemd/hermes-worker.service.template" ]]; then
        cat > "${PROJECT_ROOT}/config/systemd/hermes-worker.service.template" <<'EOF'
[Unit]
Description=Transvega Hermes Celery Worker
After=network.target redis.service postgresql.service hermes.service
Wants=redis.service postgresql.service hermes.service

[Service]
Type=exec
User={{PROJECT_USER}}
Group={{PROJECT_GROUP}}
WorkingDirectory={{PROJECT_ROOT}}
EnvironmentFile={{PROJECT_ROOT}}/.env
Environment=PYTHONPATH={{PROJECT_ROOT}}:{{PROJECT_ROOT}}/services/integration-api:{{PROJECT_ROOT}}/services/task-queue:{{PROJECT_ROOT}}/adapters:{{PROJECT_ROOT}}/agents
ExecStart={{VENV_DIR}}/bin/celery -A tasks.celery_app worker --loglevel=info --concurrency={{WORKER_CONCURRENCY}} --queues=high,default,low,approvals,notifications
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

# Seguridad
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths={{PROJECT_ROOT}}/hermes_data {{PROJECT_ROOT}}/invoice_worker_logs /var/log/transvega /data/invoices /data/dogs

[Install]
WantedBy=multi-user.target
EOF
    fi

    # Approvals service
    if [[ ! -f "${PROJECT_ROOT}/config/systemd/approvals.service.template" ]]; then
        cat > "${PROJECT_ROOT}/config/systemd/approvals.service.template" <<'EOF'
[Unit]
Description=Transvega Approvals Service
After=network.target postgresql.service redis.service
Wants=postgresql.service redis.service

[Service]
Type=exec
User={{PROJECT_USER}}
Group={{PROJECT_GROUP}}
WorkingDirectory={{PROJECT_ROOT}}/services/approval-service
EnvironmentFile={{PROJECT_ROOT}}/.env
Environment=PYTHONPATH={{PROJECT_ROOT}}:{{PROJECT_ROOT}}/services/approval-service
ExecStart={{VENV_DIR}}/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port {{APPROVALS_PORT}}
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

# Seguridad
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/log/transvega

[Install]
WantedBy=multi-user.target
EOF
    fi

    log_info "Templates systemd verificados/creados"
}

main() {
    log_info "=== Configurador Servicios Systemd ==="
    log_info "Usuario: ${PROJECT_USER} | Grupo: ${PROJECT_GROUP}"
    log_info "Virtualenv: ${VENV_DIR}"
    echo ""

    check_root
    create_templates

    install_service "hermes"
    install_service "hermes-worker"
    install_service "approvals"

    log_info "✅ Servicios systemd instalados"
    echo ""
    echo "Para iniciar:"
    echo "  systemctl start hermes hermes-worker approvals"
    echo ""
    echo "Para ver logs:"
    echo "  journalctl -u hermes -f"
    echo "  journalctl -u hermes-worker -f"
    echo "  journalctl -u approvals -f"
}

main "$@"