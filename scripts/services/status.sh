#!/usr/bin/env bash
# scripts/services/status.sh
# Estado de todos los servicios Transvega con health checks reales
# Uso: ./scripts/services/status.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

if [[ -f "${PROJECT_ROOT}/.env" ]]; then
    set -a
    source "${PROJECT_ROOT}/.env"
    set +a
fi

# Configuración
APACHE_PORT="${APACHE_PORT:-8080}"
DOLIBARR_LOCAL_URL="http://127.0.0.1:${APACHE_PORT}"
HERMES_URL="http://127.0.0.1:${API_PORT:-8000}"
APPROVALS_URL="http://127.0.0.1:${APPROVALS_PORT:-8002}"
OLLAMA_URL="http://127.0.0.1:${OLLAMA_PORT:-11434}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[OK]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[FAIL]${NC} $*"; }
log_step()  { echo -e "${BLUE}[CHECK]${NC} $*"; }

check_systemd() {
    local service="$1"
    local name="$2"

    if systemctl is-active --quiet "$service"; then
        log_info "${name}: systemd ACTIVO"
        return 0
    else
        log_error "${name}: systemd INACTIVO"
        return 1
    fi
}

check_http() {
    local url="$1"
    local name="$2"
    local expected_codes="${3:-200,301,302,401,403}"

    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$url" 2>/dev/null || echo "000")

    IFS=',' read -ra codes <<< "$expected_codes"
    for c in "${codes[@]}"; do
        if [[ "$code" == "$c" ]]; then
            log_info "${name}: HTTP ${code}"
            return 0
        fi
    done

    log_error "${name}: HTTP ${code} (esperado ${expected_codes})"
    return 1
}

check_dolibarr() {
    log_step "Dolibarr..."

    local all_ok=1

    # Apache
    check_systemd "apache2" "Apache2" || all_ok=0

    # HTTP local
    check_http "$DOLIBARR_LOCAL_URL" "Dolibarr HTTP" || all_ok=0

    # API REST (sin auth - espera 401)
    check_http "${DOLIBARR_LOCAL_URL}/api/index.php/thirdparties" "Dolibarr REST API" "401,200" || all_ok=0

    # MariaDB
    check_systemd "mariadb" "MariaDB" || all_ok=0

    # Archivos críticos
    local htdocs="${PROJECT_ROOT}/dolibarr-23.0.4/htdocs"
    if [[ -f "${htdocs}/index.php" && -f "${htdocs}/api/index.php" ]]; then
        log_info "Dolibarr archivos: PRESENTES"
    else
        log_error "Dolibarr archivos: FALTANTES"
        all_ok=0
    fi

    return $all_ok
}

check_postgresql() {
    log_step "PostgreSQL (Auditoría)..."

    local all_ok=1

    check_systemd "postgresql" "PostgreSQL" || all_ok=0

    if PGPASSWORD="${AUDIT_DB_PASSWORD}" psql -h "${AUDIT_DB_HOST:-127.0.0.1}" -p "${AUDIT_DB_PORT:-5432}" -U "${AUDIT_DB_USER:-audit}" -d "${AUDIT_DB_NAME:-audit}" -c "SELECT 1" >/dev/null 2>&1; then
        log_info "PostgreSQL: CONEXIÓN OK"
    else
        log_error "PostgreSQL: CONEXIÓN FALLIDA"
        all_ok=0
    fi

    return $all_ok
}

check_redis() {
    log_step "Redis..."

    local all_ok=1

    check_systemd "redis-server" "Redis" || all_ok=0

    if redis-cli -h "${REDIS_HOST:-127.0.0.1}" -p "${REDIS_PORT:-6379}" -a "${REDIS_PASSWORD}" ping | grep -q "PONG"; then
        log_info "Redis: PONG"
    else
        log_error "Redis: SIN RESPUESTA"
        all_ok=0
    fi

    return $all_ok
}

check_hermes() {
    log_step "Hermes API..."

    local all_ok=1

    check_systemd "hermes" "Hermes API" || all_ok=0

    check_http "${HERMES_URL}/health" "Hermes /health" || all_ok=0

    check_http "${HERMES_URL}/health/ready" "Hermes /health/ready" || all_ok=0

    return $all_ok
}

check_worker() {
    log_step "Hermes Worker..."

    check_systemd "hermes-worker" "Hermes Worker"
}

check_approvals() {
    log_step "Approvals Service..."

    local all_ok=1

    check_systemd "approvals" "Approvals" || all_ok=0

    check_http "${APPROVALS_URL}/health/live" "Approvals /health/live" || all_ok=0

    return $all_ok
}

check_ollama() {
    log_step "Ollama..."

    local all_ok=1

    check_systemd "ollama" "Ollama" || all_ok=0

    if curl -sf "${OLLAMA_URL}/api/tags" >/dev/null 2>&1; then
        log_info "Ollama API: RESPONDE"
        local model
        model=$(curl -sf "${OLLAMA_URL}/api/tags" | jq -r '.models[].name' | grep "^${OLLAMA_MODEL:-transvega-local}$" || echo "")
        if [[ -n "$model" ]]; then
            log_info "Ollama modelo: ${OLLAMA_MODEL:-transvega-local} DISPONIBLE"
        else
            log_warn "Ollama modelo: ${OLLAMA_MODEL:-transvega-local} NO ENCONTRADO"
        fi
    else
        log_error "Ollama API: SIN RESPUESTA"
        all_ok=0
    fi

    return $all_ok
}

check_cloudflare() {
    log_step "Cloudflare Tunnel..."

    check_systemd "cloudflared" "Cloudflared"

    if [[ -n "${CLOUDFLARE_TUNNEL_TOKEN:-}" ]]; then
        log_info "Token Cloudflare: CONFIGURADO"
    else
        log_warn "Token Cloudflare: NO CONFIGURADO"
    fi
}

main() {
    echo ""
    echo "=========================================="
    echo "  TRANSVEGA ANIMAL - STATUS"
    echo "=========================================="
    echo "$(date)"
    echo ""

    local total=0
    local passed=0

    local checks=(
        "check_dolibarr:Dolibarr"
        "check_postgresql:PostgreSQL"
        "check_redis:Redis"
        "check_hermes:Hermes API"
        "check_worker:Hermes Worker"
        "check_approvals:Approvals"
        "check_ollama:Ollama"
        "check_cloudflare:Cloudflare"
    )

    for check in "${checks[@]}"; do
        local func="${check%%:*}"
        local name="${check#*:}"
        total=$((total + 1))
        echo -n "[$name] "
        if $func; then
            passed=$((passed + 1))
        fi
        echo ""
    done

    echo "=========================================="
    echo "RESUMEN: ${passed}/${total} servicios OK"
    echo "=========================================="

    if [[ $passed -eq $total ]]; then
        log_info "✅ TODOS LOS SERVICIOS OPERATIVOS"
        exit 0
    else
        log_error "❌ ALGUNOS SERVICIOS CON PROBLEMAS"
        exit 1
    fi
}

main "$@"