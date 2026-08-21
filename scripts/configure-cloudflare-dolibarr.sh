#!/usr/bin/env bash
# scripts/configure-cloudflare-dolibarr.sh
# Configura Cloudflare Tunnel para Dolibarr preservando ingress existentes
# Requiere .env.local con CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_ZONE_ID

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

# Cargar variables de entorno
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ENV_FILE="${PROJECT_ROOT}/.env.local"
BACKUP_DIR="${PROJECT_ROOT}/backups/cloudflare"

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
DNS_RECORD_NAME="dolibarr-staging"

# Función para backup de configuración
backup_config() {
    local tunnel_id=$1
    local config=$2
    mkdir -p "$BACKUP_DIR"
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_file="${BACKUP_DIR}/tunnel_${tunnel_id}_config_${timestamp}.json"
    echo "$config" | jq '.' > "$backup_file"
    log_info "Backup guardado en: $backup_file"
}

# Función para mostrar ingress actuales
show_current_ingress() {
    local config=$1
    echo "$config" | jq -r '.ingress[]? | "  - hostname: \(.hostname // "catch-all"), service: \(.service), path: \(.path // "/")"' 2>/dev/null || echo "  (no ingress rules found)"
}

log_info "=== Configurando Cloudflare Tunnel para Dolibarr (Staging) ==="
log_info "Dominio: ${DOLIBARR_HOSTNAME}"
log_info "Destino local: ${LOCAL_URL}"
log_info "Ruta: / (acceso completo Dolibarr ERP)"

# 1. Listar tunnels existentes
log_step "1/6: Obteniendo tunnels existentes..."
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
log_step "2/6: Obteniendo configuración actual del tunnel..."
config_response=$(curl -s -X GET "https://api.cloudflare.com/client/v4/accounts/${CLOUDFLARE_ACCOUNT_ID}/cfd_tunnel/${tunnel_id}/configurations" \
    -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
    -H "Content-Type: application/json")

if ! echo "$config_response" | grep -q '"success":true'; then
    log_error "Error obteniendo configuración: $config_response"
    exit 1
fi

current_config=$(echo "$config_response" | jq -r '.result.config // "{}"')
log_info "Configuración actual del tunnel:"
show_current_ingress "$current_config"

# 3. Backup de configuración actual
log_step "3/6: Guardando backup de configuración actual..."
backup_config "$tunnel_id" "$current_config"

# 4. Construir nueva configuración preservando ingress existentes
log_step "4/6: Construyendo nueva configuración (preservando ingress existentes)..."

# Extraer ingress actuales
current_ingress=$(echo "$current_config" | jq -c '.ingress // []')

# Verificar si ya existe ingress para Dolibarr
has_dolibarr=$(echo "$current_ingress" | jq -r --arg host "${DOLIBARR_HOSTNAME}" '.[] | select(.hostname == $host) | .hostname' | head -1)

# Filtrar ingress existentes para remover cualquier entrada previa de dolibarr-staging
filtered_ingress=$(echo "$current_ingress" | jq -c --arg host "${DOLIBARR_HOSTNAME}" 'map(select(.hostname != $host))')

# Añadir/modificar ingress para Dolibarr (al principio, antes del catch-all)
new_ingress=$(echo "$filtered_ingress" | jq -c --arg host "${DOLIBARR_HOSTNAME}" --arg url "${LOCAL_URL}" '
    # Insertar antes del último elemento si es catch-all, sino al final
    if length > 0 and (.[length-1].hostname == null or .[length-1].service == "http_status:404") then
        .[:length-1] + [{"hostname": $host, "service": $url, "path": "/", "originRequest": {"noTLSVerify": true}}] + .[length-1:]
    else
        . + [{"hostname": $host, "service": $url, "path": "/", "originRequest": {"noTLSVerify": true}}]
    end
')

new_config=$(cat <<EOF
{
  "config": {
    "ingress": ${new_ingress}
  }
}
EOF
)

log_info "Nueva configuración de ingress:"
echo "$new_config" | jq -r '.config.ingress[]? | "  - hostname: \(.hostname // "catch-all"), service: \(.service), path: \(.path // "/")"'

# Verificar que Telegram sigue presente
telegram_preserved=$(echo "$new_ingress" | jq -r '.[] | select(.hostname | test("telegram")) | .hostname' | head -1)
if [[ -n "$telegram_preserved" ]]; then
    log_info "✓ Telegram ingress preservado: $telegram_preserved"
else
    log_warn "⚠ No se detectó ingress de Telegram en la nueva configuración"
fi

# 5. Confirmar antes de aplicar
log_step "5/6: Confirmación requerida"
echo ""
echo "=== RESUMEN DE CAMBIOS ==="
echo "Tunnel: $TUNNEL_NAME ($tunnel_id)"
echo "Nuevo hostname: $DOLIBARR_HOSTNAME"
echo "Destino: $LOCAL_URL"
echo "Ingress existentes preservados: $(echo "$filtered_ingress" | jq 'length')"
echo "Telegram preservado: ${telegram_preserved:-NO}"
echo "Backup guardado en: $BACKUP_DIR"
echo ""
read -p "¿Aplicar estos cambios en Cloudflare? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    log_info "Operación cancelada por el usuario"
    exit 0
fi

# 6. Aplicar nueva configuración
log_step "6/6: Aplicando nueva configuración en Cloudflare..."
update_response=$(curl -s -X PUT "https://api.cloudflare.com/client/v4/accounts/${CLOUDFLARE_ACCOUNT_ID}/cfd_tunnel/${tunnel_id}/configurations" \
    -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "$new_config")

if ! echo "$update_response" | grep -q '"success":true'; then
    log_error "Error actualizando configuración del tunnel: $update_response"
    log_info "Para restaurar: usa el backup en $BACKUP_DIR"
    exit 1
fi

log_info "✓ Configuración del tunnel actualizada"

# 6b. Crear/actualizar registro DNS
log_step "6b/6: Configurando registro DNS..."
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

# 7. Verificar conectividad
log_step "7/7: Verificando conectividad..."
sleep 3

if curl -sf "https://${DOLIBARR_HOSTNAME}/" >/dev/null 2>&1; then
    log_info "✓ Dolibarr accesible via HTTPS: https://${DOLIBARR_HOSTNAME}/"
else
    log_warn "Dolibarr no accesible aún via HTTPS (puede tardar unos minutos en propagarse)"
fi

# Resumen final
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
echo "Backup de configuración anterior:"
echo "  ${BACKUP_DIR}/tunnel_${tunnel_id}_config_*.json"
echo ""
echo "Rollback manual:"
echo "  curl -X PUT \"https://api.cloudflare.com/client/v4/accounts/${CLOUDFLARE_ACCOUNT_ID}/cfd_tunnel/${tunnel_id}/configurations\" \\"
echo "    -H \"Authorization: Bearer \${CLOUDFLARE_API_TOKEN}\" \\"
echo "    -H \"Content-Type: application/json\" \\"
echo "    -d \"<backup_json>\""
echo ""
echo "Nota: La propagación DNS puede tardar 1-5 minutos."
echo "      El tunnel debe estar corriendo (cloudflared)."

# Funciones auxiliares al final
backup_config() {
    local tunnel_id=$1
    local config=$2
    mkdir -p "$BACKUP_DIR"
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_file="${BACKUP_DIR}/tunnel_${tunnel_id}_config_${timestamp}.json"
    echo "$config" | jq '.' > "$backup_file"
    log_info "Backup guardado en: $backup_file"
}

show_current_ingress() {
    local config=$1
    echo "$config" | jq -r '.ingress[]? | "  - hostname: \(.hostname // "catch-all"), service: \(.service), path: \(.path // "/")"' 2>/dev/null || echo "  (no ingress rules found)"
}