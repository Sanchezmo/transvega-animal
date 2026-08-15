#!/usr/bin/env bash
# scripts/configure-telegram-webhook.sh
# Configura el webhook de Telegram para staging
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
    log_error "Copia .env.staging.example a .env.staging y rellena los valores reales"
    exit 1
fi

# Cargar variables de entorno
set -a
source "$ENV_FILE"
set +a

# Validar variables requeridas
required_vars=(
    "TELEGRAM_BOT_TOKEN"
    "TELEGRAM_WEBHOOK_SECRET"
    "TELEGRAM_WEBHOOK_PUBLIC_URL"
)

missing_vars=()
for var in "${required_vars[@]}"; do
    if [[ -z "${!var:-}" || "${!var}" == "CHANGE_ME" ]]; then
        missing_vars+=("$var")
    fi
done

if [[ ${#missing_vars[@]} -gt 0 ]]; then
    log_error "Faltan variables requeridas en .env.staging:"
    for var in "${missing_vars[@]}"; do
        log_error "  - $var"
    done
    exit 1
fi

# Validar formato de URL
if [[ ! "$TELEGRAM_WEBHOOK_PUBLIC_URL" =~ ^https://.+/api/v1/telegram/webhook$ ]]; then
    log_error "TELEGRAM_WEBHOOK_PUBLIC_URL debe terminar en /api/v1/telegram/webhook"
    log_error "Valor actual: $TELEGRAM_WEBHOOK_PUBLIC_URL"
    exit 1
fi

log_info "Configurando webhook de Telegram..."
log_info "URL pública: $TELEGRAM_WEBHOOK_PUBLIC_URL"

# Construir URL de la API de Telegram
TELEGRAM_API_URL="https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook"

# Realizar petición a la API de Telegram
log_info "Enviando petición a Telegram API..."

response=$(curl -s -X POST "$TELEGRAM_API_URL" \
    -H "Content-Type: application/json" \
    -d "{
        \"url\": \"${TELEGRAM_WEBHOOK_PUBLIC_URL}\",
        \"secret_token\": \"${TELEGRAM_WEBHOOK_SECRET}\",
        \"allowed_updates\": [\"message\", \"edited_message\", \"callback_query\"]
    }")

# Verificar respuesta
if echo "$response" | grep -q '"ok":true'; then
    log_info "✓ Webhook configurado correctamente"
    
    # Mostrar información del webhook configurado
    webhook_info=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo")
    echo "$webhook_info" | jq '.' 2>/dev/null || echo "$webhook_info"
else
    log_error "✗ Error configurando webhook"
    echo "$response" | jq '.' 2>/dev/null || echo "$response"
    exit 1
fi