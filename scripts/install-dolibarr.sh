#!/usr/bin/env bash
# scripts/install-dolibarr.sh
# Instalador idempotente de Dolibarr 20.0.4 en <PROJECT_ROOT>/dolibarr
# Uso: ./scripts/install-dolibarr.sh

set -euo pipefail

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

# =============================================================================
# CONFIGURACIÓN
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Versión fijada de Dolibarr (compatible con datos actuales STAGING v20.0.4)
DOLIBARR_VERSION="20.0.4"
DOLIBARR_URL="https://sourceforge.net/projects/dolibarr/files/Dolibarr%20ERP-CRM/${DOLIBARR_VERSION}/dolibarr-${DOLIBARR_VERSION}.tgz/download"
# Checksum SHA256 verificado (SourceForge: dolibarr-20.0.4.tgz)
# MD5: 630fe0d332db6c71ee73e49d715f8959 (SourceForge RSS)
DOLIBARR_SHA256="8af1304c93d202fadf6ff4bc32b0346eb8f1eb358429bc4ab3ee4509ae9fe4cb"

# Rutas destino
DOLIBARR_ROOT="${PROJECT_ROOT}/dolibarr"
HTDOCS_DIR="${DOLIBARR_ROOT}/htdocs"
DOCUMENTS_DIR="${DOLIBARR_ROOT}/documents"
CONF_DIR="${DOLIBARR_ROOT}/conf"
LOGS_DIR="${DOLIBARR_ROOT}/logs"
CUSTOM_DIR="${DOLIBARR_ROOT}/custom"

# Usuario/grupo Apache (detectado dinámicamente)
APACHE_USER="${APACHE_USER:-www-data}"
APACHE_GROUP="${APACHE_GROUP:-www-data}"

# =============================================================================
# FUNCIONES AUXILIARES
# =============================================================================

check_command() {
    command -v "$1" >/dev/null 2>&1 || { log_error "Comando requerido no encontrado: $1"; exit 1; }
}

verify_checksum() {
    local file="$1"
    local expected="$2"
    local actual
    actual=$(sha256sum "$file" | cut -d' ' -f1)
    if [[ "$actual" != "$expected" ]]; then
        log_error "Checksum inválido para $file"
        log_error "  Esperado: $expected"
        log_error "  Actual:   $actual"
        return 1
    fi
    log_info "Checksum verificado: $file"
}

create_directories() {
    log_step "Creando estructura de directorios..."
    mkdir -p "$HTDOCS_DIR" "$DOCUMENTS_DIR" "$CONF_DIR" "$LOGS_DIR" "$CUSTOM_DIR"
    
    # Subdirectorios de documents que Dolibarr espera
    mkdir -p "$DOCUMENTS_DIR"/{api,doctemplates,facture,fournisseur,societe,users,commande,propal,livraison,reception,note,expense,contract,project,shipment,delivery}
    
    log_info "Directorios creados en $DOLIBARR_ROOT"
}

download_dolibarr() {
    local tarball="${DOLIBARR_ROOT}/dolibarr-${DOLIBARR_VERSION}.tar.gz"
    
    if [[ -f "$tarball" ]]; then
        log_info "Archivo ya descargado, verificando checksum..."
        if verify_checksum "$tarball" "$DOLIBARR_SHA256"; then
            return 0
        else
            log_warn "Checksum falló, re-descargando..."
            rm -f "$tarball"
        fi
    fi
    
    log_step "Descargando Dolibarr ${DOLIBARR_VERSION}..."
    if ! curl -fL --retry 3 --retry-delay 5 -o "$tarball" "$DOLIBARR_URL"; then
        log_error "Error descargando Dolibarr desde $DOLIBARR_URL"
        return 1
    fi
    
    verify_checksum "$tarball" "$DOLIBARR_SHA256"
}

extract_dolibarr() {
    log_step "Extrayendo Dolibarr..."
    
    local tarball="${DOLIBARR_ROOT}/dolibarr-${DOLIBARR_VERSION}.tar.gz"
    local temp_extract="${DOLIBARR_ROOT}/.extract_temp"
    
    # Limpiar extracción anterior si existe
    rm -rf "$temp_extract"
    mkdir -p "$temp_extract"
    
    # Extraer
    tar -xzf "$tarball" -C "$temp_extract" --strip-components=1
    
    # Si htdocs ya existe y tiene contenido, no sobrescribir (idempotente)
    if [[ -d "$HTDOCS_DIR" && -f "$HTDOCS_DIR/index.php" ]]; then
        log_warn "htdocs/ ya existe con instalación válida, omitiendo extracción"
        rm -rf "$temp_extract"
        return 0
    fi
    
    # Mover contenido a htdocs
    mv "$temp_extract"/* "$HTDOCS_DIR"/
    rm -rf "$temp_extract"
    
    log_info "Dolibarr extraído en $HTDOCS_DIR"
}

configure_conf_php() {
    log_step "Configurando conf.php..."
    
    local conf_file="${CONF_DIR}/conf.php"
    local template_file="${HTDOCS_DIR}/install/conf.php.template"
    
    if [[ -f "$conf_file" ]]; then
        log_info "conf.php ya existe, omitiendo generación"
        return 0
    fi
    
    # Usar template de Dolibarr si existe, sino crear uno
    if [[ -f "$template_file" ]]; then
        cp "$template_file" "$conf_file"
    else
        cat > "$conf_file" <<'CONFEOF'
<?php
/**
 * Fichero de configuración Dolibarr
 * Generado automáticamente por scripts/install-dolibarr.sh
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
    
    # Sustituir valores reales desde variables de entorno si están disponibles
    if [[ -n "${DOLIBARR_DB_PASSWORD:-}" ]]; then
        sed -i "s|\$dolibarr_main_db_pass='.*'|\$dolibarr_main_db_pass='${DOLIBARR_DB_PASSWORD}'|" "$conf_file"
    fi
    if [[ -n "${DOLIBARR_DB_USER:-}" ]]; then
        sed -i "s|\$dolibarr_main_db_user='.*'|\$dolibarr_main_db_user='${DOLIBARR_DB_USER}'|" "$conf_file"
    fi
    if [[ -n "${DOLIBARR_DB_NAME:-}" ]]; then
        sed -i "s|\$dolibarr_main_db_name='.*'|\$dolibarr_main_db_name='${DOLIBARR_DB_NAME}'|" "$conf_file"
    fi
    if [[ -n "${DOLIBARR_DB_HOST:-}" ]]; then
        sed -i "s|\$dolibarr_main_db_host='.*'|\$dolibarr_main_db_host='${DOLIBARR_DB_HOST}'|" "$conf_file"
    fi
    
    # Actualizar rutas dinámicas
    sed -i "s|/home/saulo/transvega-animal/dolibarr/documents|${DOCUMENTS_DIR}|g" "$conf_file"
    sed -i "s|http://localhost:8080|${DOLIBARR_URL_ROOT:-http://localhost:8080}|g" "$conf_file"
    
    log_info "conf.php generado en $conf_file"
}

set_permissions() {
    log_step "Configurando permisos..."
    
    # Detectar usuario Apache real
    if id "www-data" >/dev/null 2>&1; then
        APACHE_USER="www-data"
        APACHE_GROUP="www-data"
    elif id "apache" >/dev/null 2>&1; then
        APACHE_USER="apache"
        APACHE_GROUP="apache"
    elif id "httpd" >/dev/null 2>&1; then
        APACHE_USER="httpd"
        APACHE_GROUP="httpd"
    fi
    
    log_info "Usuario Apache detectado: ${APACHE_USER}:${APACHE_GROUP}"
    
    # Propietario: root (código), Grupo: www-data
    chown -R root:"${APACHE_GROUP}" "$DOLIBARR_ROOT"
    
    # Permisos base: directorios 755, archivos 644
    find "$DOLIBARR_ROOT" -type d -exec chmod 755 {} \;
    find "$DOLIBARR_ROOT" -type f -exec chmod 644 {} \;
    
    # Documentos: escritura para Apache
    chown -R "${APACHE_USER}:${APACHE_GROUP}" "$DOCUMENTS_DIR"
    chmod -R 775 "$DOCUMENTS_DIR"
    
    # Logs: escritura para Apache
    chown -R "${APACHE_USER}:${APACHE_GROUP}" "$LOGS_DIR"
    chmod -R 775 "$LOGS_DIR"
    
    # Conf: solo lectura para Apache (excepto conf.php que necesita escritura inicial)
    chown -R root:"${APACHE_GROUP}" "$CONF_DIR"
    chmod 755 "$CONF_DIR"
    chmod 644 "$CONF_DIR"/conf.php 2>/dev/null || true
    
    # Custom: nuestro código, versionado
    chown -R root:"${APACHE_GROUP}" "$CUSTOM_DIR"
    chmod -R 755 "$CUSTOM_DIR"
    
    # htdocs: PHP necesita ejecutar, pero no escribir
    chown -R root:"${APACHE_GROUP}" "$HTDOCS_DIR"
    find "$HTDOCS_DIR" -type d -exec chmod 755 {} \;
    find "$HTDOCS_DIR" -type f -exec chmod 644 {} \;
    
    # Directorios que Dolibarr necesita escribir en htdocs (cache, etc.)
    for dir in "$HTDOCS_DIR"/public/temp "$HTDOCS_DIR"/public/assets "$HTDOCS_DIR"/theme; do
        if [[ -d "$dir" ]]; then
            chown -R "${APACHE_USER}:${APACHE_GROUP}" "$dir"
            chmod -R 775 "$dir"
        fi
    done
    
    log_info "Permisos configurados"
}

create_install_lock() {
    local lock_file="${DOCUMENTS_DIR}/install.lock"
    if [[ ! -f "$lock_file" ]]; then
        touch "$lock_file"
        chown "${APACHE_USER}:${APACHE_GROUP}" "$lock_file"
        chmod 644 "$lock_file"
        log_info "install.lock creado"
    fi
}

verify_installation() {
    log_step "Verificando instalación..."
    
    local checks=(
        "HTDOCS index.php:test -f ${HTDOCS_DIR}/index.php"
        "HTDOCS main.inc.php:test -f ${HTDOCS_DIR}/main.inc.php"
        "HTDOCS api/index.php:test -f ${HTDOCS_DIR}/api/index.php"
        "Documents dir:test -d ${DOCUMENTS_DIR}"
        "Conf dir:test -d ${CONF_DIR}"
        "Conf file:test -f ${CONF_DIR}/conf.php"
        "Install lock:test -f ${DOCUMENTS_DIR}/install.lock"
        "Custom dir:test -d ${CUSTOM_DIR}"
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
    
    if [[ $all_ok -eq 1 ]]; then
        log_info "Instalación verificada correctamente"
        return 0
    else
        log_error "Algunas verificaciones fallaron"
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
    echo "Web root:      ${HTDOCS_DIR}"
    echo "Documents:     ${DOCUMENTS_DIR}"
    echo "Config:        ${CONF_DIR}/conf.php"
    echo "Logs:          ${LOGS_DIR}"
    echo "Custom:        ${CUSTOM_DIR}"
    echo ""
    echo "URL local:     http://localhost:8080"
    echo "URL Docker:    http://host.docker.internal:8080"
    echo "API REST:      http://host.docker.internal:8080/api/index.php"
    echo ""
    echo "Próximos pasos:"
    echo "  1. Configurar Apache: ./scripts/configure-apache-dolibarr.sh"
    echo "  2. Validar:           ./scripts/dolibarr-health.sh"
    echo "  3. Migrar BD:         ./scripts/restore-dolibarr.sh (desde backup Docker)"
    echo ""
}

# =============================================================================
# MAIN
# =============================================================================

main() {
    log_info "=== Instalador Dolibarr ${DOLIBARR_VERSION} ==="
    log_info "Proyecto: ${PROJECT_ROOT}"
    log_info "Destino:  ${DOLIBARR_ROOT}"
    echo ""
    
    # Verificaciones previas
    check_command "curl"
    check_command "tar"
    check_command "sha256sum"
    check_command "mysql"
    
    # Verificar si ya está instalado
    if [[ -f "${HTDOCS_DIR}/index.php" && -f "${CONF_DIR}/conf.php" ]]; then
        log_warn "Dolibarr ya parece instalado en ${HTDOCS_DIR}"
        read -p "¿Reinstalar/actualizar? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "Instalación cancelada por el usuario"
            verify_installation
            print_summary
            exit 0
        fi
    fi
    
    # Ejecutar pasos
    create_directories
    download_dolibarr
    extract_dolibarr
    configure_conf_php
    set_permissions
    create_install_lock
    
    if verify_installation; then
        print_summary
        log_info "✅ Instalación completada con éxito"
    else
        log_error "❌ Instalación completada con advertencias"
        exit 1
    fi
}

# Ejecutar
main "$@"