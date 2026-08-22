#!/usr/bin/env bash
# scripts/services/stop.sh
# Detiene todos los servicios Transvega nativos
# Uso: sudo ./scripts/services/stop.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

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

stop_service() {
    local name="$1"
    local description="$2"

    log_step "Deteniendo ${description}..."

    if ! systemctl is-active --quiet "$name"; then
        log_info "${description}: YA DETENIDO"
        return 0
    fi

    if systemctl stop "$name"; then
        log_info "${description}: DETENIDO ✓"
    else
        log_error "${description}: ERROR AL DETENER"
        return 1
    fi
}

main() {
    log_info "=== Deteniendo Servicios Transvega ==="
    echo ""

    check_root

    # Orden inverso: App services -> Cloudflare -> Ollama -> Apache -> BD
    stop_service "approvals" "Approvals Service"
    stop_service "hermes-worker" "Hermes Worker"
    stop_service "hermes" "Hermes API"
    stop_service "cloudflared" "Cloudflare Tunnel"
    stop_service "ollama" "Ollama"
    stop_service "apache2" "Apache2"
    stop_service "redis-server" "Redis"
    stop_service "postgresql" "PostgreSQL"
    stop_service "mariadb" "MariaDB"

    log_info "✅ Todos los servicios detenidos"
}

main "$@"