#!/usr/bin/env bash
# scripts/install/apache.sh
# Instala y configura Apache2 nativo (idempotente)
# Uso: ./scripts/install/apache.sh

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
APACHE_PORT="${APACHE_PORT:-8080}"
DOLIBARR_VHOST_NAME="${DOLIBARR_VHOST_NAME:-dolibarr.local}"

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

install_apache() {
    log_step "Instalando Apache2..."

    if dpkg -l | grep -q "^ii  apache2 "; then
        log_info "Apache2 ya instalado"
        return 0
    fi

    apt-get update -qq
    apt-get install -y -qq apache2 apache2-utils

    log_info "Apache2 instalado"
}

enable_modules() {
    log_step "Habilitando módulos Apache necesarios..."

    local modules=(
        "rewrite"
        "headers"
        "ssl"
        "proxy"
        "proxy_http"
        "proxy_fcgi"
        "setenvif"
        "mime"
        "dir"
        "alias"
        "expires"
        "deflate"
        "filter"
    )

    local to_enable=()
    for mod in "${modules[@]}"; do
        if ! apache2ctl -M 2>/dev/null | grep -q "${mod}_module"; then
            to_enable+=("$mod")
        fi
    done

    if [[ ${#to_enable[@]} -gt 0 ]]; then
        log_info "Habilitando: ${to_enable[*]}"
        for mod in "${to_enable[@]}"; do
            a2enmod "$mod" >/dev/null 2>&1 || log_warn "No se pudo habilitar $mod"
        done
    else
        log_info "Todos los módulos requeridos ya están habilitados"
    fi
}

configure_ports() {
    log_step "Configurando puertos Apache..."

    local ports_conf="/etc/apache2/ports.conf"
    [[ -f "${ports_conf}.orig" ]] || cp "$ports_conf" "${ports_conf}.orig"

    # Asegurar que escucha en puerto 80 y 8080
    if ! grep -q "Listen ${APACHE_PORT}" "$ports_conf"; then
        echo "Listen ${APACHE_PORT}" >> "$ports_conf"
        log_info "Puerto ${APACHE_PORT} añadido a ports.conf"
    fi

    # Verificar puerto 80
    if ! grep -q "Listen 80" "$ports_conf"; then
        sed -i '1iListen 80' "$ports_conf"
    fi
}

detect_apache_user() {
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
}

verify_apache() {
    log_step "Verificando Apache..."

    # Test config
    if apache2ctl configtest 2>&1 | grep -q "Syntax OK"; then
        log_info "Configuración Apache: Syntax OK"
    else
        log_error "Configuración Apache: ERROR DE SINTAXIS"
        apache2ctl configtest
        return 1
    fi

    # Verificar servicio
    if systemctl is-active --quiet apache2; then
        log_info "Servicio Apache2: ACTIVO"
    else
        log_warn "Servicio Apache2: INACTIVO (iniciando...)"
        systemctl start apache2
        sleep 2
    fi

    # Verificar puertos
    sleep 1
    if ss -tlnp | grep -q ":${APACHE_PORT} "; then
        log_info "Apache escuchando en puerto ${APACHE_PORT}"
    else
        log_warn "Apache NO escucha en puerto ${APACHE_PORT} (puede necesitar VirtualHost habilitado)"
    fi

    if ss -tlnp | grep -q ":80 "; then
        log_info "Apache escuchando en puerto 80"
    fi

    return 0
}

enable_service() {
    log_step "Habilitando servicio Apache2..."

    systemctl enable apache2 >/dev/null 2>&1

    if systemctl is-active --quiet apache2; then
        log_info "Servicio Apache2 ya activo"
    else
        systemctl start apache2
        log_info "Servicio Apache2 iniciado"
    fi
}

main() {
    log_info "=== Instalador Apache2 ==="
    log_info "Puerto Dolibarr: ${APACHE_PORT} | ServerName: ${DOLIBARR_VHOST_NAME}"
    echo ""

    check_root
    install_apache
    enable_modules
    configure_ports
    detect_apache_user
    enable_service

    if verify_apache; then
        log_info "✅ Apache2 configurado correctamente"
    else
        log_error "❌ Error en verificación Apache"
        exit 1
    fi
}

main "$@"