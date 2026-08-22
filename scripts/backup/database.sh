#!/usr/bin/env bash
# scripts/backup/database.sh
# Backup de bases de datos (MariaDB + PostgreSQL + Redis)
# Uso: ./scripts/backup/database.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

if [[ -f "${PROJECT_ROOT}/.env" ]]; then
    set -a
    source "${PROJECT_ROOT}/.env"
    set +a
fi

BACKUP_DIR="${BACKUP_LOCAL_PATH:-/var/backups/transvega}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="transvega_${TIMESTAMP}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }
log_step()  { echo -e "${BLUE}[STEP]${NC} $*"; }

mkdir -p "${BACKUP_DIR}/${BACKUP_NAME}"

backup_mariadb() {
    log_step "Backup MariaDB (Dolibarr)..."

    local db_name="${DOLIBARR_DB_NAME:-dolibarr}"
    local db_user="${DOLIBARR_DB_USER:-dolibarr}"
    local db_pass="${DOLIBARR_DB_PASSWORD}"
    local db_host="${DOLIBARR_DB_HOST:-127.0.0.1}"
    local db_port="${DOLIBARR_DB_PORT:-3306}"

    if mysqldump -h"$db_host" -P"$db_port" -u"$db_user" -p"$db_pass" \
        --single-transaction --routines --triggers --events \
        "$db_name" | gzip > "${BACKUP_DIR}/${BACKUP_NAME}/mariadb_${db_name}.sql.gz"; then
        log_info "MariaDB: OK (${BACKUP_DIR}/${BACKUP_NAME}/mariadb_${db_name}.sql.gz)"
    else
        log_error "MariaDB: FALLÓ"
        return 1
    fi
}

backup_postgresql() {
    log_step "Backup PostgreSQL (Auditoría)..."

    local db_name="${AUDIT_DB_NAME:-audit}"
    local db_user="${AUDIT_DB_USER:-audit}"
    local db_pass="${AUDIT_DB_PASSWORD}"
    local db_host="${AUDIT_DB_HOST:-127.0.0.1}"
    local db_port="${AUDIT_DB_PORT:-5432}"

    if PGPASSWORD="$db_pass" pg_dump -h"$db_host" -p"$db_port" -U"$db_user" -d"$db_name" \
        --no-owner --no-privileges | gzip > "${BACKUP_DIR}/${BACKUP_NAME}/postgresql_${db_name}.sql.gz"; then
        log_info "PostgreSQL: OK (${BACKUP_DIR}/${BACKUP_NAME}/postgresql_${db_name}.sql.gz)"
    else
        log_error "PostgreSQL: FALLÓ"
        return 1
    fi
}

backup_redis() {
    log_step "Backup Redis..."

    local redis_host="${REDIS_HOST:-127.0.0.1}"
    local redis_port="${REDIS_PORT:-6379}"
    local redis_pass="${REDIS_PASSWORD}"

    # Usar BGSAVE para snapshot no bloqueante
    if redis-cli -h"$redis_host" -p"$redis_port" -a"$redis_pass" BGSAVE >/dev/null 2>&1; then
        # Esperar a que termine
        local saved=0
        for i in {1..30}; do
            if redis-cli -h"$redis_host" -p"$redis_port" -a"$redis_pass" LASTSAVE | grep -q "$(redis-cli -h"$redis_host" -p"$redis_port" -a"$redis_pass" LASTSAVE)"; then
                sleep 1
            else
                saved=1
                break
            fi
        done

        # Copiar RDB
        local rdb_path
        rdb_path=$(redis-cli -h"$redis_host" -p"$redis_port" -a"$redis_pass" CONFIG GET dir | tail -1)
        local rdb_file="${rdb_path}/dump.rdb"

        if [[ -f "$rdb_file" ]]; then
            cp "$rdb_file" "${BACKUP_DIR}/${BACKUP_NAME}/redis_dump.rdb"
            log_info "Redis: OK (${BACKUP_DIR}/${BACKUP_NAME}/redis_dump.rdb)"
        else
            log_warn "Redis: RDB no encontrado en $rdb_file"
        fi
    else
        log_error "Redis: BGSAVE falló"
        return 1
    fi
}

backup_config() {
    log_step "Backup configuración..."

    # Solo archivos de config, NO secretos
    local config_files=(
        "${PROJECT_ROOT}/.env.example"
        "${PROJECT_ROOT}/docker-compose.yml"
        "${PROJECT_ROOT}/docker-compose.*.yml"
        "${PROJECT_ROOT}/Makefile"
        "${PROJECT_ROOT}/pyproject.toml"
        "${PROJECT_ROOT}/README.md"
    )

    mkdir -p "${BACKUP_DIR}/${BACKUP_NAME}/config"

    for pattern in "${config_files[@]}"; do
        for file in $pattern; do
            if [[ -f "$file" ]]; then
                cp "$file" "${BACKUP_DIR}/${BACKUP_NAME}/config/"
            fi
        done
    done

    # Scripts
    cp -r "${PROJECT_ROOT}/scripts" "${BACKUP_DIR}/${BACKUP_NAME}/config/" 2>/dev/null || true
    cp -r "${PROJECT_ROOT}/config" "${BACKUP_DIR}/${BACKUP_NAME}/config/" 2>/dev/null || true

    log_info "Configuración: OK"
}

create_manifest() {
    log_step "Creando manifest..."

    cat > "${BACKUP_DIR}/${BACKUP_NAME}/MANIFEST.txt" <<EOF
Transvega Animal Backup
=======================
Fecha: $(date -Iseconds)
Host: $(hostname)
Usuario: $(whoami)

Contenido:
EOF

    for file in "${BACKUP_DIR}/${BACKUP_NAME}"/*; do
        if [[ -f "$file" ]]; then
            local size
            size=$(du -h "$file" | cut -f1)
            echo "  $(basename "$file"): ${size}" >> "${BACKUP_DIR}/${BACKUP_NAME}/MANIFEST.txt"
        elif [[ -d "$file" ]]; then
            local count
            count=$(find "$file" -type f | wc -l)
            echo "  $(basename "$file")/ (${count} archivos)" >> "${BACKUP_DIR}/${BACKUP_NAME}/MANIFEST.txt"
        fi
    done

    log_info "Manifest creado"
}

main() {
    log_info "=== Backup Transvega ==="
    log_info "Destino: ${BACKUP_DIR}/${BACKUP_NAME}"
    echo ""

    backup_mariadb
    backup_postgresql
    backup_redis
    backup_config
    create_manifest

    # Comprimir todo
    log_step "Comprimiendo backup completo..."
    cd "${BACKUP_DIR}"
    tar -czf "${BACKUP_NAME}.tar.gz" "${BACKUP_NAME}"
    rm -rf "${BACKUP_NAME}"

    local size
    size=$(du -h "${BACKUP_DIR}/${BACKUP_NAME}.tar.gz" | cut -f1)
    log_info "✅ Backup completado: ${BACKUP_DIR}/${BACKUP_NAME}.tar.gz (${size})"
    echo ""
    echo "Para restaurar:"
    echo "  ./scripts/backup/restore.sh ${BACKUP_DIR}/${BACKUP_NAME}.tar.gz"
}

main "$@"