#!/usr/bin/env bash
# scripts/staging-ollama-pull.sh
# Descarga modelos de Ollama para staging
# Lee OLLAMA_MODEL y OLLAMA_VISION_MODEL desde .env.staging

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

# Cargar variables de entorno
set -a
source "$ENV_FILE"
set +a

# Validar variables requeridas
if [[ -z "${OLLAMA_MODEL:-}" || "${OLLAMA_MODEL}" == "CHANGE_ME" ]]; then
    log_error "OLLAMA_MODEL no configurado en .env.staging"
    exit 1
fi

if [[ -z "${OLLAMA_VISION_MODEL:-}" || "${OLLAMA_VISION_MODEL}" == "CHANGE_ME" ]]; then
    log_error "OLLAMA_VISION_MODEL no configurado en .env.staging"
    exit 1
fi

# Verificar que el contenedor de Ollama está corriendo
if ! docker ps --format '{{.Names}}' | grep -q "^transvega-ollama-staging$"; then
    log_error "Contenedor transvega-ollama-staging no está corriendo"
    log_error "Ejecuta primero: make staging-up"
    exit 1
fi

# Descargar modelo principal
log_info "Descargando modelo principal: $OLLAMA_MODEL"
docker exec transvega-ollama-staging ollama pull "$OLLAMA_MODEL"

# Descargar modelo vision si es diferente
if [[ "$OLLAMA_VISION_MODEL" != "$OLLAMA_MODEL" ]]; then
    log_info "Descargando modelo vision: $OLLAMA_VISION_MODEL"
    docker exec transvega-ollama-staging ollama pull "$OLLAMA_VISION_MODEL"
else
    log_info "OLLAMA_VISION_MODEL es igual a OLLAMA_MODEL, saltando descarga duplicada"
fi

log_info "Modelos descargados correctamente"
docker exec transvega-ollama-staging ollama list