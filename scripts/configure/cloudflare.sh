#!/usr/bin/env bash
# scripts/configure/cloudflare.sh
# Configura Cloudflare Tunnel ingress (adaptado de script existente)
# Uso: ./scripts/configure/cloudflare.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

if [[ -f "${PROJECT_ROOT}/.env" ]]; then
    set -a
    source "${PROJECT_ROOT}/.env"
    set +a
fi

DOMAIN="${DOMAIN:-mascotalegal.es}"
DOLIBARR_HOSTNAME="dolibarr-staging.${DOMAIN}"
HERMES_HOSTNAME="hermes.transvega-animal.es"
TELEGRAM_HOSTNAME="telegram.transvega-animal.es"
TUNNEL_NAME="transvega-staging"
LOCAL_DOLIBARR_URL="http://localhost:8080"
LOCAL_HERMES_URL="http://localhost:8000"
DNS_RECORD_DOLIBARR="dolibarr-staging"
DNS_RECORD_HERMES="hermes"
DNS_RECORD_TELEGRAM="telegram"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }
log_step()  { echo -e "${BLUE}[STEP]${NC} $*"; }

validate_env() {
    local required=("CLOUDFLARE_API_TOKEN" "CLOUDFLARE_ACCOUNT_ID" "CLOUDFLARE_ZONE_ID")
    local missing=()
    for var in "${required[@]}"; do
        if [[ -z "${!var:-}" ]]; then
            missing+=("$var")
        fi
    done

    if [[ ${#missing[@]} -gt 0 ]]; then
        log_warn "Variables Cloudflare faltantes en .env (configuración manual requerida):"
        for var in "${missing[@]}"; do
            log_warn "  - $var"
        done
        log_info "Ejecuta manualmente:"
        echo "  cloudflared tunnel login"
        echo "  cloudflared tunnel create ${TUNNEL_NAME}"
        echo "  cloudflared tunnel route dns ${TUNNEL_NAME} ${DOLIBARR_HOSTNAME}"
        echo "  cloudflared tunnel route dns ${TUNNEL_NAME} ${HERMES_HOSTNAME}"
        echo "  cloudflared tunnel route dns ${TUNNEL_NAME} ${TELEGRAM_HOSTNAME}"
        return 1
    fi
    return 0
}

get_tunnel_id() {
    local response
    response=$(curl -s -X GET "https://api.cloudflare.com/client/v4/accounts/${CLOUDFLARE_ACCOUNT_ID}/cfd_tunnel" \
        -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
        -H "Content-Type: application/json")

    if echo "$response" | grep -q '"success":true'; then
        echo "$response" | jq -r ".result[] | select(.name == \"${TUNNEL_NAME}\") | .id" 2>/dev/null
    fi
}

create_tunnel() {
    log_step "Creando tunnel ${TUNNEL_NAME}..."
    local response
    response=$(curl -s -X POST "https://api.cloudflare.com/client/v4/accounts/${CLOUDFLARE_ACCOUNT_ID}/cfd_tunnel" \
        -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
        -H "Content-Type: application/json" \
        -d "{\"name\": \"${TUNNEL_NAME}\", \"config_src\": \"cloudflare\"}")

    if echo "$response" | grep -q '"success":true'; then
        local tunnel_id
        tunnel_id=$(echo "$response" | jq -r '.result.id')
        log_info "Tunnel creado: ${tunnel_id}"
        echo "$tunnel_id"
    else
        log_error "Error creando tunnel: $response"
        return 1
    fi
}

update_ingress() {
    local tunnel_id="$1"
    log_step "Actualizando configuración ingress..."

    local current_config
    current_config=$(curl -s -X GET "https://api.cloudflare.com/client/v4/accounts/${CLOUDFLARE_ACCOUNT_ID}/cfd_tunnel/${tunnel_id}/configurations" \
        -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
        -H "Content-Type: application/json")

    local current_ingress
    current_ingress=$(echo "$current_config" | jq -c '.result.config.ingress // []')

    # Filtrar entradas existentes para nuestros hostnames
    local filtered_ingress
    filtered_ingress=$(echo "$current_ingress" | jq -c --arg h1 "${DOLIBARR_HOSTNAME}" --arg h2 "${HERMES_HOSTNAME}" --arg h3 "${TELEGRAM_HOSTNAME}" \
        'map(select(.hostname != $h1 and .hostname != $h2 and .hostname != $h3))')

    # Añadir nuestras entradas antes del catch-all
    local new_ingress
    new_ingress=$(echo "$filtered_ingress" | jq -c --arg h1 "${DOLIBARR_HOSTNAME}" --arg u1 "${LOCAL_DOLIBARR_URL}" \
        --arg h2 "${HERMES_HOSTNAME}" --arg u2 "${LOCAL_HERMES_URL}" \
        --arg h3 "${TELEGRAM_HOSTNAME}" --arg u3 "${LOCAL_HERMES_URL}" '
        if length > 0 and (.[length-1].hostname == null or .[length-1].service == "http_status:404") then
            .[:length-1] +
            [
                {"hostname": $h1, "service": $u1, "path": "/", "originRequest": {"noTLSVerify": true}},
                {"hostname": $h2, "service": $u2, "path": "/", "originRequest": {"noTLSVerify": true}},
                {"hostname": $h3, "service": $u3, "path": "/", "originRequest": {"noTLSVerify": true}}
            ] +
            .[length-1:]
        else
            . +
            [
                {"hostname": $h1, "service": $u1, "path": "/", "originRequest": {"noTLSVerify": true}},
                {"hostname": $h2, "service": $u2, "path": "/", "originRequest": {"noTLSVerify": true}},
                {"hostname": $h3, "service": $u3, "path": "/", "originRequest": {"noTLSVerify": true}}
            ]
        end
    ')

    local new_config
    new_config=$(cat <<EOF
{
  "config": {
    "ingress": ${new_ingress}
  }
}
EOF
)

    log_info "Nueva configuración ingress:"
    echo "$new_config" | jq -r '.config.ingress[]? | "  - hostname: \(.hostname // "catch-all"), service: \(.service), path: \(.path // "/")"'

    # Confirmar si interactivo
    if [[ -t 0 ]]; then
        read -p "¿Aplicar cambios en Cloudflare? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "Cancelado por usuario"
            return 0
        fi
    fi

    local update_response
    update_response=$(curl -s -X PUT "https://api.cloudflare.com/client/v4/accounts/${CLOUDFLARE_ACCOUNT_ID}/cfd_tunnel/${tunnel_id}/configurations" \
        -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
        -H "Content-Type: application/json" \
        -d "$new_config")

    if echo "$update_response" | grep -q '"success":true'; then
        log_info "✅ Ingress actualizado"
    else
        log_error "Error actualizando ingress: $update_response"
        return 1
    fi
}

update_dns() {
    local tunnel_id="$1"
    log_step "Actualizando registros DNS..."

    for record_name in "${DNS_RECORD_DOLIBARR}" "${DNS_RECORD_HERMES}" "${DNS_RECORD_TELEGRAM}"; do
        local dns_response
        dns_response=$(curl -s -X GET "https://api.cloudflare.com/client/v4/zones/${CLOUDFLARE_ZONE_ID}/dns_records?name=${record_name}&type=CNAME" \
            -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
            -H "Content-Type: application/json")

        if echo "$dns_response" | grep -q '"success":true'; then
            local count
            count=$(echo "$dns_response" | jq '.result | length')
            if [[ "$count" -gt 0 ]]; then
                local record_id
                record_id=$(echo "$dns_response" | jq -r '.result[0].id')
                log_info "Actualizando DNS ${record_name}..."
                curl -s -X PUT "https://api.cloudflare.com/client/v4/zones/${CLOUDFLARE_ZONE_ID}/dns_records/${record_id}" \
                    -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
                    -H "Content-Type: application/json" \
                    -d "{
                        \"type\": \"CNAME\",
                        \"name\": \"${record_name}\",
                        \"content\": \"${tunnel_id}.cfargotunnel.com\",
                        \"ttl\": 1,
                        \"proxied\": true,
                        \"comment\": \"Transvega via Cloudflare Tunnel\"
                    }" | grep -q '"success":true' && log_info "  ✓ ${record_name}" || log_warn "  ✗ ${record_name}"
            else
                log_info "Creando DNS ${record_name}..."
                curl -s -X POST "https://api.cloudflare.com/client/v4/zones/${CLOUDFLARE_ZONE_ID}/dns_records" \
                    -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
                    -H "Content-Type: application/json" \
                    -d "{
                        \"type\": \"CNAME\",
                        \"name\": \"${record_name}\",
                        \"content\": \"${tunnel_id}.cfargotunnel.com\",
                        \"ttl\": 1,
                        \"proxied\": true,
                        \"comment\": \"Transvega via Cloudflare Tunnel\"
                    }" | grep -q '"success":true' && log_info "  ✓ ${record_name}" || log_warn "  ✗ ${record_name}"
            fi
        fi
    done
}

main() {
    log_info "=== Configurador Cloudflare Tunnel ==="
    echo ""

    if ! validate_env; then
        log_warn "Saltando configuración automática - requiere variables en .env"
        return 0
    fi

    local tunnel_id
    tunnel_id=$(get_tunnel_id)

    if [[ -z "$tunnel_id" || "$tunnel_id" == "null" ]]; then
        tunnel_id=$(create_tunnel)
        [[ -n "$tunnel_id" ]] || exit 1
    else
        log_info "Tunnel existente: ${tunnel_id}"
    fi

    update_ingress "$tunnel_id"
    update_dns "$tunnel_id"

    log_info "✅ Cloudflare Tunnel configurado"
    echo ""
    echo "URLs públicas (tras propagación DNS 1-5 min):"
    echo "  Dolibarr: https://${DOLIBARR_HOSTNAME}"
    echo "  Hermes:   https://${HERMES_HOSTNAME}"
    echo "  Telegram: https://${TELEGRAM_HOSTNAME}"
    echo ""
    echo "Verificar tunnel: journalctl -u cloudflared -f"
}

main "$@"