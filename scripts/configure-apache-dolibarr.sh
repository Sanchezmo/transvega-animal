#!/usr/bin/env bash
# scripts/configure-apache-dolibarr.sh
# Configura Apache VirtualHost para Dolibarr en puerto 8080
# Uso: ./scripts/configure-apache-dolibarr.sh

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

DOLIBARR_ROOT="${PROJECT_ROOT}/dolibarr"
HTDOCS_DIR="${DOLIBARR_ROOT}/htdocs"
DOCUMENTS_DIR="${DOLIBARR_ROOT}/documents"

# Puerto Apache para Dolibarr (local, Cloudflare termina SSL)
DOLIBARR_PORT="${DOLIBARR_PORT:-8080}"
SERVER_NAME="${DOLIBARR_SERVER_NAME:-dolibarr.local}"

# Rutas Apache
APACHE_SITES_AVAILABLE="/etc/apache2/sites-available"
APACHE_SITES_ENABLED="/etc/apache2/sites-enabled"
VHOST_FILE="${APACHE_SITES_AVAILABLE}/transvega-dolibarr.conf"
VHOST_ENABLED="${APACHE_SITES_ENABLED}/transvega-dolibarr.conf"

# Usuario Apache
APACHE_USER="${APACHE_USER:-www-data}"
APACHE_GROUP="${APACHE_GROUP:-www-data}"

# =============================================================================
# FUNCIONES
# =============================================================================

check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "Este script requiere privilegios de root (sudo)"
        log_info "Ejecuta: sudo $0"
        exit 1
    fi
}

check_apache() {
    if ! command -v apache2 >/dev/null 2>&1 && ! command -v httpd >/dev/null 2>&1; then
        log_error "Apache no está instalado"
        exit 1
    fi
    log_info "Apache detectado: $(apache2 -v 2>/dev/null | head -1 || httpd -v 2>/dev/null | head -1)"
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
        log_warn "No se detectó usuario Apache estándar, usando www-data"
    fi
    log_info "Usuario Apache: ${APACHE_USER}:${APACHE_GROUP}"
}

enable_modules() {
    log_step "Habilitando módulos Apache necesarios..."
    
    local modules=("rewrite" "headers" "ssl" "proxy" "proxy_http" "proxy_fcgi" "setenvif" "mime" "dir" "alias")
    local to_enable=()
    
    for mod in "${modules[@]}"; do
        if ! apache2ctl -M 2>/dev/null | grep -q "${mod}_module"; then
            to_enable+=("$mod")
        fi
    done
    
    if [[ ${#to_enable[@]} -gt 0 ]]; then log_info "Habilitando: ${to_enable[*]}"; fi
    for mod in "${to_enable[@]}"; do
        a2enmod "$mod" >/dev/null 2>&1 || log_warn "No se pudo habilitar $mod (puede ya estar habilitado)"
    done
    
    log_info "Módulos verificados"
}

create_vhost() {
    log_step "Creando VirtualHost en ${VHOST_FILE}..."
    
    cat > "$VHOST_FILE" <<VHOSTEOF
# VirtualHost para Dolibarr - Transvega Animal
# Generado automáticamente por scripts/configure-apache-dolibarr.sh
# NO EDITAR MANUALMENTE - regenerar con el script

<VirtualHost *:${DOLIBARR_PORT}>
    ServerName ${SERVER_NAME}
    ServerAlias localhost

    # DocumentRoot apunta directamente al código del proyecto
    DocumentRoot ${HTDOCS_DIR}

    # Configuración del directorio web
    <Directory ${HTDOCS_DIR}>
        Options FollowSymLinks
        AllowOverride All
        Require all granted
        
        # Seguridad: denegar acceso a archivos sensibles
        <FilesMatch "^\.">
            Require all denied
        </FilesMatch>
        
        <FilesMatch "(conf\.php|install\.lock|\.sql$|\.log$)">
            Require all denied
        </FilesMatch>
    </Directory>

    # Documentos: NO servir directamente por seguridad
    # Dolibarr los sirve a través de document.php con autenticación
    <Directory ${DOCUMENTS_DIR}>
        Require all denied
    </Directory>

    # Logs específicos
    ErrorLog \${APACHE_LOG_DIR}/transvega-dolibarr-error.log
    CustomLog \${APACHE_LOG_DIR}/transvega-dolibarr-access.log combined

    # Configuración PHP
    <IfModule mod_php.c>
        php_value upload_max_filesize 100M
        php_value post_max_size 100M
        php_value max_execution_time 300
        php_value max_input_time 300
        php_value memory_limit 256M
        php_value max_input_vars 5000
        # Seguridad
        php_flag expose_php Off
        # Session
        php_value session.gc_maxlifetime 7200
    </IfModule>

    # Headers de seguridad
    <IfModule mod_headers.c>
        Header always set X-Content-Type-Options "nosniff"
        Header always set X-Frame-Options "SAMEORIGIN"
        Header always set X-XSS-Protection "1; mode=block"
        Header always set Referrer-Policy "strict-origin-when-cross-origin"
        # CSP básica para Dolibarr
        Header always set Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:; connect-src 'self'; frame-ancestors 'self';"
    </IfModule>

    # Rewrite para API REST y URLs limpias
    <IfModule mod_rewrite.c>
        RewriteEngine On
        
        # API REST - pasar a index.php
        RewriteRule ^api/index\.php/(.*)$ /api/index.php [QSA,L]
        RewriteRule ^api/(.*)$ /api/index.php [QSA,L]
        
        # Dolibarr URLs limpias (opcional, requiere config Dolibarr)
        # RewriteCond %{REQUEST_FILENAME} !-f
        # RewriteCond %{REQUEST_FILENAME} !-d
        # RewriteRule ^(.*)$ /index.php [QSA,L]
    </IfModule>

    # Proxy para Cloudflare Tunnel (si se usa internamente)
    # ProxyPass / http://localhost:${DOLIBARR_PORT}/
    # ProxyPassReverse / http://localhost:${DOLIBARR_PORT}/
</VirtualHost>

# También escuchar en puerto 8080 si no está ya
# (Normalmente ports.conf ya tiene Listen 8080, pero por si acaso)
# Listen ${DOLIBARR_PORT}
VHOSTEOF

    log_info "VirtualHost creado: ${VHOST_FILE}"
}

enable_site() {
    log_step "Habilitando sitio..."
    
    if [[ -L "$VHOST_ENABLED" ]]; then
        log_info "Sitio ya habilitado"
    else
        a2ensite transvega-dolibarr >/dev/null
        log_info "Sitio habilitado: ${VHOST_ENABLED}"
    fi
}

disable_default_site() {
    log_step "Verificando sitio por defecto..."
    
    # NO deshabilitar 000-default.conf automáticamente (punto 9 del requerimiento)
    # Solo advertir si existe conflicto en el mismo puerto
    if [[ -L "/etc/apache2/sites-enabled/000-default.conf" ]]; then
        local default_port
        default_port=$(grep -h "Listen\|<VirtualHost" /etc/apache2/sites-enabled/000-default.conf 2>/dev/null | grep -oE '[0-9]+' | head -1 || echo "80")
        if [[ "$default_port" == "$DOLIBARR_PORT" ]]; then
            log_warn "000-default.conf usa puerto ${DOLIBARR_PORT} - posible conflicto"
            log_warn "Considera: sudo a2dissite 000-default.conf"
        fi
    fi
}

validate_config() {
    log_step "Validando configuración Apache..."
    
    if apache2ctl configtest; then
        log_info "✅ Sintaxis OK"
        return 0
    else
        log_error "❌ Error de sintaxis en configuración Apache"
        return 1
    fi
}

reload_apache() {
    log_step "Recargando Apache..."
    
    if systemctl reload apache2; then
        log_info "✅ Apache recargado"
    else
        log_error "❌ Error recargando Apache"
        return 1
    fi
}

verify_running() {
    log_step "Verificando Apache en puerto ${DOLIBARR_PORT}..."
    
    sleep 2
    
    if ss -tlnp | grep -q ":${DOLIBARR_PORT}"; then
        log_info "✅ Apache escuchando en puerto ${DOLIBARR_PORT}"
    else
        log_warn "⚠️ Apache no parece escuchar en puerto ${DOLIBARR_PORT}"
        log_info "Verifica: ss -tlnp | grep :${DOLIBARR_PORT}"
    fi
    
    # Test HTTP
    if curl -sf "http://localhost:${DOLIBARR_PORT}/" >/dev/null 2>&1; then
        log_info "✅ HTTP responde en localhost:${DOLIBARR_PORT}"
    else
        log_warn "⚠️ HTTP no responde (puede ser normal si Dolibarr no está instalado aún)"
    fi
}

print_summary() {
    echo ""
    echo "=========================================="
    echo "  APACHE CONFIGURADO PARA DOLIBARR"
    echo "=========================================="
    echo ""
    echo "VirtualHost:   ${VHOST_FILE}"
    echo "Puerto:        ${DOLIBARR_PORT}"
    echo "ServerName:    ${SERVER_NAME}"
    echo "DocumentRoot:  ${HTDOCS_DIR}"
    echo "Documents:     ${DOCUMENTS_DIR} (protegido)"
    echo ""
    echo "Logs:"
    echo "  Error:  /var/log/apache2/transvega-dolibarr-error.log"
    echo "  Access: /var/log/apache2/transvega-dolibarr-access.log"
    echo ""
    echo "Comandos útiles:"
    echo "  Ver config:     cat ${VHOST_FILE}"
    echo "  Test config:    sudo apache2ctl configtest"
    echo "  Recargar:       sudo systemctl reload apache2"
    echo "  Ver logs:       sudo tail -f /var/log/apache2/transvega-dolibarr-error.log"
    echo "  Deshabilitar:   sudo a2dissite transvega-dolibarr"
    echo ""
}

# =============================================================================
# MAIN
# =============================================================================

main() {
    log_info "=== Configurador Apache para Dolibarr ==="
    log_info "Proyecto: ${PROJECT_ROOT}"
    log_info "Puerto: ${DOLIBARR_PORT}"
    echo ""
    
    check_root
    check_apache
    detect_apache_user
    enable_modules
    create_vhost
    enable_site
    disable_default_site
    
    if validate_config; then
        reload_apache
        verify_running
        print_summary
        log_info "✅ Configuración Apache completada"
    else
        log_error "❌ Error en configuración, no se recargó Apache"
        exit 1
    fi
}

# Ejecutar
main "$@"