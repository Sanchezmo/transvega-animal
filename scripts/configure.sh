#!/usr/bin/env bash
# scripts/configure.sh
# Orquestador de configuración post-instalación
# Uso: ./scripts/configure.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Cargar .env
if [[ -f "${PROJECT_ROOT}/.env" ]]; then
    set -a
    source "${PROJECT_ROOT}/.env"
    set +a
fi

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
        log_error "Este script requiere root (sudo)"
        exit 1
    fi
}

run_script() {
    local script="$1"
    local description="$2"

    log_step "$description"

    if [[ -f "${SCRIPT_DIR}/configure/${script}" ]]; then
        bash "${SCRIPT_DIR}/configure/${script}"
    else
        log_warn "Script no encontrado (opcional): ${SCRIPT_DIR}/configure/${script}"
    fi
}

main() {
    echo ""
    echo "=========================================="
    echo "  TRANSVEGA - CONFIGURACIÓN POST-INSTALACIÓN"
    echo "=========================================="
    echo ""

    check_root

    # 1. Apache VirtualHost para Dolibarr
    run_script "apache.sh" "Configurando Apache VirtualHost para Dolibarr (puerto 8080)"

    # 2. Dolibarr conf.php (ya hecho en install, pero verificar)
    run_script "dolibarr.sh" "Verificando configuración Dolibarr"

    # 3. MariaDB (ya configurado en install)
    run_script "mariadb.sh" "Verificando configuración MariaDB"

    # 4. PostgreSQL (ya configurado en install)
    run_script "postgresql.sh" "Verificando configuración PostgreSQL"

    # 5. Redis (ya configurado en install)
    run_script "redis.sh" "Verificando configuración Redis"

    # 6. Cloudflare Tunnel ingress
    run_script "cloudflare.sh" "Configurando Cloudflare Tunnel ingress"

    # 7. Systemd services
    run_script "services.sh" "Instalando y habilitando servicios systemd"

    # 8. Hermes variables
    run_script "hermes.sh" "Configurando variables de entorno para systemd"

    echo ""
    echo "=========================================="
    echo "  CONFIGURACIÓN COMPLETADA"
    echo "=========================================="
    echo ""
    log_info "Próximos pasos:"
    echo "  1. Iniciar servicios:"
    echo "     sudo ${SCRIPT_DIR}/services/start.sh"
    echo ""
    echo "  2. Verificar estado:"
    echo "     make status"
    echo ""
    echo "  3. Health checks:"
    echo "     make check"
    echo ""
}

main "$@"