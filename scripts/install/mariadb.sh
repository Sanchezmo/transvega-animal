#!/usr/bin/env bash
# scripts/install/mariadb.sh
# Instala y configura MariaDB nativo para Dolibarr (idempotente)
# Uso: ./scripts/install/mariadb.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

# Cargar .env
if [[ -f "${PROJECT_ROOT}/.env" ]]; then
    set -a
    source "${PROJECT_ROOT}/.env"
    set +a
fi

# Configuración con defaults
DOLIBARR_DB_HOST="${DOLIBARR_DB_HOST:-127.0.0.1}"
DOLIBARR_DB_PORT="${DOLIBARR_DB_PORT:-3306}"
DOLIBARR_DB_NAME="${DOLIBARR_DB_NAME:-dolibarr}"
DOLIBARR_DB_USER="${DOLIBARR_DB_USER:-dolibarr}"
DOLIBARR_DB_PASSWORD="${DOLIBARR_DB_PASSWORD:-}"
DOLIBARR_DB_ROOT_PASSWORD="${DOLIBARR_DB_ROOT_PASSWORD:-}"

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

validate_env() {
    local missing=()
    [[ -z "$DOLIBARR_DB_PASSWORD" ]] && missing+=("DOLIBARR_DB_PASSWORD")
    [[ -z "$DOLIBARR_DB_ROOT_PASSWORD" ]] && missing+=("DOLIBARR_DB_ROOT_PASSWORD")

    if [[ ${#missing[@]} -gt 0 ]]; then
        log_error "Faltan variables requeridas en .env:"
        for var in "${missing[@]}"; do
            log_error "  - $var"
        done
        log_info "Generar con: openssl rand -base64 32"
        exit 1
    fi
}

install_mariadb() {
    log_step "Instalando MariaDB..."

    if dpkg -l | grep -q "^ii  mariadb-server "; then
        log_info "MariaDB ya instalado"
        return 0
    fi

    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq mariadb-server mariadb-client

    log_info "MariaDB instalado"
}

configure_mariadb() {
    log_step "Configurando MariaDB para Dolibarr..."

    # Configuración optimizada para Dolibarr
    cat > /etc/mysql/mariadb.conf.d/99-transvega.cnf <<EOF
# Configuración Transvega para Dolibarr 23.0.4
# Generado automáticamente por scripts/install/mariadb.sh

[mysqld]
# Conexiones
bind-address = 127.0.0.1
port = ${DOLIBARR_DB_PORT}
max_connections = 200
max_user_connections = 150

# Character set (requerido por Dolibarr)
character-set-server = utf8mb4
collation-server = utf8mb4_unicode_ci
init_connect = 'SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci'

# InnoDB (motor por defecto Dolibarr)
innodb_buffer_pool_size = 256M
innodb_log_file_size = 64M
innodb_flush_log_at_trx_commit = 2
innodb_flush_method = O_DIRECT
innodb_file_per_table = 1

# Query cache (desactivado en versiones modernas, usar query_cache_type=0)
query_cache_type = 0
query_cache_size = 0

# Temp tables
tmp_table_size = 64M
max_heap_table_size = 64M

# Logs
slow_query_log = 1
slow_query_log_file = /var/log/mysql/slow.log
long_query_time = 2
log_queries_not_using_indexes = 0

# Seguridad
local_infile = 0
skip_name_resolve = 1

# Dolibarr specific
sql_mode = "STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION"
EOF

    log_info "Configuración MariaDB creada en /etc/mysql/mariadb.conf.d/99-transvega.cnf"
}

secure_mariadb() {
    log_step "Asegurando instalación MariaDB..."

    # Verificar si root ya tiene password
    if mysql -u root -e "SELECT 1" >/dev/null 2>&1; then
        log_warn "Root sin password - configurando..."
        mysql -u root <<EOF
ALTER USER 'root'@'localhost' IDENTIFIED BY '${DOLIBARR_DB_ROOT_PASSWORD}';
DELETE FROM mysql.user WHERE User='';
DELETE FROM mysql.user WHERE User='root' AND Host NOT IN ('localhost', '127.0.0.1', '::1');
DROP DATABASE IF EXISTS test;
DELETE FROM mysql.db WHERE Db='test' OR Db='test\\_%';
FLUSH PRIVILEGES;
EOF
        log_info "Root password configurado"
    else
        # Verificar si el password actual coincide
        if mysql -u root -p"${DOLIBARR_DB_ROOT_PASSWORD}" -e "SELECT 1" >/dev/null 2>&1; then
            log_info "Root password ya configurado correctamente"
        else
            log_error "No se puede acceder a MariaDB root. Password incorrecto o ya cambiado."
            log_info "Intenta: mysql_secure_installation manualmente"
            exit 1
        fi
    fi
}

create_dolibarr_database() {
    log_step "Creando base de datos y usuario Dolibarr..."

    # Usar root con password
    mysql -u root -p"${DOLIBARR_DB_ROOT_PASSWORD}" <<EOF
-- Crear base de datos si no existe
CREATE DATABASE IF NOT EXISTS \`${DOLIBARR_DB_NAME}\`
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

-- Crear usuario si no existe
CREATE USER IF NOT EXISTS '${DOLIBARR_DB_USER}'@'%' IDENTIFIED BY '${DOLIBARR_DB_PASSWORD}';
CREATE USER IF NOT EXISTS '${DOLIBARR_DB_USER}'@'localhost' IDENTIFIED BY '${DOLIBARR_DB_PASSWORD}';
CREATE USER IF NOT EXISTS '${DOLIBARR_DB_USER}'@'127.0.0.1' IDENTIFIED BY '${DOLIBARR_DB_PASSWORD}';

-- Otorgar permisos
GRANT ALL PRIVILEGES ON \`${DOLIBARR_DB_NAME}\`.* TO '${DOLIBARR_DB_USER}'@'%';
GRANT ALL PRIVILEGES ON \`${DOLIBARR_DB_NAME}\`.* TO '${DOLIBARR_DB_USER}'@'localhost';
GRANT ALL PRIVILEGES ON \`${DOLIBARR_DB_NAME}\`.* TO '${DOLIBARR_DB_USER}'@'127.0.0.1';

FLUSH PRIVILEGES;
EOF

    log_info "Base de datos '${DOLIBARR_DB_NAME}' y usuario '${DOLIBARR_DB_USER}' creados/actualizados"
}

verify_mariadb() {
    log_step "Verificando MariaDB..."

    # Test conexión root
    if ! mysql -u root -p"${DOLIBARR_DB_ROOT_PASSWORD}" -e "SELECT VERSION()" >/dev/null 2>&1; then
        log_error "Conexión root fallida"
        return 1
    fi

    local version
    version=$(mysql -u root -p"${DOLIBARR_DB_ROOT_PASSWORD}" -sNe "SELECT VERSION()")
    log_info "MariaDB version: ${version}"

    # Verificar versión >= 10.6 (requerido Dolibarr 23)
    local major_minor
    major_minor=$(echo "$version" | cut -d. -f1,2)
    if (( $(echo "$major_minor < 10.6" | bc -l) )); then
        log_warn "MariaDB ${major_minor} < 10.6 - Dolibarr 23.0.4 requiere 10.6+"
    fi

    # Test conexión usuario dolibarr
    if mysql -u "${DOLIBARR_DB_USER}" -p"${DOLIBARR_DB_PASSWORD}" -h "${DOLIBARR_DB_HOST}" -P "${DOLIBARR_DB_PORT}" -e "USE \`${DOLIBARR_DB_NAME}\`; SELECT 1" >/dev/null 2>&1; then
        log_info "Usuario dolibarr: conexión OK"
    else
        log_error "Usuario dolibarr: conexión FALLIDA"
        return 1
    fi

    # Verificar charset
    local charset
    charset=$(mysql -u root -p"${DOLIBARR_DB_ROOT_PASSWORD}" -sNe "SHOW VARIABLES LIKE 'character_set_server'")
    log_info "Character set server: ${charset}"

    local collation
    collation=$(mysql -u root -p"${DOLIBARR_DB_ROOT_PASSWORD}" -sNe "SHOW VARIABLES LIKE 'collation_server'")
    log_info "Collation server: ${collation}"

    return 0
}

enable_service() {
    log_step "Habilitando servicio MariaDB..."

    systemctl enable mariadb >/dev/null 2>&1
    systemctl start mariadb

    if systemctl is-active --quiet mariadb; then
        log_info "Servicio MariaDB activo"
    else
        log_error "Servicio MariaDB no se inició"
        systemctl status mariadb --no-pager
        return 1
    fi
}

main() {
    log_info "=== Instalador MariaDB para Dolibarr ==="
    log_info "DB: ${DOLIBARR_DB_NAME} | User: ${DOLIBARR_DB_USER} | Host: ${DOLIBARR_DB_HOST}:${DOLIBARR_DB_PORT}"
    echo ""

    check_root
    validate_env
    install_mariadb
    configure_mariadb
    enable_service
    secure_mariadb
    create_dolibarr_database

    if verify_mariadb; then
        log_info "✅ MariaDB configurado correctamente para Dolibarr"
    else
        log_error "❌ Error en verificación MariaDB"
        exit 1
    fi
}

main "$@"