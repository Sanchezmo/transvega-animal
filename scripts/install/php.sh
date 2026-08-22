#!/usr/bin/env bash
# scripts/install/php.sh
# Instala PHP y extensiones requeridas por Dolibarr 23.0.4 (idempotente)
# Uso: ./scripts/install/php.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

# Cargar .env
if [[ -f "${PROJECT_ROOT}/.env" ]]; then
    set -a
    source "${PROJECT_ROOT}/.env"
    set +a
fi

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

detect_php_version() {
    # Dolibarr 23.0.4 requiere PHP 8.1+
    # Usar versión por defecto de Debian/Kali (probablemente 8.2 o 8.3)
    local default_version
    default_version=$(apt-cache policy php 2>/dev/null | grep Candidate | awk '{print $2}' | cut -d: -f2 | cut -d. -f1,2 || echo "8.2")
    PHP_VERSION="${default_version}"
    log_info "Versión PHP a instalar: ${PHP_VERSION}"
}

install_php() {
    log_step "Instalando PHP ${PHP_VERSION} y extensiones..."

    # Extensiones requeridas por Dolibarr 23.0.4
    # Fuente: https://wiki.dolibarr.org/index.php/Installation_prerequisites
    local php_packages=(
        "php${PHP_VERSION}"
        "php${PHP_VERSION}-cli"
        "php${PHP_VERSION}-fpm"
        "php${PHP_VERSION}-mysql"
        "php${PHP_VERSION}-pgsql"
        "php${PHP_VERSION}-gd"
        "php${PHP_VERSION}-curl"
        "php${PHP_VERSION}-mbstring"
        "php${PHP_VERSION}-xml"
        "php${PHP_VERSION}-zip"
        "php${PHP_VERSION}-intl"
        "php${PHP_VERSION}-bcmath"
        "php${PHP_VERSION}-soap"
        "php${PHP_VERSION}-ldap"
        "php${PHP_VERSION}-imap"
        "php${PHP_VERSION}-apcu"
        "php${PHP_VERSION}-opcache"
        "php${PHP_VERSION}-redis"
        "php${PHP_VERSION}-imagick"
        "libapache2-mod-php${PHP_VERSION}"
    )

    local to_install=()
    for pkg in "${php_packages[@]}"; do
        if ! dpkg -l | grep -q "^ii  ${pkg} "; then
            to_install+=("$pkg")
        fi
    done

    if [[ ${#to_install[@]} -gt 0 ]]; then
        apt-get update -qq
        apt-get install -y -qq "${to_install[@]}"
        log_info "PHP y extensiones instalados: ${to_install[*]}"
    else
        log_info "PHP y todas las extensiones requeridas ya están instaladas"
    fi
}

configure_php() {
    log_step "Configurando PHP para Dolibarr..."

    local php_ini="/etc/php/${PHP_VERSION}/apache2/php.ini"
    local php_cli_ini="/etc/php/${PHP_VERSION}/cli/php.ini"
    local php_fpm_ini="/etc/php/${PHP_VERSION}/fpm/php.ini"

    [[ -f "${php_ini}.orig" ]] || cp "$php_ini" "${php_ini}.orig"
    [[ -f "${php_cli_ini}.orig" ]] || cp "$php_cli_ini" "${php_cli_ini}.orig"

    # Configuración común para Apache y CLI
    for ini in "$php_ini" "$php_cli_ini"; do
        sed -i 's/^;*memory_limit = .*/memory_limit = 256M/' "$ini"
        sed -i 's/^;*max_execution_time = .*/max_execution_time = 300/' "$ini"
        sed -i 's/^;*max_input_time = .*/max_input_time = 300/' "$ini"
        sed -i 's/^;*post_max_size = .*/post_max_size = 100M/' "$ini"
        sed -i 's/^;*upload_max_filesize = .*/upload_max_filesize = 100M/' "$ini"
        sed -i 's/^;*max_input_vars = .*/max_input_vars = 5000/' "$ini"
        sed -i 's/^;*date.timezone = .*/date.timezone = Europe\/Madrid/' "$ini"
        sed -i 's/^;*expose_php = .*/expose_php = Off/' "$ini"
        sed -i 's/^;*session.gc_maxlifetime = .*/session.gc_maxlifetime = 7200/' "$ini"
        sed -i 's/^;*opcache.enable = .*/opcache.enable = 1/' "$ini"
        sed -i 's/^;*opcache.memory_consumption = .*/opcache.memory_consumption = 128/' "$ini"
        sed -i 's/^;*opcache.interned_strings_buffer = .*/opcache.interned_strings_buffer = 8/' "$ini"
        sed -i 's/^;*opcache.max_accelerated_files = .*/opcache.max_accelerated_files = 10000/' "$ini"
        sed -i 's/^;*opcache.revalidate_freq = .*/opcache.revalidate_freq = 2/' "$ini"
        sed -i 's/^;*opcache.fast_shutdown = .*/opcache.fast_shutdown = 1/' "$ini"
    done

    # Configuración FPM (si se usa)
    if [[ -f "$php_fpm_ini" ]]; then
        [[ -f "${php_fpm_ini}.orig" ]] || cp "$php_fpm_ini" "${php_fpm_ini}.orig"
        sed -i 's/^;*pm.max_children = .*/pm.max_children = 50/' "$php_fpm_ini"
        sed -i 's/^;*pm.start_servers = .*/pm.start_servers = 5/' "$php_fpm_ini"
        sed -i 's/^;*pm.min_spare_servers = .*/pm.min_spare_servers = 5/' "$php_fpm_ini"
        sed -i 's/^;*pm.max_spare_servers = .*/pm.max_spare_servers = 35/' "$php_fpm_ini"
    fi

    log_info "PHP configurado para Dolibarr"
}

enable_php_modules() {
    log_step "Verificando módulos PHP habilitados..."

    local required_modules=(
        "mysqli"
        "pdo_mysql"
        "gd"
        "curl"
        "mbstring"
        "xml"
        "zip"
        "intl"
        "bcmath"
        "soap"
        "ldap"
        "imap"
        "apcu"
        "opcache"
        "redis"
        "imagick"
    )

    local missing=()
    for mod in "${required_modules[@]}"; do
        if ! php -m | grep -q "^${mod}$"; then
            missing+=("$mod")
        fi
    done

    if [[ ${#missing[@]} -gt 0 ]]; then
        log_warn "Módulos PHP faltantes: ${missing[*]}"
        log_info "Intentando habilitar..."
        for mod in "${missing[@]}"; do
            phpenmod -v "${PHP_VERSION}" -s ALL "$mod" 2>/dev/null || true
        done
    else
        log_info "Todos los módulos PHP requeridos están habilitados"
    fi
}

verify_php() {
    log_step "Verificando PHP..."

    # Versión
    local version
    version=$(php -v | head -1)
    log_info "PHP: ${version}"

    # Módulos críticos
    local critical=("mysqli" "pdo_mysql" "gd" "curl" "mbstring" "xml" "zip" "intl" "bcmath")
    local all_ok=1
    for mod in "${critical[@]}"; do
        if php -m | grep -q "^${mod}$"; then
            log_info "  ✓ ${mod}"
        else
            log_error "  ✗ ${mod} (FALTA)"
            all_ok=0
        fi
    done

    # Configuración clave
    local memory_limit
    memory_limit=$(php -r "echo ini_get('memory_limit');")
    log_info "memory_limit: ${memory_limit}"

    local max_execution
    max_execution=$(php -r "echo ini_get('max_execution_time');")
    log_info "max_execution_time: ${max_execution}"

    local upload_max
    upload_max=$(php -r "echo ini_get('upload_max_filesize');")
    log_info "upload_max_filesize: ${upload_max}"

    if [[ $all_ok -eq 1 ]]; then
        return 0
    else
        return 1
    fi
}

restart_apache() {
    log_step "Recargando Apache para aplicar PHP..."

    if systemctl reload apache2; then
        log_info "Apache recargado"
    else
        log_warn "Error recargando Apache (puede no estar corriendo aún)"
    fi
}

main() {
    log_info "=== Instalador PHP para Dolibarr 23.0.4 ==="
    echo ""

    check_root
    detect_php_version
    install_php
    configure_php
    enable_php_modules
    restart_apache

    if verify_php; then
        log_info "✅ PHP configurado correctamente para Dolibarr"
    else
        log_error "❌ Faltan módulos PHP críticos"
        exit 1
    fi
}

main "$@"