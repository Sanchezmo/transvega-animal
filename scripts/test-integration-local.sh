#!/usr/bin/env bash
# =============================================================================
# Script para ejecutar tests de integración localmente con infraestructura de test
# =============================================================================
# Uso:
#   ./scripts/test-integration-local.sh              # Levanta servicios, init DB, ejecuta tests
#   ./scripts/test-integration-local.sh --no-up      # Solo ejecuta tests (servicios ya arriba)
#   ./scripts/test-integration-local.sh --keep-up    # No baja servicios al final
#   ./scripts/test-integration-local.sh --unit       # Ejecuta tests unitarios también
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="$PROJECT_ROOT/docker-compose.test.yml"
ENV_FILE="$PROJECT_ROOT/.env.test"
TEST_PROJECT="transvega-test"

# Colores
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

COMPOSE_CMD="docker compose -p $TEST_PROJECT -f $COMPOSE_FILE --env-file $ENV_FILE"

# Flags
DO_UP=true
DO_DOWN=true
RUN_UNIT=false
PYTEST_ARGS=()

# Parsear argumentos
while [[ $# -gt 0 ]]; do
    case $1 in
        --no-up)
            DO_UP=false
            shift
            ;;
        --keep-up)
            DO_DOWN=false
            shift
            ;;
        --unit)
            RUN_UNIT=true
            shift
            ;;
        --help|-h)
            echo "Uso: $0 [--no-up] [--keep-up] [--unit] [pytest-args...]"
            echo "  --no-up    : No levantar servicios (asume que ya están corriendo)"
            echo "  --keep-up  : No bajar servicios al finalizar"
            echo "  --unit     : Ejecutar tests unitarios también"
            exit 0
            ;;
        *)
            PYTEST_ARGS+=("$1")
            shift
            ;;
    esac
done

cd "$PROJECT_ROOT"

# Función para limpiar al salir
cleanup() {
    if [[ "$DO_DOWN" == true ]]; then
        echo -e "${YELLOW}Bajando servicios de test...${NC}"
        $COMPOSE_CMD down -v
    fi
}

trap cleanup EXIT

# 1. Levantar servicios de test
if [[ "$DO_UP" == true ]]; then
    echo -e "${GREEN}=== Levantando servicios de test (PostgreSQL + Redis) ===${NC}"
    $COMPOSE_CMD up -d

    echo -e "${GREEN}=== Esperando health checks ===${NC}"
    # Esperar a que postgres esté healthy
    for i in {1..30}; do
        if $COMPOSE_CMD ps postgres-test | grep -q "healthy"; then
            echo -e "${GREEN}✓ PostgreSQL test listo${NC}"
            break
        fi
        if [[ $i -eq 30 ]]; then
            echo -e "${RED}✗ Timeout esperando PostgreSQL${NC}"
            $COMPOSE_CMD logs postgres-test
            exit 1
        fi
        sleep 1
    done

    # Esperar a que redis esté healthy
    for i in {1..15}; do
        if $COMPOSE_CMD ps redis-test | grep -q "healthy"; then
            echo -e "${GREEN}✓ Redis test listo${NC}"
            break
        fi
        if [[ $i -eq 15 ]]; then
            echo -e "${RED}✗ Timeout esperando Redis${NC}"
            $COMPOSE_CMD logs redis-test
            exit 1
        fi
        sleep 1
    done
fi

# 2. Inicializar schema de base de datos
echo -e "${GREEN}=== Inicializando schema de base de datos ===${NC}"
export $(grep -v '^#' "$ENV_FILE" | xargs)
cd "$PROJECT_ROOT/services/integration-api"
python -c "
import asyncio
import sys
sys.path.insert(0, '.')
from app.core.database import init_db
asyncio.run(init_db())
print('✓ Schema inicializado correctamente')
"

# 3. Ejecutar tests
echo -e "${GREEN}=== Ejecutando tests de integración ===${NC}"
cd "$PROJECT_ROOT"

# Cargar variables de entorno para pytest
export $(grep -v '^#' "$ENV_FILE" | xargs)

# Args por defecto para pytest
DEFAULT_ARGS=(
    "tests/integration"
    -v
    --tb=short
    --asyncio-mode=auto
)

# Si no se pasaron args personalizados, usar defaults
if [[ ${#PYTEST_ARGS[@]} -eq 0 ]]; then
    PYTEST_ARGS=("${DEFAULT_ARGS[@]}")
fi

# Ejecutar pytest
if python -m pytest "${PYTEST_ARGS[@]}"; then
    echo -e "${GREEN}=== Tests de integración: PASARON ===${NC}"
    INTEGRATION_RESULT=0
else
    echo -e "${RED}=== Tests de integración: FALLARON ===${NC}"
    INTEGRATION_RESULT=1
fi

# 4. Tests unitarios (opcional)
if [[ "$RUN_UNIT" == true ]]; then
    echo -e "${GREEN}=== Ejecutando tests unitarios ===${NC}"
    if python -m pytest tests/unit -v --tb=short --asyncio-mode=auto; then
        echo -e "${GREEN}=== Tests unitarios: PASARON ===${NC}"
        UNIT_RESULT=0
    else
        echo -e "${RED}=== Tests unitarios: FALLARON ===${NC}"
        UNIT_RESULT=1
    fi
fi

# Resumen final
echo ""
echo -e "${GREEN}=== RESUMEN ===${NC}"
echo -e "Integración: $([ $INTEGRATION_RESULT -eq 0 ] && echo -e "${GREEN}PASS${NC}" || echo -e "${RED}FAIL${NC}")"
if [[ "$RUN_UNIT" == true ]]; then
    echo -e "Unitarios:   $([ $UNIT_RESULT -eq 0 ] && echo -e "${GREEN}PASS${NC}" || echo -e "${RED}FAIL${NC}")"
fi

# Exit code
if [[ "$RUN_UNIT" == true ]]; then
    exit $((INTEGRATION_RESULT || UNIT_RESULT))
else
    exit $INTEGRATION_RESULT
fi