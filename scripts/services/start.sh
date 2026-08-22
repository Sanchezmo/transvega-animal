#!/usr/bin/env bash
# scripts/services/start.sh
# Inicia todos los servicios Transvega nativos
# Uso: sudo ./scripts/services/start.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

if [[ -f "${PROJECT_ROOT}/.env" ]]; then
    set -a
    source "${PROJECT_ROOT}/.env"
    set +a
fi

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

start_service() {
    local name="$1"
    local description="$2"

    log_step "Iniciando ${description}..."

    if systemctl is-active --quiet "$name"; then
        log_info "${description}: YA ACTIVO"
        return 0
    fi

    if systemctl start "$name"; then
        sleep 2
        if systemctl is-active --quiet "$name"; then
            log_info "${description}: INICIADO ✓"
        else
            log_error "${description}: FALLÓ AL INICIAR"
            systemctl status "$name" --no-pager
            return 1
        fi
    else
        log_error "${description}: ERROR AL INICIAR"
        return 1
    fi
}

main() {
    log_info "=== Iniciando Servicios Transvega ==="
    echo ""

    check_root

    # Orden de inicio: BD -> Apache -> Ollama -> Cloudflare -> App services
    start_service "mariadb" "MariaDB (Dolibarr)"
    start_service "postgresql" "PostgreSQL (Auditoría)"
    start_service "redis-server" "Redis"
    start_service "apache2" "Apache2 (Dolibarr)"
    start_service "ollama" "Ollama"
    start_service "cloudflared" "Cloudflare Tunnel"

    # Servicios aplicación
    start_service "hermes" "Hermes API"
    start_service "hermes-worker" "Hermes Worker"
    start_service "approvals" "Approvals Service"

    log_info "✅ Todos los servicios iniciados"
    echo ""
    echo "Verificar estado: make status"
}

main "$@"