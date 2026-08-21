#!/usr/bin/env bash
# scripts/configure-cloudflare-dolibarr.sh
# Configura Cloudflare Tunnel para Dolibarr
# Requiere .env.local con CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_ZONE_ID

set -euo pipefail

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

# Cargar variables de entorno
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ENV_FILE="${PROJECT_ROOT}/.env.local"

if [[ ! -f "$ENV_FILE" ]]; then
    log_error "No se encuentra .env.local en $PROJECT_ROOT"
    exit 1
fi

set -a
source "$ENV_FILE"
set +a

# Validar variables requeridas
required_vars=(
    "CLOUDFLARE_API_TOKEN"
    "CLOUDFLARE_ACCOUNT_ID"
    "CLOUDFLARE_ZONE_ID"
)

missing_vars=()
for var in "${required_vars[@]}"; do
    if [[ -z "${!var:-}" ]]; then
        missing_vars+=("$var")
    fi
done

if [[ ${#missing_vars[@]} -gt 0 ]]; then
    log_error "Faltan variables requeridas en .env.local:"
    for var in "${missing_vars[@]}"; do
        log_error "  - $var"
    done
    exit 1
fi

DOMAIN="${DOMAIN:-mascotalegal.es}"
DOLIBARR_HOSTNAME="dolibarr-staging.${DOMAIN}"
TUNNEL_NAME="transvega-dolibarr-staging"
LOCAL_URL="http://localhost:8080"

log_info "=== Configurando Cloudflare Tunnel para Dolibarr (Staging) ==="
log_info "Dominio: ${DOLIBARR_HOSTNAME}"
log_info "Destino local: ${LOCAL_URL}"
log_info "Ruta: / (acceso completo Dolibarr ERP)"

# 1. Listar tunnels existentes
log_info "Obteniendo tunnels existentes..."
tunnels_response=$(curl -s -X GET "https://api.cloudflare.com/client/v4/accounts/${CLOUDFLARE_ACCOUNT_ID}/cfd_tunnel" \
    -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
    -H "Content-Type: application/json")

if ! echo "$tunnels_response" | grep -q '"success":true'; then
    log_error "Error obteniendo tunnels: $tunnels_response"
    exit 1
fi

# Buscar tunnel existente
tunnel_id=$(echo "$tunnels_response" | jq -r ".result[] | select(.name == \"${TUNNEL_NAME}\") | .id" 2>/dev/null)

if [[ -n "$tunnel_id" && "$tunnel_id" != "null" ]]; then
    log_info "Tunnel '${TUNNEL_NAME}' encontrado (ID: ${tunnel_id})"
else
    # Crear nuevo tunnel
    log_info "Creando nuevo tunnel '${TUNNEL_NAME}'..."
    create_response=$(curl -s -X POST "https://api.cloudflare.com/client/v4/accounts/${CLOUDFLARE_ACCOUNT_ID}/cfd_tunnel" \
        -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
        -H "Content-Type: application/json" \
        -d "{\"name\": \"${TUNNEL_NAME}\", \"config_src\": \"cloudflare\"}")

    if ! echo "$create_response" | grep -q '"success":true'; then
        log_error "Error creando tunnel: $create_response"
        exit 1
    fi

    tunnel_id=$(echo "$create_response" | jq -r '.result.id')
    log_info "Tunnel creado con ID: ${tunnel_id}"
fi

# 2. Obtener configuración actual del tunnel
log_info "Obteniendo configuración actual del tunnel..."
config_response=$(curl -s -X GET "https://api.cloudflare.com/client/v4/accounts/${CLOUDFLARE_ACCOUNT_ID}/cfd_tunnel/${tunnel_id}/configurations" \
    -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
    -H "Content-Type: application/json")

if ! echo "$config_response" | grep -q '"success":true'; then
    log_error "Error obteniendo configuración: $config_response"
    exit 1
fi

current_config=$(echo "$config_response" | jq -r '.result.config // "{}"')
log_info "Configuración actual obtenida"

# 3. Actualizar configuración para incluir Dolibarr
# La configuración de ingress debe incluir el hostname de Dolibarr
log_info "Actualizando configuración para ${DOLIBARR_HOSTNAME}..."

# Crear nueva configuración con ingress para Dolibarr
# Ruta / para acceso completo (API + interfaz web Dolibarr ERP)
new_config=$(cat <<EOF
{
  "config": {
    "ingress": [
      {
        "hostname": "${DOLIBARR_HOSTNAME}",
        "service": "http://localhost:8080",
        "path": "/",
        "originRequest": {
          "noTLSVerify": true
        }
      },
      {
        "service": "http_status:404"
      }
    ]
  }
}
EOF
)

# Actualizar configuración del tunnel
update_response=$(curl -s -X PUT "https://api.cloudflare.com/client/v4/accounts/${CLOUDFLARE_ACCOUNT_ID}/cfd_tunnel/${tunnel_id}/configurations" \
    -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "$new_config")

if ! echo "$update_response" | grep -q '"success":true'; then
    log_error "Error actualizando configuración del tunnel: $update_response"
    exit 1
fi

log_info "✓ Configuración del tunnel actualizada"

# 3. Crear/actualizar registro DNS para Dolibarr
log_info "Configurando registro DNS para ${DOLIBARR_HOSTNAME}..."

# Verificar si ya existe el registro
# El nombre DNS debe ser "dolibarr-staging" para dolibarr-staging.mascotalegal.es
DNS_RECORD_NAME="dolibarr-staging"
dns_response=$(curl -s -X GET "https://api.cloudflare.com/client/v4/zones/${CLOUDFLARE_ZONE_ID}/dns_records?name=${DNS_RECORD_NAME}&type=CNAME" \
    -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
    -H "Content-Type: application/json")

if echo "$dns_response" | grep -q '"success":true'; then
    record_count=$(echo "$dns_response" | jq '.result | length')
    if [[ "$record_count" -gt 0 ]]; then
        record_id=$(echo "$dns_response" | jq -r '.result[0].id')
        log_info "Registro DNS CNAME ya existe (ID: ${record_id}), actualizando..."
        
        update_dns=$(curl -s -X PUT "https://api.cloudflare.com/client/v4/zones/${CLOUDFLARE_ZONE_ID}/dns_records/${record_id}" \
            -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
            -H "Content-Type: application/json" \
            -d "{
                \"type\": \"CNAME\",
                \"name\": \"${DNS_RECORD_NAME}\",
                \"content\": \"${tunnel_id}.cfargotunnel.com\",
                \"ttl\": 1,
                \"proxied\": true,
                \"comment\": \"Dolibarr Staging via Cloudflare Tunnel\"
            }")
        
        if echo "$update_dns" | grep -q '"success":true'; then
            log_info "✓ Registro DNS actualizado"
        else
            log_warn "No se pudo actualizar registro DNS: $update_dns"
        fi
    else
        # Crear nuevo registro
        create_dns=$(curl -s -X POST "https://api.cloudflare.com/client/v4/zones/${CLOUDFLARE_ZONE_ID}/dns_records" \
            -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
            -H "Content-Type: application/json" \
            -d "{
                \"type\": \"CNAME\",
                \"name\": \"${DNS_RECORD_NAME}\",
                \"content\": \"${tunnel_id}.cfargotunnel.com\",
                \"ttl\": 1,
                \"proxied\": true,
                \"comment\": \"Dolibarr Staging via Cloudflare Tunnel\"
            }")
        
        if echo "$create_dns" | grep -q '"success":true'; then
            log_info "✓ Registro DNS creado"
        else
            log_warn "No se pudo crear registro DNS: $create_dns"
        fi
    fi
fi

# 4. Verificar conectividad
log_info "Verificando conectividad..."
sleep 3

if curl -sf "https://${DOLIBARR_HOSTNAME}/" >/dev/null 2>&1; then
    log_info "✓ Dolibarr accesible via HTTPS: https://${DOLIBARR_HOSTNAME}/"
else
    log_warn "Dolibarr no accesible aún via HTTPS (puede tardar unos minutos en propagarse)"
fi

# Resumen
echo ""
echo "=========================================="
echo "  CLOUDFLARE TUNNEL DOLIBARR CONFIGURADO"
echo "=========================================="
echo ""
echo "Tunnel ID:     ${tunnel_id}"
echo "Hostname:      https://${DOLIBARR_HOSTNAME}"
echo "Destino local: ${LOCAL_URL}"
echo "DNS:           CNAME -> ${tunnel_id}.cfargotunnel.com (proxied)"
echo ""
echo "Para usar en Hermes/Docker:"
echo "  DOLIBARR_API_URL=https://${DOLIBARR_HOSTNAME}/api/index.php"
echo ""
echo "Nota: La propagación DNS puede tardar 1-5 minutos."
echo "      El tunnel debe estar corriendo (cloudflared)."