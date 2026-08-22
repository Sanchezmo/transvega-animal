#!/usr/bin/env bash
# scripts/backup/restore.sh
# Restaura backup de bases de datos (CON CONFIRMACIÓN)
# Uso: ./scripts/backup/restore.sh <backup_file.tar.gz>

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

if [[ -f "${PROJECT_ROOT}/.env" ]]; then
    set -a
    source "${PROJECT_ROOT}/.env"
    set +a
fi

BACKUP_FILE="${1:-}"

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
        log_error "Requiere root (sudo)"
        exit 1
    fi
}

validate_backup() {
    if [[ -z "$BACKUP_FILE" ]]; then
        log_error "Uso: $0 <backup_file.tar.gz>"
        exit 1
    fi

    if [[ ! -f "$BACKUP_FILE" ]]; then
        log_error "Archivo no encontrado: $BACKUP_FILE"
        exit 1
    fi

    log_info "Backup a restaurar: $BACKUP_FILE"
}

confirm_restore() {
    echo ""
    log_warn "⚠️  ADVERTENCIA: Esto SOBREESCRIBIRÁ las bases de datos actuales:"
    echo "  - MariaDB (Dolibarr): ${DOLIBARR_DB_NAME:-dolibarr}"
    echo "  - PostgreSQL (Auditoría): ${AUDIT_DB_NAME:-audit}"
    echo "  - Redis: datos actuales"
    echo ""
    read -p "¿Estás SEGURO de querer continuar? Escribe 'RESTAURAR' para confirmar: " confirm
    echo ""

    if [[ "$confirm" != "RESTAURAR" ]]; then
        log_info "Restauración cancelada por el usuario"
        exit 0
    fi
}

extract_backup() {
    log_step "Extrayendo backup..."

    local tmp_dir
    tmp_dir=$(mktemp -d -t transvega-restore-XXXXXX)
    trap "rm -rf $tmp_dir" EXIT

    tar -xzf "$BACKUP_FILE" -C "$tmp_dir"

    # Encontrar directorio extraído
    local extracted_dir
    extracted_dir=$(find "$tmp_dir" -maxdepth 1 -type d -name "transvega_*" | head -1)

    if [[ -z "$extracted_dir" ]]; then
        log_error "Formato de backup inválido"
        exit 1
    fi

    echo "$extracted_dir"
}

restore_mariadb() {
    local backup_dir="$1"
    local sql_file
    sql_file=$(find "$backup_dir" -name "mariadb_*.sql.gz" | head -1)

    if [[ -z "$sql_file" ]]; then
        log_warn "MariaDB: No hay backup en el archivo"
        return 0
    fi

    log_step "Restaurando MariaDB (Dolibarr)..."

    local db_name="${DOLIBARR_DB_NAME:-dolibarr}"
    local db_user="${DOLIBARR_DB_USER:-dolibarr}"
    local db_pass="${DOLIBARR_DB_PASSWORD}"
    local db_host="${DOLIBARR_DB_HOST:-127.0.0.1}"
    local db_port="${DOLIBARR_DB_PORT:-3306}"

    # Dropear y recrear base de datos
    mysql -h"$db_host" -P"$db_port" -u root -p"${DOLIBARR_DB_ROOT_PASSWORD}" -e "DROP DATABASE IF EXISTS \`$db_name\`; CREATE DATABASE \`$db_name\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

    # Restaurar
    if gunzip -c "$sql_file" | mysql -h"$db_host" -P"$db_port" -u"$db_user" -p"$db_pass" "$db_name"; then
        log_info "MariaDB: RESTAURADO"
    else
        log_error "MariaDB: FALLÓ LA RESTAURACIÓN"
        return 1
    fi
}

restore_postgresql() {
    local backup_dir="$1"
    local sql_file
    sql_file=$(find "$backup_dir" -name "postgresql_*.sql.gz" | head -1)

    if [[ -z "$sql_file" ]]; then
        log_warn "PostgreSQL: No hay backup en el archivo"
        return 0
    fi

    log_step "Restaurando PostgreSQL (Auditoría)..."

    local db_name="${AUDIT_DB_NAME:-audit}"
    local db_user="${AUDIT_DB_USER:-audit}"
    local db_pass="${AUDIT_DB_PASSWORD}"
    local db_host="${AUDIT_DB_HOST:-127.0.0.1}"
    local db_port="${AUDIT_DB_PORT:-5432}"

    # Dropear y recrear
    PGPASSWORD="$db_pass" psql -h"$db_host" -p"$db_port" -U"$db_user" -d postgres -c "DROP DATABASE IF EXISTS $db_name; CREATE DATABASE $db_name OWNER $db_user ENCODING 'UTF8' LC_COLLATE 'es_ES.UTF-8' LC_CTYPE 'es_ES.UTF-8' TEMPLATE template0;"

    # Restaurar
    if gunzip -c "$sql_file" | PGPASSWORD="$db_pass" psql -h"$db_host" -p"$db_port" -U"$db_user" -d"$db_name"; then
        log_info "PostgreSQL: RESTAURADO"
    else
        log_error "PostgreSQL: FALLÓ LA RESTAURACIÓN"
        return 1
    fi
}

restore_redis() {
    local backup_dir="$1"
    local rdb_file
    rdb_file=$(find "$backup_dir" -name "redis_dump.rdb" | head -1)

    if [[ -z "$rdb_file" ]]; then
        log_warn "Redis: No hay backup RDB en el archivo"
        return 0
    fi

    log_step "Restaurando Redis..."

    local redis_host="${REDIS_HOST:-127.0.0.1}"
    local redis_port="${REDIS_PORT:-6379}"
    local redis_pass="${REDIS_PASSWORD}"

    # Detener Redis, copiar RDB, reiniciar
    systemctl stop redis-server

    local rdb_path
    rdb_path=$(redis-cli -h"$redis_host" -p"$redis_port" -a"$redis_pass" CONFIG GET dir 2>/dev/null | tail -1 || echo "/var/lib/redis")

    cp "$rdb_file" "${rdb_path}/dump.rdb"
    chown redis:redis "${rdb_path}/dump.rdb" 2>/dev/null || true

    systemctl start redis-server
    sleep 2

    if redis-cli -h"$redis_host" -p"$redis_port" -a"$redis_pass" ping | grep -q "PONG"; then
        log_info "Redis: RESTAURADO"
    else
        log_error "Redis: NO RESPONDE TRAS RESTAURACIÓN"
        return 1
    fi
}

main() {
    echo ""
    echo "=========================================="
    echo "  TRANSVEGA - RESTAURACIÓN DE BACKUP"
    echo "=========================================="
    echo ""

    check_root
    validate_backup
    confirm_restore

    local extracted_dir
    extracted_dir=$(extract_backup)

    restore_mariadb "$extracted_dir"
    restore_postgresql "$extracted_dir"
    restore_redis "$extracted_dir"

    echo ""
    log_info "✅ Restauración completada"
    echo ""
    echo "Verificar servicios:"
    echo "  make status"
}

main "$@"