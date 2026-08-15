#!/usr/bin/env bash
# scripts/staging-status.sh
# Muestra el estado de los servicios de staging

set -euo pipefail

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Directorio base
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Función para logging
log_info() { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

cd "$PROJECT_ROOT"

if [[ ! -f ".env.staging" ]]; then
    echo -e "${RED}[ERROR]${NC} No se encuentra .env.staging"
    exit 1
fi

if [[ ! -f "docker-compose.staging.yml" ]]; then
    echo -e "${RED}[ERROR]${NC} No se encuentra docker-compose.staging.yml"
    exit 1
fi

log_info "Estado de servicios de staging:"
echo ""

# Mostrar estado de servicios
docker compose \
    --env-file .env.staging \
    -f docker-compose.staging.yml \
    ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"

echo ""
log_info "Health checks:"

# Verificar health checks de servicios con healthcheck
services_with_healthcheck=("audit-db" "redis" "mock-dolibarr" "dolibarr-db" "dolibarr" "ollama" "api" "approvals" "dashboard")

for service in "${services_with_healthcheck[@]}"; do
    health=$(docker compose --env-file .env.staging -f docker-compose.staging.yml ps --format json "$service" 2>/dev/null | jq -r '.[0].Health // "none"' 2>/dev/null || echo "unknown")
    state=$(docker compose --env-file .env.staging -f docker-compose.staging.yml ps --format json "$service" 2>/dev/null | jq -r '.[0].State // "unknown"' 2>/dev/null || echo "unknown")
    
    if [[ "$health" == "healthy" ]]; then
        echo -e "  ${GREEN}✓${NC} $service: $state ($health)"
    elif [[ "$health" == "unhealthy" ]]; then
        echo -e "  ${RED}✗${NC} $service: $state ($health)"
    elif [[ "$health" == "starting" ]]; then
        echo -e "  ${YELLOW}⟳${NC} $service: $state ($health)"
    else
        echo -e "  ${YELLOW}?${NC} $service: $state (sin healthcheck)"
    fi
done

echo ""
log_info "Redes Docker:"
docker network ls --filter "name=transvega-animal" --format "table {{.Name}}\t{{.Driver}}\t{{.Scope}}"

echo ""
log_info "Volúmenes:"
docker volume ls --filter "name=transvega-animal" --format "table {{.Name}}\t{{.Driver}}"