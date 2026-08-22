#!/usr/bin/env bash
# scripts/check.sh
# Verificación profunda del entorno Transvega
# Uso: ./scripts/check.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

if [[ -f "${PROJECT_ROOT}/.env" ]]; then
    set -a
    source "${PROJECT_ROOT}/.env"
    set +a
fi

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[OK]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[FAIL]${NC} $*"; }
log_step()  { echo -e "${BLUE}[CHECK]${NC} $*"; }

check_file() {
    local file="$1"
    local desc="$2"
    if [[ -f "$file" ]]; then
        log_info "$desc: $file"
        return 0
    else
        log_error "$desc: NO ENCONTRADO ($file)"
        return 1
    fi
}

check_dir() {
    local dir="$1"
    local desc="$2"
    if [[ -d "$dir" ]]; then
        log_info "$desc: $dir"
        return 0
    else
        log_error "$desc: NO ENCONTRADO ($dir)"
        return 1
    fi
}

check_command() {
    local cmd="$1"
    local desc="$2"
    if command -v "$cmd" >/dev/null 2>&1; then
        local version
        version=$($cmd --version 2>&1 | head -1)
        log_info "$desc: $version"
        return 0
    else
        log_error "$desc: NO INSTALADO ($cmd)"
        return 1
    fi
}

check_env_var() {
    local var="$1"
    local desc="$2"
    local required="${3:-true}"
    local value="${!var:-}"

    if [[ -n "$value" ]]; then
        # Ocultar valores sensibles
        if [[ "$var" == *"PASSWORD"* || "$var" == *"SECRET"* || "$var" == *"TOKEN"* || "$var" == *"KEY"* ]]; then
            log_info "$desc ($var): ***CONFIGURADO***"
        else
            log_info "$desc ($var): $value"
        fi
        return 0
    else
        if [[ "$required" == "true" ]]; then
            log_error "$desc ($var): VACÍO (REQUERIDO)"
            return 1
        else
            log_warn "$desc ($var): VACÍO (opcional)"
            return 0
        fi
    fi
}

check_systemd_service() {
    local service="$1"
    local desc="$2"
    if systemctl is-active --quiet "$service" 2>/dev/null; then
        log_info "$desc ($service): ACTIVO"
        return 0
    else
        log_error "$desc ($service): INACTIVO"
        return 1
    fi
}

check_http_endpoint() {
    local url="$1"
    local desc="$2"
    local expected="${3:-200}"
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$url" 2>/dev/null || echo "000")
    if [[ "$code" == "$expected" ]] || [[ "$expected" == "any" && "$code" =~ ^[23] ]]; then
        log_info "$desc: HTTP $code"
        return 0
    else
        log_error "$desc: HTTP $code (esperado $expected)"
        return 1
    fi
}

main() {
    echo ""
    echo "=========================================="
    echo "  TRANSVEGA - VERIFICACIÓN PROFUNDA"
    echo "=========================================="
    echo ""

    local total=0
    local passed=0

    # 1. Archivos y directorios críticos
    log_step "Archivos y directorios críticos"
    check_file "${PROJECT_ROOT}/.env" "Archivo .env" && ((passed++)) || true; ((total++))
    check_file "${PROJECT_ROOT}/.env.example" "Archivo .env.example" && ((passed++)) || true; ((total++))
    check_file "${PROJECT_ROOT}/Makefile" "Makefile" && ((passed++)) || true; ((total++))
    check_dir "${PROJECT_ROOT}/dolibarr-23.0.4" "Dolibarr source" && ((passed++)) || true; ((total++))
    check_file "${PROJECT_ROOT}/dolibarr-23.0.4/htdocs/index.php" "Dolibarr index.php" && ((passed++)) || true; ((total++))
    check_file "${PROJECT_ROOT}/dolibarr-23.0.4/htdocs/api/index.php" "Dolibarr API" && ((passed++)) || true; ((total++))
    check_dir "${PROJECT_ROOT}/services/integration-api" "Integration API" && ((passed++)) || true; ((total++))
    check_dir "${PROJECT_ROOT}/services/task-queue" "Task Queue" && ((passed++)) || true; ((total++))
    check_dir "${PROJECT_ROOT}/services/approval-service" "Approval Service" && ((passed++)) || true; ((total++))
    check_dir "${PROJECT_ROOT}/adapters/dolibarr" "Dolibarr Adapter" && ((passed++)) || true; ((total++))
    check_dir "${PROJECT_ROOT}/scripts" "Scripts" && ((passed++)) || true; ((total++))
    check_dir "${PROJECT_ROOT}/config" "Config templates" && ((passed++)) || true; ((total++))

    # 2. Variables de entorno
    echo ""
    log_step "Variables de entorno críticas"
    check_env_var "DOLIBARR_DB_PASSWORD" "Dolibarr DB Password" && ((passed++)) || true; ((total++))
    check_env_var "DOLIBARR_DB_ROOT_PASSWORD" "Dolibarr DB Root Password" && ((passed++)) || true; ((total++))
    check_env_var "AUDIT_DB_PASSWORD" "Audit DB Password" && ((passed++)) || true; ((total++))
    check_env_var "REDIS_PASSWORD" "Redis Password" && ((passed++)) || true; ((total++))
    check_env_var "JWT_SECRET_KEY" "JWT Secret Key" && ((passed++)) || true; ((total++))
    check_env_var "FERNET_KEY" "Fernet Key" && ((passed++)) || true; ((total++))
    check_env_var "DOLIBARR_API_KEY" "Dolibarr API Key" && ((passed++)) || true; ((total++))
    check_env_var "OLLAMA_ENDPOINT" "Ollama Endpoint" false && ((passed++)) || true; ((total++))
    check_env_var "CLOUDFLARE_TUNNEL_TOKEN" "Cloudflare Tunnel Token" false && ((passed++)) || true; ((total++))
    check_env_var "TELEGRAM_BOT_TOKEN" "Telegram Bot Token" false && ((passed++)) || true; ((total++))

    # 3. Comandos del sistema
    echo ""
    log_step "Comandos del sistema"
    check_command "apache2" "Apache2" && ((passed++)) || true; ((total++))
    check_command "mysql" "MariaDB Client" && ((passed++)) || true; ((total++))
    check_command "psql" "PostgreSQL Client" && ((passed++)) || true; ((total++))
    check_command "redis-cli" "Redis Client" && ((passed++)) || true; ((total++))
    check_command "ollama" "Ollama" && ((passed++)) || true; ((total++))
    check_command "cloudflared" "Cloudflared" && ((passed++)) || true; ((total++))
    check_command "python3" "Python3" && ((passed++)) || true; ((total++))
    check_command "curl" "cURL" && ((passed++)) || true; ((total++))
    check_command "jq" "jq" && ((passed++)) || true; ((total++))

    # 4. Servicios systemd
    echo ""
    log_step "Servicios systemd"
    check_systemd_service "mariadb" "MariaDB" && ((passed++)) || true; ((total++))
    check_systemd_service "postgresql" "PostgreSQL" && ((passed++)) || true; ((total++))
    check_systemd_service "redis-server" "Redis" && ((passed++)) || true; ((total++))
    check_systemd_service "apache2" "Apache2" && ((passed++)) || true; ((total++))
    check_systemd_service "ollama" "Ollama" && ((passed++)) || true; ((total++))
    check_systemd_service "cloudflared" "Cloudflare Tunnel" && ((passed++)) || true; ((total++))
    check_systemd_service "hermes" "Hermes API" && ((passed++)) || true; ((total++))
    check_systemd_service "hermes-worker" "Hermes Worker" && ((passed++)) || true; ((total++))
    check_systemd_service "approvals" "Approvals Service" && ((passed++)) || true; ((total++))

    # 5. Health checks HTTP (solo si servicios activos)
    echo ""
    log_step "Health checks HTTP"
    if systemctl is-active --quiet apache2 2>/dev/null; then
        check_http_endpoint "http://127.0.0.1:${APACHE_PORT:-8080}/" "Dolibarr HTTP" "200,301,302,401,403" && ((passed++)) || true; ((total++))
        check_http_endpoint "http://127.0.0.1:${APACHE_PORT:-8080}/api/index.php/thirdparties" "Dolibarr REST API" "401,200" && ((passed++)) || true; ((total++))
    else
        log_warn "Apache inactivo - saltando HTTP checks Dolibarr"
    fi

    if systemctl is-active --quiet hermes 2>/dev/null; then
        check_http_endpoint "http://127.0.0.1:${API_PORT:-8000}/health" "Hermes /health" "200" && ((passed++)) || true; ((total++))
        check_http_endpoint "http://127.0.0.1:${API_PORT:-8000}/health/ready" "Hermes /health/ready" "200" && ((passed++)) || true; ((total++))
    else
        log_warn "Hermes inactivo - saltando HTTP checks"
    fi

    if systemctl is-active --quiet approvals 2>/dev/null; then
        check_http_endpoint "http://127.0.0.1:${APPROVALS_PORT:-8002}/health/live" "Approvals /health/live" "200" && ((passed++)) || true; ((total++))
    else
        log_warn "Approvals inactivo - saltando HTTP checks"
    fi

    if systemctl is-active --quiet ollama 2>/dev/null; then
        check_http_endpoint "http://127.0.0.1:${OLLAMA_PORT:-11434}/api/tags" "Ollama /api/tags" "200" && ((passed++)) || true; ((total++))
    else
        log_warn "Ollama inactivo - saltando HTTP checks"
    fi

    # 6. Conexiones BD
    echo ""
    log_step "Conexiones base de datos"
    if command -v mysql >/dev/null 2>&1 && [[ -n "${DOLIBARR_DB_PASSWORD:-}" ]]; then
        if mysql -h"${DOLIBARR_DB_HOST:-127.0.0.1}" -P"${DOLIBARR_DB_PORT:-3306}" -u"${DOLIBARR_DB_USER:-dolibarr}" -p"${DOLIBARR_DB_PASSWORD}" -e "USE \`${DOLIBARR_DB_NAME:-dolibarr}\`; SELECT 1" >/dev/null 2>&1; then
            log_info "MariaDB (Dolibarr): CONEXIÓN OK" && ((passed++))
        else
            log_error "MariaDB (Dolibarr): CONEXIÓN FALLIDA"
        fi
        ((total++))
    fi

    if command -v psql >/dev/null 2>&1 && [[ -n "${AUDIT_DB_PASSWORD:-}" ]]; then
        if PGPASSWORD="${AUDIT_DB_PASSWORD}" psql -h"${AUDIT_DB_HOST:-127.0.0.1}" -p"${AUDIT_DB_PORT:-5432}" -U"${AUDIT_DB_USER:-audit}" -d"${AUDIT_DB_NAME:-audit}" -c "SELECT 1" >/dev/null 2>&1; then
            log_info "PostgreSQL (Auditoría): CONEXIÓN OK" && ((passed++))
        else
            log_error "PostgreSQL (Auditoría): CONEXIÓN FALLIDA"
        fi
        ((total++))
    fi

    if command -v redis-cli >/dev/null 2>&1 && [[ -n "${REDIS_PASSWORD:-}" ]]; then
        if redis-cli -h"${REDIS_HOST:-127.0.0.1}" -p"${REDIS_PORT:-6379}" -a"${REDIS_PASSWORD}" ping | grep -q "PONG"; then
            log_info "Redis: PONG" && ((passed++))
        else
            log_error "Redis: SIN RESPUESTA"
        fi
        ((total++))
    fi

    # 7. Python virtualenv
    echo ""
    log_step "Python Virtualenv"
    if [[ -f "${PROJECT_ROOT}/.venv/bin/python" ]]; then
        log_info "Virtualenv: EXISTE" && ((passed++))
        if "${PROJECT_ROOT}/.venv/bin/python" -c "import fastapi, uvicorn, pydantic, sqlalchemy, redis, celery" 2>/dev/null; then
            log_info "Dependencias Python: OK" && ((passed++))
        else
            log_error "Dependencias Python: FALTANTES"
        fi
        ((total++))
    else
        log_error "Virtualenv: NO ENCONTRADO"
        ((total++))
    fi

    # 8. Ollama modelo
    if systemctl is-active --quiet ollama 2>/dev/null; then
        log_step "Ollama Modelo"
        if curl -sf "http://127.0.0.1:${OLLAMA_PORT:-11434}/api/tags" | jq -r '.models[].name' | grep -q "^${OLLAMA_MODEL:-transvega-local}$"; then
            log_info "Modelo ${OLLAMA_MODEL:-transvega-local}: DISPONIBLE" && ((passed++))
        else
            log_error "Modelo ${OLLAMA_MODEL:-transvega-local}: NO ENCONTRADO"
        fi
        ((total++))
    fi

    # Resumen
    echo ""
    echo "=========================================="
    echo "RESUMEN: ${passed}/${total} checks OK"
    echo "=========================================="

    if [[ $passed -eq $total ]]; then
        log_info "✅ TODOS LOS CHECKS PASARON"
        exit 0
    else
        local failed=$((total - passed))
        log_error "❌ $failed CHECKS FALLARON"
        exit 1
    fi
}

main "$@"