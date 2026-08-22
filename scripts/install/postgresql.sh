#!/usr/bin/env bash
# scripts/install/postgresql.sh
# Instala y configura PostgreSQL 16 nativo para auditoría (idempotente)
# Uso: ./scripts/install/postgresql.sh

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
AUDIT_DB_HOST="${AUDIT_DB_HOST:-127.0.0.1}"
AUDIT_DB_PORT="${AUDIT_DB_PORT:-5432}"
AUDIT_DB_NAME="${AUDIT_DB_NAME:-audit}"
AUDIT_DB_USER="${AUDIT_DB_USER:-audit}"
AUDIT_DB_PASSWORD="${AUDIT_DB_PASSWORD:-}"

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
    if [[ -z "$AUDIT_DB_PASSWORD" ]]; then
        log_error "Falta AUDIT_DB_PASSWORD en .env"
        log_info "Generar con: openssl rand -base64 32"
        exit 1
    fi
}

install_postgresql() {
    log_step "Instalando PostgreSQL 16..."

    if dpkg -l | grep -q "^ii  postgresql-16 "; then
        log_info "PostgreSQL 16 ya instalado"
        return 0
    fi

    # Verificar si repo pgdg está configurado
    if [[ ! -f /etc/apt/sources.list.d/pgdg.list ]]; then
        log_warn "Repositorio PostgreSQL no configurado. Ejecuta primero: ./scripts/install/dependencies.sh"
        # Intentar instalar de repos oficiales (puede ser versión antigua)
        apt-get update -qq
        apt-get install -y -qq postgresql postgresql-contrib
    else
        apt-get update -qq
        apt-get install -y -qq postgresql-16 postgresql-client-16 postgresql-contrib-16
    fi

    log_info "PostgreSQL instalado"
}

configure_postgresql() {
    log_step "Configurando PostgreSQL..."

    # Detectar versión instalada
    local pg_version
    pg_version=$(ls /etc/postgresql/ 2>/dev/null | head -1)
    if [[ -z "$pg_version" ]]; then
        pg_version="16"
    fi

    local pg_conf="/etc/postgresql/${pg_version}/main/postgresql.conf"
    local pg_hba="/etc/postgresql/${pg_version}/main/pg_hba.conf"

    # Backup configs originales
    [[ -f "${pg_conf}.orig" ]] || cp "$pg_conf" "${pg_conf}.orig"
    [[ -f "${pg_hba}.orig" ]] || cp "$pg_hba" "${pg_hba}.orig"

    # Configuración postgresql.conf optimizada para auditoría
    cat > "$pg_conf" <<EOF
# PostgreSQL configuración Transvega - Auditoría
# Generado automáticamente por scripts/install/postgresql.sh

# Conexiones
listen_addresses = '127.0.0.1'
port = ${AUDIT_DB_PORT}
max_connections = 100

# Memoria
shared_buffers = 256MB
effective_cache_size = 1GB
maintenance_work_mem = 64MB
work_mem = 4MB

# WAL
wal_level = replica
max_wal_senders = 3
wal_keep_size = 128MB

# Checkpoints
checkpoint_timeout = 15min
max_wal_size = 1GB
min_wal_size = 80MB

# Query planner
random_page_cost = 1.1
effective_io_concurrency = 200

# Logging
log_destination = 'stderr'
logging_collector = on
log_directory = 'log'
log_filename = 'postgresql-%Y-%m-%d_%H%M%S.log'
log_rotation_age = 1d
log_rotation_size = 100MB
log_min_duration_statement = 1000
log_line_prefix = '%m [%p] %q%u@%d '
log_checkpoints = on
log_connections = on
log_disconnections = on
log_lock_waits = on
log_temp_files = 0
log_autovacuum_min_duration = 0

# Autovacuum
autovacuum = on
autovacuum_max_workers = 3
autovacuum_naptime = 1min
autovacuum_vacuum_threshold = 50
autovacuum_analyze_threshold = 50

# Cliente
default_text_search_config = 'pg_catalog.spanish'
datestyle = 'iso, mdy'
timezone = 'Europe/Madrid'
lc_messages = 'es_ES.UTF-8'
lc_monetary = 'es_ES.UTF-8'
lc_numeric = 'es_ES.UTF-8'
lc_time = 'es_ES.UTF-8'
EOF

    # Configurar pg_hba.conf para autenticación local
    cat > "$pg_hba" <<EOF
# PostgreSQL Client Authentication Configuration
# Generado automáticamente por scripts/install/postgresql.sh

# TYPE  DATABASE        USER            ADDRESS                 METHOD

# Local connections
local   all             all                                     peer
local   ${AUDIT_DB_NAME}        ${AUDIT_DB_USER}                        md5

# IPv4 local connections
host    all             all             127.0.0.1/32            scram-sha-256
host    ${AUDIT_DB_NAME}        ${AUDIT_DB_USER}        127.0.0.1/32            md5

# IPv6 local connections
host    all             all             ::1/128                 scram-sha-256

# Replication
local   replication     all                                     peer
host    replication     all             127.0.0.1/32            scram-sha-256
host    replication     all             ::1/128                 scram-sha-256
EOF

    log_info "Configuración PostgreSQL actualizada"
}

create_audit_database() {
    log_step "Creando base de datos y usuario de auditoría..."

    # Iniciar servicio si no está corriendo
    systemctl start postgresql
    sleep 2

    # Crear usuario y base de datos
    sudo -u postgres psql <<EOF
-- Crear usuario si no existe
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '${AUDIT_DB_USER}') THEN
        CREATE ROLE ${AUDIT_DB_USER} WITH LOGIN PASSWORD '${AUDIT_DB_PASSWORD}';
    ELSE
        ALTER ROLE ${AUDIT_DB_USER} WITH PASSWORD '${AUDIT_DB_PASSWORD}';
    END IF;
END
\$\$;

-- Crear base de datos si no existe
SELECT 'CREATE DATABASE ${AUDIT_DB_NAME} OWNER ${AUDIT_DB_USER} ENCODING ''UTF8'' LC_COLLATE ''es_ES.UTF-8'' LC_CTYPE ''es_ES.UTF-8'' TEMPLATE template0'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${AUDIT_DB_NAME}')\gexec

-- Otorgar permisos
GRANT ALL PRIVILEGES ON DATABASE ${AUDIT_DB_NAME} TO ${AUDIT_DB_USER};
\c ${AUDIT_DB_NAME}
GRANT ALL ON SCHEMA public TO ${AUDIT_DB_USER};
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO ${AUDIT_DB_USER};
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO ${AUDIT_DB_USER};
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO ${AUDIT_DB_USER};

-- Extensiones necesarias
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
EOF

    log_info "Base de datos '${AUDIT_DB_NAME}' y usuario '${AUDIT_DB_USER}' creados"
}

init_audit_schema() {
    log_step "Inicializando schema de auditoría..."

    local schema_file="${PROJECT_ROOT}/config/postgresql/audit-db.sql"
    if [[ ! -f "$schema_file" ]]; then
        # Copiar desde infrastructure/docker si existe
        local source_schema="${PROJECT_ROOT}/infrastructure/docker/init-audit-db.sql"
        if [[ -f "$source_schema" ]]; then
            mkdir -p "$(dirname "$schema_file")"
            cp "$source_schema" "$schema_file"
            log_info "Schema copiado desde infrastructure/docker/"
        else
            log_warn "No se encontró schema SQL en ${source_schema}"
            return 0
        fi
    fi

    # Ejecutar schema
    PGPASSWORD="${AUDIT_DB_PASSWORD}" psql -h "${AUDIT_DB_HOST}" -p "${AUDIT_DB_PORT}" -U "${AUDIT_DB_USER}" -d "${AUDIT_DB_NAME}" -f "$schema_file" >/dev/null 2>&1 || {
        log_warn "Schema ya aplicado o error (ignorando si tablas existen)"
    }

    log_info "Schema de auditoría inicializado"
}

verify_postgresql() {
    log_step "Verificando PostgreSQL..."

    # Test conexión
    if PGPASSWORD="${AUDIT_DB_PASSWORD}" psql -h "${AUDIT_DB_HOST}" -p "${AUDIT_DB_PORT}" -U "${AUDIT_DB_USER}" -d "${AUDIT_DB_NAME}" -c "SELECT 1" >/dev/null 2>&1; then
        log_info "Conexión PostgreSQL: OK"
    else
        log_error "Conexión PostgreSQL: FALLIDA"
        return 1
    fi

    # Verificar tablas
    local tables
    tables=$(PGPASSWORD="${AUDIT_DB_PASSWORD}" psql -h "${AUDIT_DB_HOST}" -p "${AUDIT_DB_PORT}" -U "${AUDIT_DB_USER}" -d "${AUDIT_DB_NAME}" -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_name LIKE 'audit_%' OR table_name IN ('approval_requests','task_queue','agent_sessions')")
    log_info "Tablas de auditoría: ${tables}"

    # Verificar extensiones
    local extensions
    extensions=$(PGPASSWORD="${AUDIT_DB_PASSWORD}" psql -h "${AUDIT_DB_HOST}" -p "${AUDIT_DB_PORT}" -U "${AUDIT_DB_USER}" -d "${AUDIT_DB_NAME}" -tAc "SELECT extname FROM pg_extension WHERE extname IN ('uuid-ossp','pgcrypto')")
    log_info "Extensiones: ${extensions}"

    return 0
}

enable_service() {
    log_step "Habilitando servicio PostgreSQL..."

    systemctl enable postgresql >/dev/null 2>&1
    systemctl start postgresql

    if systemctl is-active --quiet postgresql; then
        log_info "Servicio PostgreSQL activo"
    else
        log_error "Servicio PostgreSQL no se inició"
        systemctl status postgresql --no-pager
        return 1
    fi
}

main() {
    log_info "=== Instalador PostgreSQL para Auditoría ==="
    log_info "DB: ${AUDIT_DB_NAME} | User: ${AUDIT_DB_USER} | Host: ${AUDIT_DB_HOST}:${AUDIT_DB_PORT}"
    echo ""

    check_root
    validate_env
    install_postgresql
    configure_postgresql
    enable_service
    create_audit_database
    init_audit_schema

    if verify_postgresql; then
        log_info "✅ PostgreSQL configurado correctamente para auditoría"
    else
        log_error "❌ Error en verificación PostgreSQL"
        exit 1
    fi
}

main "$@"