#!/usr/bin/env bash
# scripts/configure/postgresql.sh
# Verifica configuración PostgreSQL (idempotente)
# Uso: sudo ./scripts/configure/postgresql.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

if [[ -f "${PROJECT_ROOT}/.env" ]]; then
    set -a
    source "${PROJECT_ROOT}/.env"
    set +a
fi

AUDIT_DB_HOST="${AUDIT_DB_HOST:-127.0.0.1}"
AUDIT_DB_PORT="${AUDIT_DB_PORT:-5432}"
AUDIT_DB_NAME="${AUDIT_DB_NAME:-audit}"
AUDIT_DB_USER="${AUDIT_DB_USER:-audit}"
AUDIT_DB_PASSWORD="${AUDIT_DB_PASSWORD:-}"

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
    log_step "Verificando servicio PostgreSQL..."
    if systemctl is-active --quiet postgresql; then
        log_info "Servicio PostgreSQL: ACTIVO"
    else
        log_warn "Servicio PostgreSQL: INACTIVO - iniciando"
        systemctl start postgresql
        sleep 2
    fi
}

verify_database() {
    log_step "Verificando base de datos auditoría..."

    if PGPASSWORD="${AUDIT_DB_PASSWORD}" psql -h "${AUDIT_DB_HOST}" -p "${AUDIT_DB_PORT}" -U "${AUDIT_DB_USER}" -d "${AUDIT_DB_NAME}" -c "SELECT 1" >/dev/null 2>&1; then
        log_info "Conexión: OK"
    else
        log_error "Conexión: FALLIDA"
        return 1
    fi

    local tables
    tables=$(PGPASSWORD="${AUDIT_DB_PASSWORD}" psql -h "${AUDIT_DB_HOST}" -p "${AUDIT_DB_PORT}" -U "${AUDIT_DB_USER}" -d "${AUDIT_DB_NAME}" -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND (table_name LIKE 'audit_%' OR table_name IN ('approval_requests','task_queue','agent_sessions'))")
    log_info "Tablas auditoría: ${tables}"

    local extensions
    extensions=$(PGPASSWORD="${AUDIT_DB_PASSWORD}" psql -h "${AUDIT_DB_HOST}" -p "${AUDIT_DB_PORT}" -U "${AUDIT_DB_USER}" -d "${AUDIT_DB_NAME}" -tAc "SELECT extname FROM pg_extension WHERE extname IN ('uuid-ossp','pgcrypto')")
    log_info "Extensiones: ${extensions}"
}

main() {
    log_info "=== Verificador PostgreSQL ==="
    check_root
    verify_service
    if verify_database; then
        log_info "✅ PostgreSQL verificado"
    else
        log_error "❌ Error en verificación"
        exit 1
    fi
}

main "$@"