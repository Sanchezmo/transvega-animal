#!/usr/bin/env bash
# scripts/configure/mariadb.sh
# Verifica configuración MariaDB (idempotente)
# Uso: sudo ./scripts/configure/mariadb.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

if [[ -f "${PROJECT_ROOT}/.env" ]]; then
    set -a
    source "${PROJECT_ROOT}/.env"
    set +a
fi

DOLIBARR_DB_HOST="${DOLIBARR_DB_HOST:-127.0.0.1}"
DOLIBARR_DB_PORT="${DOLIBARR_DB_PORT:-3306}"
DOLIBARR_DB_NAME="${DOLIBARR_DB_NAME:-dolibarr}"
DOLIBARR_DB_USER="${DOLIBARR_DB_USER:-dolibarr}"
DOLIBARR_DB_PASSWORD="${DOLIBARR_DB_PASSWORD:-}"
DOLIBARR_DB_ROOT_PASSWORD="${DOLIBARR_DB_ROOT_PASSWORD:-}"

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
        log_error "Requiere root"
        exit 1
    fi
}

verify_service() {
    log_step "Verificando servicio MariaDB..."
    if systemctl is-active --quiet mariadb; then
        log_info "Servicio MariaDB: ACTIVO"
    else
        log_warn "Servicio MariaDB: INACTIVO - iniciando"
        systemctl start mariadb
        sleep 2
    fi
}

verify_config() {
    log_step "Verificando configuración..."
    local conf="/etc/mysql/mariadb.conf.d/99-transvega.cnf"
    if [[ -f "$conf" ]]; then
        log_info "Configuración Transvega: PRESENTE"
    else
        log_warn "Configuración Transvega: AUSENTE (ejecutar install/mariadb.sh)"
    fi
}

verify_database() {
    log_step "Verificando base de datos y usuario..."

    if mysql -u root -p"${DOLIBARR_DB_ROOT_PASSWORD}" -e "SELECT 1" >/dev/null 2>&1; then
        log_info "Root access: OK"
    else
        log_error "Root access: FALLIDO"
        return 1
    fi

    if mysql -u "${DOLIBARR_DB_USER}" -p"${DOLIBARR_DB_PASSWORD}" -h "${DOLIBARR_DB_HOST}" -P "${DOLIBARR_DB_PORT}" -e "USE \`${DOLIBARR_DB_NAME}\`; SELECT 1" >/dev/null 2>&1; then
        log_info "Usuario dolibarr: OK"
    else
        log_error "Usuario dolibarr: FALLIDO"
        return 1
    fi

    local charset
    charset=$(mysql -u root -p"${DOLIBARR_DB_ROOT_PASSWORD}" -sNe "SHOW VARIABLES LIKE 'character_set_server'" 2>/dev/null | awk '{print $2}')
    log_info "Character set: ${charset}"

    local collation
    collation=$(mysql -u root -p"${DOLIBARR_DB_ROOT_PASSWORD}" -sNe "SHOW VARIABLES LIKE 'collation_server'" 2>/dev/null | awk '{print $2}')
    log_info "Collation: ${collation}"
}

main() {
    log_info "=== Verificador MariaDB ==="
    check_root
    verify_service
    verify_config
    if verify_database; then
        log_info "✅ MariaDB verificado"
    else
        log_error "❌ Error en verificación"
        exit 1
    fi
}

main "$@"