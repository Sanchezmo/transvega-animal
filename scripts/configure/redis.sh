#!/usr/bin/env bash
# scripts/configure/redis.sh
# Verifica configuración Redis (idempotente)
# Uso: sudo ./scripts/configure/redis.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

if [[ -f "${PROJECT_ROOT}/.env" ]]; then
    set -a
    source "${PROJECT_ROOT}/.env"
    set +a
fi

REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
REDIS_PORT="${REDIS_PORT:-6379}"
REDIS_PASSWORD="${REDIS_PASSWORD:-}"
REDIS_MAXMEMORY="${REDIS_MAXMEMORY:-512mb}"
REDIS_MAXMEMORY_POLICY="${REDIS_MAXMEMORY_POLICY:-allkeys-lru}"

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
    log_step "Verificando servicio Redis..."
    if systemctl is-active --quiet redis-server; then
        log_info "Servicio Redis: ACTIVO"
    else
        log_warn "Servicio Redis: INACTIVO - iniciando"
        systemctl start redis-server
        sleep 1
    fi
}

verify_config() {
    log_step "Verificando configuración..."

    if redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}" -a "${REDIS_PASSWORD}" ping | grep -q "PONG"; then
        log_info "Conexión: OK"
    else
        log_error "Conexión: FALLIDA"
        return 1
    fi

    local maxmemory
    maxmemory=$(redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}" -a "${REDIS_PASSWORD}" CONFIG GET maxmemory | tail -1)
    log_info "Maxmemory: ${maxmemory}"

    local policy
    policy=$(redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}" -a "${REDIS_PASSWORD}" CONFIG GET maxmemory-policy | tail -1)
    log_info "Maxmemory-policy: ${policy}"

    local used
    used=$(redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}" -a "${REDIS_PASSWORD}" INFO memory | grep "used_memory_human:" | cut -d: -f2 | tr -d '\r')
    log_info "Memoria usada: ${used}"
}

main() {
    log_info "=== Verificador Redis ==="
    check_root
    verify_service
    if verify_config; then
        log_info "✅ Redis verificado"
    else
        log_error "❌ Error en verificación"
        exit 1
    fi
}

main "$@"