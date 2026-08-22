#!/usr/bin/env bash
# scripts/install/ollama.sh
# Instala Ollama nativo y crea modelo transvega-local (idempotente)
# Uso: ./scripts/install/ollama.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

# Cargar .env
if [[ -f "${PROJECT_ROOT}/.env" ]]; then
    set -a
    source "${PROJECT_ROOT}/.env"
    set +a
fi

# Configuración
OLLAMA_HOST="${OLLAMA_HOST:-127.0.0.1}"
OLLAMA_PORT="${OLLAMA_PORT:-11434}"
OLLAMA_ENDPOINT="${OLLAMA_ENDPOINT:-http://${OLLAMA_HOST}:${OLLAMA_PORT}}"
OLLAMA_MODEL="${OLLAMA_MODEL:-transvega-local}"
OLLAMA_BASE_MODEL="${OLLAMA_BASE_MODEL:-qwen3.5:4b-q4_K_M}"

MODELFILE_SOURCE="${PROJECT_ROOT}/infrastructure/ollama/Modelfile"

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

install_ollama() {
    log_step "Instalando Ollama..."

    if command -v ollama >/dev/null 2>&1; then
        local version
        version=$(ollama --version 2>/dev/null || echo "unknown")
        log_info "Ollama ya instalado: ${version}"
        return 0
    fi

    log_info "Descargando e instalando Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh

    log_info "Ollama instalado"
}

verify_ollama_binary() {
    log_step "Verificando binario Ollama..."

    if ! command -v ollama >/dev/null 2>&1; then
        log_error "ollama no encontrado en PATH"
        return 1
    fi

    local version
    version=$(ollama --version)
    log_info "Ollama version: ${version}"

    return 0
}

enable_ollama_service() {
    log_step "Habilitando servicio Ollama (systemd)..."

    # El instalador de Ollama ya crea el servicio systemd
    if systemctl list-unit-files | grep -q "^ollama.service"; then
        systemctl enable ollama >/dev/null 2>&1
        systemctl start ollama
        log_info "Servicio Ollama habilitado e iniciado"
    else
        log_warn "Servicio systemd ollama no encontrado (instalador puede haber fallado)"
        log_info "Intentando iniciar manualmente..."
        ollama serve &
        sleep 3
    fi

    # Esperar a que el servicio esté listo
    local max_wait=30
    local waited=0
    while [[ $waited -lt $max_wait ]]; do
        if curl -sf "${OLLAMA_ENDPOINT}/api/tags" >/dev/null 2>&1; then
            log_info "Ollama API respondiendo en ${OLLAMA_ENDPOINT}"
            return 0
        fi
        sleep 1
        waited=$((waited + 1))
    done

    log_error "Ollama no respondió en ${max_wait}s"
    return 1
}

create_model() {
    log_step "Creando modelo ${OLLAMA_MODEL} desde ${OLLAMA_BASE_MODEL}..."

    # Verificar si el modelo ya existe
    if ollama list | grep -q "^${OLLAMA_MODEL}"; then
        log_info "Modelo ${OLLAMA_MODEL} ya existe"
        return 0
    fi

    # Verificar Modelfile
    local modelfile_path
    if [[ -f "$MODELFILE_SOURCE" ]]; then
        modelfile_path="$MODELFILE_SOURCE"
        log_info "Usando Modelfile: ${MODELFILE_SOURCE}"
    else
        log_warn "Modelfile no encontrado en ${MODELFILE_SOURCE}, creando fallback"
        modelfile_path="/tmp/Modelfile-transvega"
        cat > "$modelfile_path" <<EOF
FROM ${OLLAMA_BASE_MODEL}
PARAMETER num_thread 10
PARAMETER num_ctx 8192
PARAMETER temperature 0.1
PARAMETER top_p 0.9
PARAMETER repeat_penalty 1.1
EOF
    fi

    # Crear modelo
    log_info "Creando modelo (esto puede tardar varios minutos)..."
    if ollama create "${OLLAMA_MODEL}" -f "$modelfile_path"; then
        log_info "Modelo ${OLLAMA_MODEL} creado exitosamente"
    else
        log_error "Error creando modelo ${OLLAMA_MODEL}"
        return 1
    fi
}

verify_model() {
    log_step "Verificando modelo..."

    if ollama list | grep -q "^${OLLAMA_MODEL}"; then
        local size
        size=$(ollama list | grep "^${OLLAMA_MODEL}" | awk '{print $2}')
        log_info "Modelo ${OLLAMA_MODEL} disponible (${size})"
    else
        log_error "Modelo ${OLLAMA_MODEL} no encontrado"
        return 1
    fi

    # Test rápido de generación
    log_info "Probando generación..."
    local test_response
    test_response=$(timeout 30 ollama run "${OLLAMA_MODEL}" "Responde solo: OK" 2>/dev/null | head -1 || echo "timeout")
    if [[ "$test_response" == *"OK"* ]]; then
        log_info "Test de generación: OK"
    else
        log_warn "Test de generación: ${test_response} (puede ser normal en primera ejecución)"
    fi

    return 0
}

verify_api() {
    log_step "Verificando API Ollama..."

    # Tags endpoint
    local tags
    tags=$(curl -sf "${OLLAMA_ENDPOINT}/api/tags" | jq -r '.models[].name' 2>/dev/null | grep "^${OLLAMA_MODEL}$" || echo "")
    if [[ -n "$tags" ]]; then
        log_info "API /api/tags: Modelo listado correctamente"
    else
        log_warn "API /api/tags: Modelo no listado (verificar)"
    fi

    # Version endpoint
    local version
    version=$(curl -sf "${OLLAMA_ENDPOINT}/api/version" | jq -r '.version' 2>/dev/null || echo "unknown")
    log_info "Ollama API version: ${version}"

    return 0
}

main() {
    log_info "=== Instalador Ollama Nativo ==="
    log_info "Endpoint: ${OLLAMA_ENDPOINT}"
    log_info "Modelo: ${OLLAMA_MODEL} (base: ${OLLAMA_BASE_MODEL})"
    echo ""

    check_root
    install_ollama

    if verify_ollama_binary && enable_ollama_service && create_model && verify_model && verify_api; then
        log_info "✅ Ollama configurado correctamente"
        echo ""
        echo "Uso:"
        echo "  ollama run ${OLLAMA_MODEL}"
        echo "  curl ${OLLAMA_ENDPOINT}/api/generate -d '{\"model\":\"${OLLAMA_MODEL}\",\"prompt\":\"Hola\"}'"
        echo ""
        echo "Para Hermes/API: OLLAMA_ENDPOINT=${OLLAMA_ENDPOINT}"
    else
        log_error "❌ Error en configuración Ollama"
        exit 1
    fi
}

main "$@"