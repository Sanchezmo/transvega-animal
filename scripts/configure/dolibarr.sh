#!/usr/bin/env bash
# scripts/configure/dolibarr.sh
# Verifica y regenera conf.php de Dolibarr si necesario (idempotente)
# Uso: sudo ./scripts/configure/dolibarr.sh

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
DOLIBARR_CONF_DIR="${DOLIBARR_CONF_DIR:-${PROJECT_ROOT}/dolibarr-23.0.4/conf}"
DOLIBARR_HTDOCS="${DOLIBARR_HTDOCS:-${PROJECT_ROOT}/dolibarr-23.0.4/htdocs}"
DOLIBARR_DOCUMENTS="${DOLIBARR_DOCUMENTS:-${PROJECT_ROOT}/dolibarr-23.0.4/documents}"
DOLIBARR_LOCAL_URL="${DOLIBARR_LOCAL_URL:-http://127.0.0.1:8080}"

DOLIBARR_DB_HOST="${DOLIBARR_DB_HOST:-127.0.0.1}"
DOLIBARR_DB_PORT="${DOLIBARR_DB_PORT:-3306}"
DOLIBARR_DB_NAME="${DOLIBARR_DB_NAME:-dolibarr}"
DOLIBARR_DB_USER="${DOLIBARR_DB_USER:-dolibarr}"
DOLIBARR_DB_PASSWORD="${DOLIBARR_DB_PASSWORD:-}"

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

verify_conf_php() {
    log_step "Verificando conf.php..."

    local conf_file="${DOLIBARR_CONF_DIR}/conf.php"

    if [[ ! -f "$conf_file" ]]; then
        log_warn "conf.php no existe - regenerando"
        return 1
    fi

    # Verificar valores clave
    local checks=(
        "\$dolibarr_main_db_host.*=.*'${DOLIBARR_DB_HOST}'"
        "\$dolibarr_main_db_port.*=.*'${DOLIBARR_DB_PORT}'"
        "\$dolibarr_main_db_name.*=.*'${DOLIBARR_DB_NAME}'"
        "\$dolibarr_main_db_user.*=.*'${DOLIBARR_DB_USER}'"
        "\$dolibarr_main_db_pass.*=.*'${DOLIBARR_DB_PASSWORD}'"
        "\$dolibarr_main_data_root.*=.*'${DOLIBARR_DOCUMENTS}'"
        "\$dolibarr_main_url_root.*=.*'${DOLIBARR_LOCAL_URL}'"
    )

    local all_ok=1
    for pattern in "${checks[@]}"; do
        if grep -q "$pattern" "$conf_file"; then
            log_info "  ✓ $(echo "$pattern" | cut -d. -f2 | cut -d= -f1)"
        else
            log_warn "  ✗ $(echo "$pattern" | cut -d. -f2 | cut -d= -f1) - no coincide"
            all_ok=0
        fi
    done

    return $all_ok
}

regenerate_conf_php() {
    log_step "Regenerando conf.php..."

    local conf_file="${DOLIBARR_CONF_DIR}/conf.php"
    local template_file="${DOLIBARR_HTDOCS}/install/conf.php.template"

    # Backup si existe
    if [[ -f "$conf_file" ]]; then
        cp "$conf_file" "${conf_file}.bak.$(date +%s)"
        log_info "Backup creado: ${conf_file}.bak.*"
    fi

    if [[ -f "$template_file" ]]; then
        cp "$template_file" "$conf_file"
    else
        cat > "$conf_file" <<'CONFEOF'
<?php
/**
 * Fichero de configuración Dolibarr
 * Generado automáticamente por scripts/configure/dolibarr.sh
 * NO EDITAR MANUALMENTE - usar variables de entorno
 */

// Base de datos
$dolibarr_main_db_host='localhost';
$dolibarr_main_db_port='3306';
$dolibarr_main_db_name='dolibarr';
$dolibarr_main_db_user='dolibarr';
$dolibarr_main_db_pass='dolibarr_password_segura_2026';
$dolibarr_main_db_type='mysqli';

// Rutas
$dolibarr_main_document_root='/var/www/html';
$dolibarr_main_data_root='/home/saulo/transvega-animal/dolibarr/documents';
$dolibarr_main_url_root='http://localhost:8080';
$dolibarr_main_url_root_alt='http://host.docker.internal:8080';

// Seguridad
$dolibarr_main_authentication='dolibarr';
$dolibarr_main_force_https='0';

// Configuración adicional
$dolibarr_main_prod='1';
$dolibarr_main_demo='0';
$dolibarr_main_optimize_smarty='1';
$dolibarr_main_db_character_set='utf8mb4';
$dolibarr_main_db_collation='utf8mb4_unicode_ci';

// Módulos personalizados
$dolibarr_main_modules_expense_report='1';
$dolibarr_main_modules_supplier_proposal='1';
CONFEOF
    fi

    # Sustituir valores reales
    sed -i "s|\$dolibarr_main_db_host='.*'|\$dolibarr_main_db_host='${DOLIBARR_DB_HOST}'|" "$conf_file"
    sed -i "s|\$dolibarr_main_db_port='.*'|\$dolibarr_main_db_port='${DOLIBARR_DB_PORT}'|" "$conf_file"
    sed -i "s|\$dolibarr_main_db_name='.*'|\$dolibarr_main_db_name='${DOLIBARR_DB_NAME}'|" "$conf_file"
    sed -i "s|\$dolibarr_main_db_user='.*'|\$dolibarr_main_db_user='${DOLIBARR_DB_USER}'|" "$conf_file"
    sed -i "s|\$dolibarr_main_db_pass='.*'|\$dolibarr_main_db_pass='${DOLIBARR_DB_PASSWORD}'|" "$conf_file"
    sed -i "s|/home/saulo/transvega-animal/dolibarr/documents|${DOLIBARR_DOCUMENTS}|g" "$conf_file"
    sed -i "s|http://localhost:8080|${DOLIBARR_LOCAL_URL}|g" "$conf_file"

    # Permisos
    local APACHE_USER APACHE_GROUP
    if id "www-data" >/dev/null 2>&1; then
        APACHE_USER="www-data"
        APACHE_GROUP="www-data"
    elif id "apache" >/dev/null 2>&1; then
        APACHE_USER="apache"
        APACHE_GROUP="apache"
    else
        APACHE_USER="www-data"
        APACHE_GROUP="www-data"
    fi

    chown root:"${APACHE_GROUP}" "$conf_file"
    chmod 644 "$conf_file"

    log_info "conf.php regenerado en $conf_file"
}

verify_install_lock() {
    log_step "Verificando install.lock..."

    local lock_file="${DOLIBARR_DOCUMENTS}/install.lock"
    if [[ ! -f "$lock_file" ]]; then
        touch "$lock_file"
        local APACHE_USER APACHE_GROUP
        if id "www-data" >/dev/null 2>&1; then
            APACHE_USER="www-data"
            APACHE_GROUP="www-data"
        elif id "apache" >/dev/null 2>&1; then
            APACHE_USER="apache"
            APACHE_GROUP="apache"
        else
            APACHE_USER="www-data"
            APACHE_GROUP="www-data"
        fi
        chown "${APACHE_USER}:${APACHE_GROUP}" "$lock_file"
        chmod 644 "$lock_file"
        log_info "install.lock creado"
    else
        log_info "install.lock existe"
    fi
}

verify_permissions() {
    log_step "Verificando permisos..."

    local APACHE_USER APACHE_GROUP
    if id "www-data" >/dev/null 2>&1; then
        APACHE_USER="www-data"
        APACHE_GROUP="www-data"
    elif id "apache" >/dev/null 2>&1; then
        APACHE_USER="apache"
        APACHE_GROUP="apache"
    else
        APACHE_USER="www-data"
        APACHE_GROUP="www-data"
    fi

    # Documents debe ser escribible por Apache
    if [[ -d "$DOLIBARR_DOCUMENTS" ]]; then
        local owner
        owner=$(stat -c "%U:%G" "$DOLIBARR_DOCUMENTS")
        if [[ "$owner" == "${APACHE_USER}:${APACHE_GROUP}" ]]; then
            log_info "Documents: propietario OK (${owner})"
        else
            log_warn "Documents: propietario ${owner} (esperado ${APACHE_USER}:${APACHE_GROUP})"
        fi
    fi
}

test_db_connection() {
    log_step "Probando conexión a MariaDB..."

    if mysql -h"$DOLIBARR_DB_HOST" -P"$DOLIBARR_DB_PORT" -u"$DOLIBARR_DB_USER" -p"$DOLIBARR_DB_PASSWORD" -e "USE \`$DOLIBARR_DB_NAME\`; SELECT 1" >/dev/null 2>&1; then
        local tables
        tables=$(mysql -h"$DOLIBARR_DB_HOST" -P"$DOLIBARR_DB_PORT" -u"$DOLIBARR_DB_USER" -p"$DOLIBARR_DB_PASSWORD" -e "USE \`$DOLIBARR_DB_NAME\`; SHOW TABLES LIKE 'llx_%';" 2>/dev/null | tail -n +2 | wc -l)
        log_info "MariaDB: Conexión OK (${tables} tablas llx_*)"
        return 0
    else
        log_error "MariaDB: Conexión fallida"
        return 1
    fi
}

main() {
    log_info "=== Configurador Dolibarr ==="
    echo ""

    check_root

    if ! verify_conf_php; then
        regenerate_conf_php
    else
        log_info "conf.php ya configurado correctamente"
    fi

    verify_install_lock
    verify_permissions

    if test_db_connection; then
        log_info "✅ Dolibarr configurado correctamente"
    else
        log_error "❌ Error en verificación de base de datos"
        exit 1
    fi
}

main "$@"