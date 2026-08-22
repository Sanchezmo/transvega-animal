#!/usr/bin/env bash
# scripts/install/dolibarr.sh
# Instala Dolibarr 23.0.4 desde repo versionado (idempotente)
# Uso: ./scripts/install/dolibarr.sh

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
DOLIBARR_VERSION="${DOLIBARR_VERSION:-23.0.4}"
DOLIBARR_ROOT="${DOLIBARR_ROOT:-${PROJECT_ROOT}/dolibarr-23.0.4}"
DOLIBARR_HTDOCS="${DOLIBARR_HTDOCS:-${DOLIBARR_ROOT}/htdocs}"
DOLIBARR_DOCUMENTS="${DOLIBARR_DOCUMENTS:-${DOLIBARR_ROOT}/documents}"
DOLIBARR_CONF_DIR="${DOLIBARR_CONF_DIR:-${DOLIBARR_ROOT}/conf}"
DOLIBARR_CUSTOM_DIR="${DOLIBARR_CUSTOM_DIR:-${DOLIBARR_ROOT}/custom}"

DOLIBARR_DB_HOST="${DOLIBARR_DB_HOST:-127.0.0.1}"
DOLIBARR_DB_PORT="${DOLIBARR_DB_PORT:-3306}"
DOLIBARR_DB_NAME="${DOLIBARR_DB_NAME:-dolibarr}"
DOLIBARR_DB_USER="${DOLIBARR_DB_USER:-dolibarr}"
DOLIBARR_DB_PASSWORD="${DOLIBARR_DB_PASSWORD:-}"
DOLIBARR_LOCAL_URL="${DOLIBARR_LOCAL_URL:-http://127.0.0.1:8080}"

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

validate_env() {
    local missing=()
    [[ -z "$DOLIBARR_DB_PASSWORD" ]] && missing+=("DOLIBARR_DB_PASSWORD")

    if [[ ${#missing[@]} -gt 0 ]]; then
        log_error "Faltan variables en .env:"
        for var in "${missing[@]}"; do
            log_error "  - $var"
        done
        exit 1
    fi
}

verify_source_exists() {
    log_step "Verificando código fuente Dolibarr en repo..."

    if [[ ! -d "$DOLIBARR_ROOT" ]]; then
        log_error "Directorio Dolibarr no encontrado: $DOLIBARR_ROOT"
        log_info "Debe existir dolibarr-23.0.4/htdocs/index.php en el repo"
        exit 1
    fi

    if [[ ! -f "${DOLIBARR_HTDOCS}/index.php" ]]; then
        log_error "Dolibarr source incompleto: falta ${DOLIBARR_HTDOCS}/index.php"
        exit 1
    fi

    log_info "Código fuente Dolibarr ${DOLIBARR_VERSION} encontrado en ${DOLIBARR_ROOT}"
}

create_directories() {
    log_step "Creando estructura de directorios..."

    mkdir -p "$DOLIBARR_HTDOCS" "$DOLIBARR_DOCUMENTS" "$DOLIBARR_CONF_DIR" "$DOLIBARR_CUSTOM_DIR"

    # Subdirectorios de documents que Dolibarr espera
    mkdir -p "$DOLIBARR_DOCUMENTS"/{api,doctemplates,facture,fournisseur,societe,users,commande,propal,livraison,reception,note,expense,contract,project,shipment,delivery}

    log_info "Directorios creados en $DOLIBARR_ROOT"
}

configure_conf_php() {
    log_step "Configurando conf.php..."

    local conf_file="${DOLIBARR_CONF_DIR}/conf.php"
    local template_file="${DOLIBARR_HTDOCS}/install/conf.php.template"

    if [[ -f "$conf_file" ]]; then
        log_info "conf.php ya existe, verificando configuración..."

        # Verificar que apunta a la BD correcta
        if grep -q "\$dolibarr_main_db_name.*=.*'${DOLIBARR_DB_NAME}'" "$conf_file" && \
           grep -q "\$dolibarr_main_db_user.*=.*'${DOLIBARR_DB_USER}'" "$conf_file"; then
            log_info "conf.php ya configurado correctamente"
            return 0
        else
            log_warn "conf.php existe pero con configuración diferente, regenerando..."
        fi
    fi

    # Usar template de Dolibarr si existe
    if [[ -f "$template_file" ]]; then
        cp "$template_file" "$conf_file"
    else
        cat > "$conf_file" <<'CONFEOF'
<?php
/**
 * Fichero de configuración Dolibarr
 * Generado automáticamente por scripts/install/dolibarr.sh
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
$dolibarr_main_document_root='/var/www/html';  // Se sobrescribe en runtime
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

    log_info "conf.php generado en $conf_file"
}

set_permissions() {
    log_step "Configurando permisos..."

    # Detectar usuario Apache
    local APACHE_USER APACHE_GROUP
    if id "www-data" >/dev/null 2>&1; then
        APACHE_USER="www-data"
        APACHE_GROUP="www-data"
    elif id "apache" >/dev/null 2>&1; then
        APACHE_USER="apache"
        APACHE_GROUP="apache"
    elif id "httpd" >/dev/null 2>&1; then
        APACHE_USER="httpd"
        APACHE_GROUP="httpd"
    else
        APACHE_USER="www-data"
        APACHE_GROUP="www-data"
    fi

    log_info "Usuario Apache: ${APACHE_USER}:${APACHE_GROUP}"

    # Propietario: root (código), Grupo: www-data
    chown -R root:"${APACHE_GROUP}" "$DOLIBARR_ROOT"

    # Permisos base: directorios 755, archivos 644
    find "$DOLIBARR_ROOT" -type d -exec chmod 755 {} \;
    find "$DOLIBARR_ROOT" -type f -exec chmod 644 {} \;

    # Documentos: escritura para Apache
    chown -R "${APACHE_USER}:${APACHE_GROUP}" "$DOLIBARR_DOCUMENTS"
    chmod -R 775 "$DOLIBARR_DOCUMENTS"

    # Logs: escritura para Apache
    local LOGS_DIR="${DOLIBARR_ROOT}/logs"
    mkdir -p "$LOGS_DIR"
    chown -R "${APACHE_USER}:${APACHE_GROUP}" "$LOGS_DIR"
    chmod -R 775 "$LOGS_DIR"

    # Conf: solo lectura para Apache (excepto conf.php que necesita escritura inicial)
    chown -R root:"${APACHE_GROUP}" "$DOLIBARR_CONF_DIR"
    chmod 755 "$DOLIBARR_CONF_DIR"
    chmod 644 "$DOLIBARR_CONF_DIR"/conf.php 2>/dev/null || true

    # Custom: nuestro código, versionado
    chown -R root:"${APACHE_GROUP}" "$DOLIBARR_CUSTOM_DIR"
    chmod -R 755 "$DOLIBARR_CUSTOM_DIR"

    # htdocs: PHP necesita ejecutar, pero no escribir
    chown -R root:"${APACHE_GROUP}" "$DOLIBARR_HTDOCS"
    find "$DOLIBARR_HTDOCS" -type d -exec chmod 755 {} \;
    find "$DOLIBARR_HTDOCS" -type f -exec chmod 644 {} \;

    # Directorios que Dolibarr necesita escribir en htdocs (cache, assets, theme)
    for dir in "$DOLIBARR_HTDOCS"/public/temp "$DOLIBARR_HTDOCS"/public/assets "$DOLIBARR_HTDOCS"/theme; do
        if [[ -d "$dir" ]]; then
            chown -R "${APACHE_USER}:${APACHE_GROUP}" "$dir"
            chmod -R 775 "$dir"
        fi
    done

    log_info "Permisos configurados"
}

create_install_lock() {
    local lock_file="${DOLIBARR_DOCUMENTS}/install.lock"
    if [[ ! -f "$lock_file" ]]; then
        touch "$lock_file"
        chown "${APACHE_USER}:${APACHE_GROUP}" "$lock_file"
        chmod 644 "$lock_file"
        log_info "install.lock creado"
    fi
}

create_dolibarr_symlink() {
    log_step "Creando symlink dolibarr/ -> dolibarr-23.0.4/ para compatibilidad..."

    local link_path="${PROJECT_ROOT}/dolibarr"
    if [[ -L "$link_path" ]]; then
        local target
        target=$(readlink "$link_path")
        if [[ "$target" == "dolibarr-23.0.4" ]]; then
            log_info "Symlink ya existe y apunta correctamente"
            return 0
        else
            log_warn "Symlink apunta a $target, actualizando..."
            rm "$link_path"
        fi
    elif [[ -d "$link_path" ]]; then
        log_warn "Existe directorio dolibarr/ (no symlink), renombrando a dolibarr.old..."
        mv "$link_path" "${link_path}.old.$(date +%s)"
    fi

    ln -s "dolibarr-23.0.4" "$link_path"
    log_info "Symlink creado: $link_path -> dolibarr-23.0.4"
}

verify_installation() {
    log_step "Verificando instalación Dolibarr..."

    local checks=(
        "HTDOCS index.php:test -f ${DOLIBARR_HTDOCS}/index.php"
        "HTDOCS main.inc.php:test -f ${DOLIBARR_HTDOCS}/main.inc.php"
        "HTDOCS api/index.php:test -f ${DOLIBARR_HTDOCS}/api/index.php"
        "Documents dir:test -d ${DOLIBARR_DOCUMENTS}"
        "Conf dir:test -d ${DOLIBARR_CONF_DIR}"
        "Conf file:test -f ${DOLIBARR_CONF_DIR}/conf.php"
        "Install lock:test -f ${DOLIBARR_DOCUMENTS}/install.lock"
        "Custom dir:test -d ${DOLIBARR_CUSTOM_DIR}"
        "Symlink:test -L ${PROJECT_ROOT}/dolibarr"
    )

    local all_ok=1
    for check in "${checks[@]}"; do
        local name="${check%%:*}"
        local cmd="${check#*:}"
        if eval "$cmd"; then
            log_info "  ✓ $name"
        else
            log_error "  ✗ $name"
            all_ok=0
        fi
    done

    # Verificar conf.php tiene BD configurada
    if [[ -f "${DOLIBARR_CONF_DIR}/conf.php" ]]; then
        if grep -q "\$dolibarr_main_db_name.*=.*'${DOLIBARR_DB_NAME}'" "${DOLIBARR_CONF_DIR}/conf.php"; then
            log_info "  ✓ conf.php: BD configurada"
        else
            log_warn "  ⚠ conf.php: BD no coincide con .env"
        fi
    fi

    if [[ $all_ok -eq 1 ]]; then
        log_info "Instalación Dolibarr verificada correctamente"
        return 0
    else
        log_error "Algunas verificaciones fallaron"
        return 1
    fi
}

test_database_connection() {
    log_step "Probando conexión a MariaDB..."

    if mysql -h"$DOLIBARR_DB_HOST" -P"$DOLIBARR_DB_PORT" -u"$DOLIBARR_DB_USER" -p"$DOLIBARR_DB_PASSWORD" -e "USE \`$DOLIBARR_DB_NAME\`; SELECT 1" >/dev/null 2>&1; then
        local tables
        tables=$(mysql -h"$DOLIBARR_DB_HOST" -P"$DOLIBARR_DB_PORT" -u"$DOLIBARR_DB_USER" -p"$DOLIBARR_DB_PASSWORD" -e "USE \`$DOLIBARR_DB_NAME\`; SHOW TABLES LIKE 'llx_%';" 2>/dev/null | tail -n +2 | wc -l)
        log_info "MariaDB: Conexión OK (${tables} tablas llx_*)"
        return 0
    else
        log_error "MariaDB: Conexión fallida"
        log_info "Verifica que MariaDB esté corriendo y credenciales en .env"
        return 1
    fi
}

print_summary() {
    echo ""
    echo "=========================================="
    echo "  DOLIBARR ${DOLIBARR_VERSION} INSTALADO"
    echo "=========================================="
    echo ""
    echo "Ubicación:     ${DOLIBARR_ROOT}"
    echo "Web root:      ${DOLIBARR_HTDOCS}"
    echo "Documents:     ${DOLIBARR_DOCUMENTS}"
    echo "Config:        ${DOLIBARR_CONF_DIR}/conf.php"
    echo "Custom:        ${DOLIBARR_CUSTOM_DIR}"
    echo "Symlink:       ${PROJECT_ROOT}/dolibarr -> dolibarr-23.0.4"
    echo ""
    echo "URL local:     ${DOLIBARR_LOCAL_URL}"
    echo "API REST:      ${DOLIBARR_LOCAL_URL}/api/index.php"
    echo ""
    echo "Próximos pasos:"
    echo "  1. Configurar Apache VirtualHost: ./scripts/configure/apache.sh"
    echo "  2. Validar:                       ./scripts/dolibarr-health.sh"
    echo ""
}

main() {
    log_info "=== Instalador Dolibarr ${DOLIBARR_VERSION} (desde repo) ==="
    log_info "Proyecto: ${PROJECT_ROOT}"
    log_info "Fuente:   ${DOLIBARR_ROOT}"
    echo ""

    check_root
    validate_env
    verify_source_exists
    create_directories
    configure_conf_php
    set_permissions
    create_install_lock
    create_dolibarr_symlink

    if verify_installation && test_database_connection; then
        print_summary
        log_info "✅ Dolibarr instalado correctamente"
    else
        log_error "❌ Instalación completada con advertencias"
        exit 1
    fi
}

main "$@"