#!/usr/bin/env bash
# scripts/services/restart.sh
# Reinicia todos los servicios Transvega nativos
# Uso: sudo ./scripts/services/restart.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

# Ejecutar stop y start
bash "${SCRIPT_DIR}/stop.sh"
echo ""
bash "${SCRIPT_DIR}/start.sh"