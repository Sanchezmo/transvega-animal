#!/usr/bin/env bash
# scripts/install/cloudflare.sh
# Instala cloudflared nativo y configura systemd (idempotente)
# Uso: ./scripts/install/cloudflare.sh

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
CLOUDFLARE_TUNNEL_TOKEN="${CLOUDFLARE_TUNNEL_TOKEN:-}"
CLOUDFLARE_TUNNEL_TOKEN_PROD="${CLOUDFLARE_TUNNEL_TOKEN_PROD:-}"

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

install_cloudflared() {
    log_step "Instalando cloudflared..."

    if command -v cloudflared >/dev/null 2>&1; then
        local version
        version=$(cloudflared --version 2>/dev/null | head -1)
        log_info "cloudflared ya instalado: ${version}"
        return 0
    fi

    # Descargar .deb oficial (más fiable que repo apt)
    local deb_url="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb"
    local deb_file="/tmp/cloudflared.deb"

    log_info "Descargando cloudflared..."
    curl -fL -o "$deb_file" "$deb_url"
    dpkg -i "$deb_file" || apt-get install -f -y -qq
    rm -f "$deb_file"

    log_info "cloudflared instalado"
}

verify_cloudflared() {
    log_step "Verificando cloudflared..."

    if ! command -v cloudflared >/dev/null 2>&1; then
        log_error "cloudflared no encontrado"
        return 1
    fi

    local version
    version=$(cloudflared --version)
    log_info "cloudflared: ${version}"

    return 0
}

create_systemd_service() {
    log_step "Creando servicio systemd para cloudflared..."

    local service_file="/etc/systemd/system/cloudflared.service"
    local env_file="/etc/cloudflared/transvega.env"

    # Crear directorio config
    mkdir -p /etc/cloudflared

    # Crear archivo de entorno (solo root readable)
    cat > "$env_file" <<EOF
# Cloudflare Tunnel configuration for Transvega
# Generado automáticamente por scripts/install/cloudflare.sh

# Token para staging (desarrollo)
TUNNEL_TOKEN_STAGING=${CLOUDFLARE_TUNNEL_TOKEN}

# Token para producción (separado)
TUNNEL_TOKEN_PROD=${CLOUDFLARE_TUNNEL_TOKEN_PROD}

# Configuración común
TUNNEL_ORIGIN_CERT_PATH=/etc/cloudflared/cert.pem
EOF

    chmod 600 "$env_file"
    log_info "Archivo de entorno creado: ${env_file}"

    # Crear servicio systemd
    cat > "$service_file" <<'EOF'
[Unit]
Description=Cloudflare Tunnel for Transvega
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=root
EnvironmentFile=/etc/cloudflared/transvega.env
# Usar TUNNEL_TOKEN_STAGING por defecto, sobrescribir con TUNNEL_TOKEN_PROD en prod
ExecStart=/usr/bin/cloudflared tunnel --no-autoupdate run --token ${TUNNEL_TOKEN_STAGING}
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

# Seguridad
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/etc/cloudflared /var/log/cloudflared

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    log_info "Servicio systemd creado: ${service_file}"
}

create_config_template() {
    log_step "Creando template de configuración Cloudflare..."

    local template_dir="${PROJECT_ROOT}/config/cloudflare"
    mkdir -p "$template_dir"

    cat > "${template_dir}/config.yml.template" <<'EOF'
# Cloudflare Tunnel configuration template
# Generado desde config/cloudflare/config.yml.template
# Copiar a /etc/cloudflared/config.yml y ajustar

tunnel: TRANSVEGA_TUNNEL_ID
credentials-file: /etc/cloudflared/TRANSVEGA_TUNNEL_ID.json

ingress:
  # Dolibarr ERP
  - hostname: dolibarr-staging.{{DOMAIN}}
    service: http://localhost:8080
    originRequest:
      noTLSVerify: true

  # Hermes API
  - hostname: hermes.transvega-animal.es
    service: http://localhost:8000
    originRequest:
      noTLSVerify: true

  # Telegram webhook
  - hostname: telegram.transvega-animal.es
    service: http://localhost:8000
    originRequest:
      noTLSVerify: true

  # Catch-all (404)
  - service: http_status:404
EOF

    log_info "Template creado: ${template_dir}/config.yml.template"
}

verify_tunnel() {
    log_step "Verificando tunnel (requiere token configurado)..."

    if [[ -z "$CLOUDFLARE_TUNNEL_TOKEN" ]]; then
        log_warn "CLOUDFLARE_TUNNEL_TOKEN no configurado en .env"
        log_info "Para configurar:"
        echo "  1. cloudflared tunnel login  # Autenticar en Cloudflare (una vez)"
        echo "  2. cloudflared tunnel create transvega-staging"
        echo "  3. cloudflared tunnel route dns transvega-staging dolibarr-staging.mascotalegal.es"
        echo "  4. Copiar token a .env: CLOUDFLARE_TUNNEL_TOKEN=eyJhIjoi..."
        return 0
    fi

    # Test conectividad con token
    if timeout 10 cloudflared tunnel --token "$CLOUDFLARE_TUNNEL_TOKEN" run 2>&1 | head -5 | grep -q "Connection registered"; then
        log_info "Token válido - Tunnel conecta correctamente"
    else
        log_warn "No se pudo verificar token (puede necesitar DNS propagado)"
    fi

    return 0
}

enable_service() {
    log_step "Habilitando servicio cloudflared..."

    if [[ -n "$CLOUDFLARE_TUNNEL_TOKEN" ]]; then
        systemctl enable cloudflared >/dev/null 2>&1
        systemctl start cloudflared
        sleep 2

        if systemctl is-active --quiet cloudflared; then
            log_info "Servicio cloudflared activo"
        else
            log_warn "Servicio cloudflared no inició (verificar token y logs: journalctl -u cloudflared)"
        fi
    else
        log_info "Token no configurado - servicio creado pero no iniciado"
        log_info "Ejecutar después de configurar token: systemctl start cloudflared"
    fi
}

main() {
    log_info "=== Instalador Cloudflare Tunnel (cloudflared) ==="
    echo ""

    check_root
    install_cloudflared
    verify_cloudflared
    create_systemd_service
    create_config_template
    verify_tunnel
    enable_service

    log_info "✅ cloudflared instalado y servicio systemd creado"
    echo ""
    echo "Próximos pasos:"
    echo "  1. Configurar token en .env: CLOUDFLARE_TUNNEL_TOKEN=..."
    echo "  2. cloudflared tunnel login (si no hecho antes)"
    echo "  3. ./scripts/configure/cloudflare.sh (configurar ingress)"
    echo "  4. systemctl start cloudflared"
    echo ""
    echo "Logs: journalctl -u cloudflared -f"
}

main "$@"