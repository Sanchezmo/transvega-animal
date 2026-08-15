#!/usr/bin/env bash
# scripts/check-telegram-webhook.sh
# Comprueba el estado del webhook de Telegram configurado
# Requiere .env.staging con variables reales

set -euo pipefail

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Directorio base
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ENV_FILE="${PROJECT_ROOT}/.env.staging"

# Función para logging
log_info() { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

# Verificar que existe .env.staging
if [[ ! -f "$ENV_FILE" ]]; then
    log_error "No se encuentra .env.staging en $PROJECT_ROOT"
    exit 1
fi

# Cargar variables de entorno
set -a
source "$ENV_FILE"
set +a

# Validar variable requerida
if [[ -z "${TELEGRAM_BOT_TOKEN:-}" || "${TELEGRAM_BOT_TOKEN}" == "CHANGE_ME" ]]; then
    log_error "TELEGRAM_BOT_TOKEN no configurado en .env.staging"
    exit 1
fi

log_info "Consultando información del webhook de Telegram..."

# Consultar información del webhook
response=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo")

# Verificar respuesta
if echo "$response" | grep -q '"ok":false'; then
    log_error "Error consultando webhook"
    echo "$response" | jq '.' 2>/dev/null || echo "$response"
    exit 1
fi

# Extraer y mostrar información relevante
echo "$response" | jq -r '
    "URL configurada: \(.result.url // "ninguna")",
    "Actualizaciones pendientes: \(.result.pending_update_count // 0)",
    "Último error: \(.result.last_error_message // "ninguno")",
    "Fecha último error: \(if .result.last_error_date then (.result.last_error_date | todate) else "nunca" end)",
    "Máximo conexiones: \(.result.max_connections // "default")",
    "IP permitidas: \(.result.ip_address // "todas")"
' 2>/dev/null || {
    # Fallback si jq no está disponible
    echo "$response"
}

# Verificar si hay URL configurada
url=$(echo "$response" | jq -r '.result.url // ""' 2>/dev/null || echo "")
if [[ -z "$url" || "$url" == "null" || "$url" == "" ]]; then
    log_warn "No hay webhook configurado actualmente"
else
    log_info "Webhook activo en: $url"
fi

# Verificar si hay errores recientes
last_error=$(echo "$response" | jq -r '.result.last_error_message // ""' 2>/dev/null || echo "")
if [[ -n "$last_error" && "$last_error" != "null" && "$last_error" != "" ]]; then
    log_warn "Último error del webhook: $last_error"
    last_error_date=$(echo "$response" | jq -r '.result.last_error_date // 0' 2>/dev/null || echo "0")
    if [[ "$last_error_date" != "0" && "$last_error_date" != "null" ]]; then
        log_warn "Fecha: $(date -d @"$last_error_date" 2>/dev/null || date -r "$last_error_date" 2>/dev/null || echo "$last_error_date")"
    fi
fi

# Verificar actualizaciones pendientes
pending=$(echo "$response" | jq -r '.result.pending_update_count // 0' 2>/dev/null || echo "0")
if [[ "$pending" -gt 0 ]]; then
    log_info "Actualizaciones pendientes: $pending"
fi

log_info "Comprobación completada"