#!/usr/bin/env bash
# scripts/dolibarr-health.sh
# Healthcheck granular para Dolibarr nativo
# Distingue: Apache, Dolibarr, REST API, Autenticación

set -euo pipefail

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[OK]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[FAIL]${NC} $*"; }
log_step()  { echo -e "${BLUE}[CHECK]${NC} $*"; }

# =============================================================================
# CONFIGURACIÓN
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

DOLIBARR_ROOT="${PROJECT_ROOT}/dolibarr"
HTDOCS_DIR="${DOLIBARR_ROOT}/htdocs"
CONF_DIR="${DOLIBARR_ROOT}/conf"

DOLIBARR_PORT="${DOLIBARR_PORT:-8080}"
DOLIBARR_URL="http://localhost:${DOLIBARR_PORT}"
API_URL="${DOLIBARR_URL}/api/index.php"

# Credenciales (desde .env.local o variables)
DOLIBARR_API_KEY="${DOLIBARR_API_KEY:-}"

# Timeouts
HTTP_TIMEOUT=10
API_TIMEOUT=15

# =============================================================================
# CHECKS INDIVIDUALES
# =============================================================================

check_apache() {
    log_step "Verificando Apache..."
    
    # Proceso
    if ! systemctl is-active --quiet apache2; then
        log_error "Apache: servicio no activo"
        return 1
    fi
    
    # Puerto - verificar que algo escucha en el puerto (puede no mostrar proceso sin root)
    if ! ss -tln | grep -q ":${DOLIBARR_PORT} "; then
        log_error "Apache: no escucha en puerto ${DOLIBARR_PORT}"
        return 1
    fi
    
    # HTTP básico
    local http_code
    http_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time "$HTTP_TIMEOUT" "$DOLIBARR_URL" 2>/dev/null || echo "000")
    
    if [[ "$http_code" =~ ^(200|301|302|401|403)$ ]]; then
        log_info "Apache: UP (HTTP $http_code en puerto ${DOLIBARR_PORT})"
        return 0
    else
        log_error "Apache: HTTP $http_code (esperado 2xx/3xx/401/403)"
        return 1
    fi
}

check_dolibarr() {
    log_step "Verificando Dolibarr (instalación)..."
    
    # Archivos críticos
    local critical_files=(
        "${HTDOCS_DIR}/index.php"
        "${HTDOCS_DIR}/main.inc.php"
        "${HTDOCS_DIR}/api/index.php"
        "${CONF_DIR}/conf.php"
        "${DOLIBARR_ROOT}/documents/install.lock"
    )
    
    local all_ok=1
    for file in "${critical_files[@]}"; do
        if [[ -f "$file" ]]; then
            log_info "  Archivo: ${file##*/} ✓"
        else
            log_error "  Archivo: ${file##*/} NO ENCONTRADO ($file)"
            all_ok=0
        fi
    done
    
    # Verificar conf.php tiene BD configurada
    if [[ -f "${CONF_DIR}/conf.php" ]]; then
        if grep -q '\$dolibarr_main_db_name' "${CONF_DIR}/conf.php"; then
            log_info "  conf.php: configuración BD ✓"
        else
            log_warn "  conf.php: sin configuración BD completa"
        fi
    fi
    
    if [[ $all_ok -eq 1 ]]; then
        log_info "Dolibarr: instalación completa ✓"
        return 0
    else
        log_error "Dolibarr: instalación incompleta"
        return 1
    fi
}

check_database() {
    log_step "Verificando conexión MariaDB..."
    
    # Leer credenciales de conf.php
    local db_host db_name db_user db_pass
    if [[ -f "${CONF_DIR}/conf.php" ]]; then
        db_host=$(grep '\$dolibarr_main_db_host' "${CONF_DIR}/conf.php" | sed "s/.*= *'\([^']*\)'.*/\1/")
        db_name=$(grep '\$dolibarr_main_db_name' "${CONF_DIR}/conf.php" | sed "s/.*= *'\([^']*\)'.*/\1/")
        db_user=$(grep '\$dolibarr_main_db_user' "${CONF_DIR}/conf.php" | sed "s/.*= *'\([^']*\)'.*/\1/")
        db_pass=$(grep '\$dolibarr_main_db_pass' "${CONF_DIR}/conf.php" | sed "s/.*= *'\([^']*\)'.*/\1/")
    fi
    
    db_host="${db_host:-localhost}"
    db_name="${db_name:-dolibarr}"
    db_user="${db_user:-dolibarr}"
    db_pass="${db_pass:-dolibarr_password_segura_2026}"
    
    # Test conexión
    if mysql -h"$db_host" -u"$db_user" -p"$db_pass" -e "USE $db_name; SELECT 1" >/dev/null 2>&1; then
        # Verificar tablas principales
        local tables
        tables=$(mysql -h"$db_host" -u"$db_user" -p"$db_pass" -e "USE $db_name; SHOW TABLES LIKE 'llx_%';" 2>/dev/null | tail -n +2 | wc -l)
        log_info "MariaDB: UP (${tables} tablas llx_* en $db_name)"
        return 0
    else
        log_error "MariaDB: conexión fallida (host=$db_host, user=$db_user, db=$db_name)"
        return 1
    fi
}

check_rest_api() {
    log_step "Verificando REST API..."
    
    if [[ -z "$DOLIBARR_API_KEY" ]]; then
        log_warn "REST API: DOLIBARR_API_KEY no configurada (solo test sin auth)"
        # Test endpoint público
        local http_code
        http_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time "$API_TIMEOUT" "${API_URL}/thirdparties" 2>/dev/null || echo "000")
        if [[ "$http_code" == "401" ]]; then
            log_info "REST API: endpoint responde (401 Unauthorized - auth requerida)"
            return 0
        elif [[ "$http_code" == "200" ]]; then
            log_info "REST API: endpoint responde (200 OK - sin auth)"
            return 0
        else
            log_error "REST API: HTTP $http_code"
            return 1
        fi
    fi
    
    # Test con API key
    local response
    response=$(curl -s -w "\n%{http_code}" --max-time "$API_TIMEOUT" \
        -H "DOLAPIKEY: ${DOLIBARR_API_KEY}" \
        -H "Accept: application/json" \
        "${API_URL}/thirdparties?limit=1" 2>/dev/null || echo -e "\n000")
    
    local http_code
    http_code=$(echo "$response" | tail -1)
    local body
    body=$(echo "$response" | head -n -1)
    
    case "$http_code" in
        200)
            log_info "REST API: OK (autenticación válida, datos accesibles)"
            return 0
            ;;
        401)
            log_error "REST API: 401 Unauthorized (API key inválida)"
            return 1
            ;;
        403)
            log_error "REST API: 403 Forbidden (permisos insuficientes)"
            return 1
            ;;
        404)
            log_error "REST API: 404 Not Found (endpoint incorrecto)"
            return 1
            ;;
        500)
            log_error "REST API: 500 Internal Server Error"
            return 1
            ;;
        *)
            log_error "REST API: HTTP $http_code"
            return 1
            ;;
    esac
}

check_documents() {
    log_step "Verificando directorio documents..."
    
    local docs_dir="${DOLIBARR_ROOT}/documents"
    
    if [[ ! -d "$docs_dir" ]]; then
        log_error "Documents: directorio no existe ($docs_dir)"
        return 1
    fi
    
    # Permisos
    local perms
    perms=$(stat -c "%a" "$docs_dir" 2>/dev/null || echo "000")
    if [[ "$perms" =~ ^(775|777|755)$ ]]; then
        log_info "Documents: permisos $perms ✓"
    else
        log_warn "Documents: permisos $perms (recomendado 775)"
    fi
    
    # Propietario
    local owner
    owner=$(stat -c "%U:%G" "$docs_dir" 2>/dev/null || echo "unknown")
    if [[ "$owner" =~ (www-data|apache) ]]; then
        log_info "Documents: propietario $owner ✓"
    else
        log_warn "Documents: propietario $owner (recomendado www-data)"
    fi
    
    # Archivos
    local count
    count=$(find "$docs_dir" -type f 2>/dev/null | wc -l)
    log_info "Documents: $count archivos"
    
    return 0
}

check_cloudflare_tunnel() {
    log_step "Verificando Cloudflare Tunnel (Dolibarr)..."
    
    # Verificar si cloudflared está corriendo
    if docker ps --format "{{.Names}}" | grep -q "cloudflared"; then
        log_info "Cloudflare Tunnel: contenedor corriendo ✓"
        
        # Verificar túnel específico para Dolibarr (requiere API Cloudflare)
        log_warn "Cloudflare Tunnel: validación completa requiere API token"
        return 0
    else
        log_warn "Cloudflare Tunnel: no detectado en Docker"
        return 0  # No es crítico para healthcheck local
    fi
}

# =============================================================================
# MAIN
# =============================================================================

run_checks() {
    local checks=(
        "check_apache:Apache"
        "check_dolibarr:Dolibarr"
        "check_database:MariaDB"
        "check_rest_api:REST API"
        "check_documents:Documents"
        "check_cloudflare_tunnel:Cloudflare Tunnel"
    )
    
    local passed=0
    local failed=0
    local warnings=0
    
    echo ""
    echo "=========================================="
    echo "  DOLIBARR HEALTHCHECK"
    echo "=========================================="
    echo "URL Base:     ${DOLIBARR_URL}"
    echo "API:          ${API_URL}"
    echo "Timestamp:    $(date -Iseconds)"
    echo ""
    
    for check in "${checks[@]}"; do
        local func="${check%%:*}"
        local name="${check#*:}"
        
        echo -n "[$name] "
        if $func; then
            ((passed++))
        else
            # Verificar si fue warning o error real
            # Los checks que devuelven 0 siempre pasan
            ((failed++))
        fi
        echo ""
    done
    
    echo "=========================================="
    echo "RESUMEN: ${passed} OK, ${failed} FAIL"
    echo "=========================================="
    
    if [[ $failed -eq 0 ]]; then
        log_info "✅ TODOS LOS CHECKS PASARON"
        return 0
    else
        log_error "❌ ALGUNOS CHECKS FALLARON"
        return 1
    fi
}

# =============================================================================
# ENTRY POINT
# =============================================================================

case "${1:-all}" in
    all)
        run_checks
        ;;
    apache)
        check_apache
        ;;
    dolibarr)
        check_dolibarr
        ;;
    db|database)
        check_database
        ;;
    api|rest)
        check_rest_api
        ;;
    docs|documents)
        check_documents
        ;;
    cf|cloudflare)
        check_cloudflare_tunnel
        ;;
    *)
        echo "Uso: $0 [all|apache|dolibarr|db|api|docs|cf]"
        exit 1
        ;;
esac