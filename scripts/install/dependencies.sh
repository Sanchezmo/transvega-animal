#!/usr/bin/env bash
# scripts/install/dependencies.sh
# Instala dependencias base del sistema (idempotente)
# Uso: ./scripts/install/dependencies.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

# Cargar .env si existe
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

detect_os() {
    if [[ -f /etc/os-release ]]; then
        source /etc/os-release
        OS_ID="${ID}"
        OS_VERSION="${VERSION_ID}"
        log_info "OS detectado: ${PRETTY_NAME}"
    else
        log_error "No se pudo detectar el sistema operativo"
        exit 1
    fi
}

update_apt() {
    log_step "Actualizando cache de paquetes..."
    apt-get update -qq
}

install_base_packages() {
    log_step "Instalando paquetes base..."

    local packages=(
        # Herramientas esenciales
        curl wget gnupg2 ca-certificates lsb-release software-properties-common
        # Build tools
        build-essential pkg-config
        # Python
        python3 python3-venv python3-dev python3-pip
        # Base de datos
        postgresql-client postgresql-contrib
        # Redis cliente
        redis-tools
        # MariaDB cliente
        mariadb-client
        # Apache (se instala en script separado, pero cliente útil)
        apache2-utils
        # Utilidades
        jq sqlite3 unzip git htop tree
        # SSL/TLS
        openssl certbot
        # Procesamiento imágenes (Dolibarr/OCR)
        imagemagick ghostscript poppler-utils tesseract-ocr tesseract-ocr-spa
        # Monitoreo
        net-tools iproute2 ss
    )

    local to_install=()
    for pkg in "${packages[@]}"; do
        if ! dpkg -l | grep -q "^ii  ${pkg} "; then
            to_install+=("$pkg")
        fi
    done

    if [[ ${#to_install[@]} -gt 0 ]]; then
        log_info "Instalando: ${to_install[*]}"
        apt-get install -y -qq "${to_install[@]}"
    else
        log_info "Todos los paquetes base ya están instalados"
    fi
}

install_postgresql_repo() {
    log_step "Configurando repositorio PostgreSQL 16..."

    # Verificar si ya está configurado
    if [[ -f /etc/apt/sources.list.d/pgdg.list ]]; then
        log_info "Repositorio PostgreSQL ya configurado"
        return 0
    fi

    # Instalar clave y repo
    install -d /usr/share/postgresql-common/pgdg
    curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.gpg
    echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.gpg] https://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list
    apt-get update -qq
    log_info "Repositorio PostgreSQL 16 añadido"
}

install_mariadb_repo() {
    log_step "Configurando repositorio MariaDB..."

    # En Debian/Kali, MariaDB suele estar en repos oficiales
    # Verificar versión disponible
    local available_version
    available_version=$(apt-cache policy mariadb-server 2>/dev/null | grep Candidate | awk '{print $2}' | cut -d: -f2 | cut -d. -f1,2 || echo "unknown")
    log_info "MariaDB disponible en repos: ${available_version}"

    # Si es < 10.6, considerar repo oficial (Dolibarr 23.0.4 requiere 10.6+)
    # Por ahora confiar en repos de Debian 12/Kali (tienen 10.11+)
}

install_ollama_repo() {
    log_step "Ollama se instala via script oficial (no apt)"
}

install_cloudflared_repo() {
    log_step "Configurando repositorio cloudflared..."

    if [[ -f /etc/apt/sources.list.d/cloudflare-cloudflared.list ]]; then
        log_info "Repositorio cloudflared ya configurado"
        return 0
    fi

    # Descargar e instalar .deb oficial (más fiable que repo)
    local deb_url="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb"
    local deb_file="/tmp/cloudflared.deb"

    if ! dpkg -l | grep -q "^ii  cloudflared "; then
        log_info "Descargando cloudflared..."
        curl -fL -o "$deb_file" "$deb_url"
        dpkg -i "$deb_file" || apt-get install -f -y -qq
        rm -f "$deb_file"
        log_info "cloudflared instalado"
    else
        log_info "cloudflared ya instalado"
    fi
}

verify_installation() {
    log_step "Verificando instalación..."

    local checks=(
        "python3:python3 --version"
        "postgresql-client:psql --version"
        "redis-tools:redis-cli --version"
        "mariadb-client:mariadb --version"
        "jq:jq --version"
        "curl:curl --version"
        "git:git --version"
        "openssl:openssl version"
        "tesseract:tesseract --version"
    )

    local all_ok=1
    for check in "${checks[@]}"; do
        local name="${check%%:*}"
        local cmd="${check#*:}"
        if eval "$cmd" >/dev/null 2>&1; then
            log_info "  ✓ $name"
        else
            log_error "  ✗ $name"
            all_ok=0
        fi
    done

    if [[ $all_ok -eq 1 ]]; then
        log_info "✅ Todas las dependencias base verificadas"
        return 0
    else
        log_error "❌ Algunas dependencias faltan"
        return 1
    fi
}

main() {
    log_info "=== Instalador de Dependencias Base ==="
    log_info "Proyecto: ${PROJECT_ROOT}"
    echo ""

    check_root
    detect_os
    update_apt
    install_base_packages
    install_postgresql_repo
    install_mariadb_repo
    install_cloudflared_repo

    if verify_installation; then
        log_info "✅ Dependencias base instaladas correctamente"
    else
        log_error "❌ Error en instalación de dependencias"
        exit 1
    fi
}

main "$@"