#!/usr/bin/env bash
# scripts/staging-up.sh
# Levanta el entorno de staging completo
# Requiere .env.staging con valores reales

set -euo pipefail

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Directorio base
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ENV_FILE="${PROJECT_ROOT}/.env.staging"
COMPOSE_FILE="${PROJECT_ROOT}/docker-compose.staging.yml"

# Función para logging
log_info() { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

# Verificar que existe .env.staging
if [[ ! -f "$ENV_FILE" ]]; then
    log_error "No se encuentra .env.staging en $PROJECT_ROOT"
    log_error "Copia .env.staging.example a .env.staging y rellena los valores reales"
    exit 1
fi

# Verificar que existe docker-compose.staging.yml
if [[ ! -f "$COMPOSE_FILE" ]]; then
    log_error "No se encuentra docker-compose.staging.yml en $PROJECT_ROOT"
    exit 1
fi

# Validar variables críticas en .env.staging
log_info "Validando configuración..."

required_vars=(
    "AUDIT_DB_PASSWORD"
    "REDIS_PASSWORD"
    "JWT_SECRET_KEY"
    "FERNET_KEY"
    "AGENT_API_KEY_SUPERVISOR"
    "AGENT_API_KEY_DOG_INTAKE"
    "DOLIBARR_DB_PASSWORD"
    "DOLIBARR_DB_ROOT_PASSWORD"
    "JWT_SECRET_KEY"
    "FERNET_KEY"
)

warnings=()
for var in "${required_vars[@]}"; do
    if [[ -z "${!var:-}" || "${!var}" == "CHANGE_ME" ]]; then
        warnings+=("$var")
    fi
done

if [[ ${#warnings[@]} -gt 0 ]]; then
    log_warn "Las siguientes variables tienen valores por defecto o están vacías:"
    for var in "${warnings[@]}"; do
        log_warn "  - $var"
    done
    log_warn "Esto puede causar fallos en el arranque. Considera usar valores reales en .env.staging"
fi

# Verificar que Docker está disponible
if ! command -v docker &> /dev/null; then
    log_error "Docker no está instalado o no está en PATH"
    exit 1
fi

if ! command -v docker compose &> /dev/null && ! docker compose version &> /dev/null; then
    log_error "Docker Compose no está disponible"
    exit 1
fi

# Levantar servicios
log_info "Levantando entorno de staging..."
cd "$PROJECT_ROOT"

docker compose \
    --env-file .env.staging \
    -f docker-compose.staging.yml \
    up -d

# Esperar a que los servicios estén healthy
log_info "Esperando a que los servicios estén healthy..."

services=("audit-db" "redis" "mock-dolibarr" "dolibarr-db" "dolibarr" "ollama" "api" "worker" "approvals" "dashboard" "cloudflared")

for service in "${services[@]}"; do
    log_info "Esperando a $service..."
    timeout=180
    elapsed=0
    while [[ $elapsed -lt $timeout ]]; do
        status=$(docker compose --env-file .env.staging -f docker-compose.staging.yml ps --format json "$service" 2>/dev/null | jq -r '.[0].Health // "none"' 2>/dev/null || echo "unknown")
        if [[ "$status" == "healthy" ]] || [[ "$status" == "none" ]]; then
            # Para servicios sin healthcheck, verificar que estén running
            running=$(docker compose --env-file .env.staging -f docker-compose.staging.yml ps --format json "$service" 2>/dev/null | jq -r '.[0].State // ""' 2>/dev/null || echo "")
            if [[ "$running" == "running" ]]; then
                log_info "  $service: OK"
                break
            fi
        fi
        sleep 5
        elapsed=$((elapsed + 5))
    done
    
    if [[ $elapsed -ge $timeout ]]; then
        log_warn "$service no alcanzó estado healthy en ${timeout}s"
    fi
done

log_info "Entorno de staging levantado"
log_info "Ejecutar 'scripts/staging-status.sh' para ver el estado de los servicios"