#!/usr/bin/env bash
# scripts/backup-dolibarr.sh
# Backup completo de Dolibarr Docker (BD + documents) para migración a host
# Uso: ./scripts/backup-dolibarr.sh [staging|dev]

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

# =============================================================================
# CONFIGURACIÓN
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

ENVIRONMENT="${1:-staging}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="${PROJECT_ROOT}/backups/dolibarr_migration_${ENVIRONMENT}_${TIMESTAMP}"

# Volúmenes Docker según entorno
if [[ "$ENVIRONMENT" == "staging" ]]; then
    DB_VOLUME="transvega-animal_dolibarr-db-data-staging"
    DOCS_VOLUME="transvega-animal_dolibarr-documents-staging"
    DB_ROOT_PASSWORD="${DOLIBARR_DB_ROOT_PASSWORD:-r1o2o3t4p5a6s7s8w9o0r1d2x3y4z5}"
    DB_NAME="dolibarr"
elif [[ "$ENVIRONMENT" == "dev" ]]; then
    DB_VOLUME="transvega-animal_dolibarr_db"
    DOCS_VOLUME="transvega-animal_dolibarr_data"
    DB_ROOT_PASSWORD="${DOLIBARR_DB_ROOT_PASSWORD:-root_password}"
    DB_NAME="dolibarr"
else
    log_error "Entorno inválido: $ENVIRONMENT (usar staging|dev)"
    exit 1
fi

# =============================================================================
# FUNCIONES
# =============================================================================

check_docker() {
    if ! command -v docker >/dev/null 2>&1; then
        log_error "Docker no encontrado"
        exit 1
    fi
    
    # Verificar que el volumen existe
    if ! docker volume inspect "$DB_VOLUME" >/dev/null 2>&1; then
        log_error "Volumen BD no encontrado: $DB_VOLUME"
        exit 1
    fi
    if ! docker volume inspect "$DOCS_VOLUME" >/dev/null 2>&1; then
        log_warn "Volumen documents no encontrado: $DOCS_VOLUME (continuando sin documents)"
    fi
}

create_backup_dir() {
    log_step "Creando directorio de backup: ${BACKUP_DIR}"
    mkdir -p "$BACKUP_DIR"
}

backup_database() {
    log_step "Backup de base de datos MariaDB (${DB_VOLUME})..."
    
    local sql_file="${BACKUP_DIR}/database.sql"
    local sql_gz="${BACKUP_DIR}/database.sql.gz"
    
    # Usar contenedor temporal para mysqldump
    docker run --rm \
        -v "$DB_VOLUME":/var/lib/mysql \
        -e MARIADB_ROOT_PASSWORD="$DB_ROOT_PASSWORD" \
        mariadb:11 \
        mariadb-dump -u root -p"$DB_ROOT_PASSWORD" --single-transaction --routines --triggers --events "$DB_NAME" > "$sql_file"
    
    if [[ ! -s "$sql_file" ]]; then
        log_error "Dump SQL vacío o fallido"
        exit 1
    fi
    
    # Comprimir
    gzip -c "$sql_file" > "$sql_gz"
    rm "$sql_file"
    
    local size
    size=$(du -h "$sql_gz" | cut -f1)
    log_info "Backup BD completado: ${sql_gz} (${size})"
}

backup_documents() {
    log_step "Backup de documents (${DOCS_VOLUME})..."
    
    local docs_dir="${BACKUP_DIR}/documents"
    local docs_tar="${BACKUP_DIR}/documents.tar.gz"
    
    if docker volume inspect "$DOCS_VOLUME" >/dev/null 2>&1; then
        mkdir -p "$docs_dir"
        
        # Copiar documentos usando contenedor temporal
        docker run --rm \
            -v "$DOCS_VOLUME":/source:ro \
            -v "$docs_dir":/dest \
            alpine \
            cp -a /source/. /dest/
        
        # Comprimir
        tar -czf "$docs_tar" -C "$BACKUP_DIR" documents
        rm -rf "$docs_dir"
        
        local size
        size=$(du -h "$docs_tar" | cut -f1)
        log_info "Backup documents completado: ${docs_tar} (${size})"
    else
        log_warn "Volumen documents no existe, saltando"
    fi
}

backup_metadata() {
    log_step "Guardando metadatos de migración..."
    
    cat > "${BACKUP_DIR}/metadata.json" <<METAEOF
{
    "timestamp": "${TIMESTAMP}",
    "environment": "${ENVIRONMENT}",
    "source": "docker",
    "target": "host_native",
    "dolibarr_version": "20.0.4",
    "database": {
        "volume": "${DB_VOLUME}",
        "name": "${DB_NAME}",
        "backup_file": "database.sql.gz"
    },
    "documents": {
        "volume": "${DOCS_VOLUME}",
        "backup_file": "documents.tar.gz"
    },
    "docker_volumes_preserved": true,
    "notes": "Backup para migración Docker -> Host nativo. Volúmenes Docker NO eliminados."
}
METAEOF
    
    log_info "Metadatos guardados"
}

verify_backup() {
    log_step "Verificando integridad del backup..."
    
    local sql_gz="${BACKUP_DIR}/database.sql.gz"
    local docs_tar="${BACKUP_DIR}/documents.tar.gz"
    local all_ok=1
    
    # Verificar SQL
    if [[ -f "$sql_gz" ]]; then
        if gzip -t "$sql_gz" 2>/dev/null; then
            log_info "  ✓ database.sql.gz: integridad OK"
        else
            log_error "  ✗ database.sql.gz: CORRUPTO"
            all_ok=0
        fi
    else
        log_error "  ✗ database.sql.gz: NO ENCONTRADO"
        all_ok=0
    fi
    
    # Verificar documents
    if [[ -f "$docs_tar" ]]; then
        if tar -tzf "$docs_tar" >/dev/null 2>&1; then
            log_info "  ✓ documents.tar.gz: integridad OK"
        else
            log_error "  ✗ documents.tar.gz: CORRUPTO"
            all_ok=0
        fi
    else
        log_warn "  ⚠ documents.tar.gz: no existe (volumen no encontrado)"
    fi
    
    if [[ $all_ok -eq 1 ]]; then
        log_info "✅ Backup verificado correctamente"
        return 0
    else
        log_error "❌ Backup con errores"
        return 1
    fi
}

print_summary() {
    echo ""
    echo "=========================================="
    echo "  BACKUP DOLIBARR COMPLETADO"
    echo "=========================================="
    echo ""
    echo "Entorno:       ${ENVIRONMENT}"
    echo "Directorio:    ${BACKUP_DIR}"
    echo "Timestamp:     ${TIMESTAMP}"
    echo ""
    echo "Archivos:"
    ls -lh "${BACKUP_DIR}"/
    echo ""
    echo "Volúmenes Docker PRESERVADOS (no eliminados):"
    echo "  - ${DB_VOLUME}"
    echo "  - ${DOCS_VOLUME}"
    echo ""
    echo "Para restaurar en host nativo:"
    echo "  ./scripts/restore-dolibarr.sh ${BACKUP_DIR}"
    echo ""
}

# =============================================================================
# MAIN
# =============================================================================

main() {
    log_info "=== Backup Dolibarr Docker -> Host (${ENVIRONMENT}) ==="
    echo ""
    
    check_docker
    create_backup_dir
    backup_database
    backup_documents
    backup_metadata
    
    if verify_backup; then
        print_summary
        log_info "✅ Backup completado con éxito"
    else
        log_error "❌ Backup completado con errores"
        exit 1
    fi
}

main "$@"