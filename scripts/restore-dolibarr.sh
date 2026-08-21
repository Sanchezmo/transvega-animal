#!/usr/bin/env bash
# scripts/restore-dolibarr.sh
# Restaura backup de Dolibarr en instalación nativa (MariaDB host + documents)
# Uso: ./scripts/restore-dolibarr.sh <backup_directory>

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

BACKUP_DIR="${1:-}"

if [[ -z "$BACKUP_DIR" ]]; then
    echo "Uso: $0 <backup_directory>"
    echo "Ejemplo: $0 backups/dolibarr_migration_staging_20260821_120000"
    exit 1
fi

if [[ ! -d "$BACKUP_DIR" ]]; then
    log_error "Directorio de backup no encontrado: $BACKUP_DIR"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

DOLIBARR_ROOT="${PROJECT_ROOT}/dolibarr"
DOCUMENTS_DIR="${DOLIBARR_ROOT}/documents"

# Credenciales MariaDB host (deben coincidir con install-dolibarr.sh)
DB_HOST="localhost"
DB_PORT="3306"
DB_NAME="dolibarr"
DB_USER="dolibarr"
DB_PASS="${DOLIBARR_DB_PASSWORD:-dolibarr_password_segura_2026}"

# =============================================================================
# FUNCIONES
# =============================================================================

check_backup() {
    log_step "Verificando backup en ${BACKUP_DIR}..."
    
    local metadata="${BACKUP_DIR}/metadata.json"
    local sql_gz="${BACKUP_DIR}/database.sql.gz"
    local docs_tar="${BACKUP_DIR}/documents.tar.gz"
    
    if [[ ! -f "$sql_gz" ]]; then
        log_error "database.sql.gz no encontrado en backup"
        exit 1
    fi
    
    if [[ -f "$metadata" ]]; then
        log_info "Metadatos del backup:"
        cat "$metadata" | python3 -m json.tool 2>/dev/null || cat "$metadata"
    fi
    
    # Verificar integridad
    if ! gzip -t "$sql_gz" 2>/dev/null; then
        log_error "database.sql.gz corrupto"
        exit 1
    fi
    
    if [[ -f "$docs_tar" ]] && ! tar -tzf "$docs_tar" >/dev/null 2>&1; then
        log_error "documents.tar.gz corrupto"
        exit 1
    fi
    
    log_info "Backup verificado correctamente"
}

check_mariadb() {
    log_step "Verificando MariaDB host..."
    
    if ! systemctl is-active --quiet mariadb; then
        log_error "MariaDB no está corriendo. Ejecuta: sudo systemctl start mariadb"
        exit 1
    fi
    
    # Verificar conexión
    if ! mysql -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" -p"$DB_PASS" -e "SELECT 1" >/dev/null 2>&1; then
        log_error "No se puede conectar a MariaDB con usuario $DB_USER"
        log_info "Verifica que el usuario existe y la contraseña es correcta"
        exit 1
    fi
    
    log_info "MariaDB accesible"
}

restore_database() {
    log_step "Restaurando base de datos en MariaDB host..."
    
    local sql_gz="${BACKUP_DIR}/database.sql.gz"
    
    # Verificar si la BD ya tiene tablas (migración previa)
    local table_count
    table_count=$(mysql -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" -p"$DB_PASS" -e "USE $DB_NAME; SHOW TABLES;" 2>/dev/null | wc -l)
    
    if [[ $table_count -gt 1 ]]; then
        log_warn "Base de datos $DB_NAME ya tiene $((table_count - 1)) tablas"
        read -p "¿Sobrescribir? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "Restauración BD cancelada por el usuario"
            return 0
        fi
    fi
    
    # Restaurar
    log_info "Importando SQL (esto puede tardar)..."
    gunzip -c "$sql_gz" | mysql -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" -p"$DB_PASS" "$DB_NAME"
    
    # Verificar
    local restored_tables
    restored_tables=$(mysql -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" -p"$DB_PASS" -e "USE $DB_NAME; SHOW TABLES;" 2>/dev/null | wc -l)
    log_info "Tablas restauradas: $((restored_tables - 1))"
    
    # Verificar usuario admin
    local admin_count
    admin_count=$(mysql -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" -p"$DB_PASS" -e "USE $DB_NAME; SELECT COUNT(*) FROM llx_user WHERE login='admin';" 2>/dev/null | tail -1)
    log_info "Usuarios admin: $admin_count"
}

restore_documents() {
    log_step "Restaurando documents..."
    
    local docs_tar="${BACKUP_DIR}/documents.tar.gz"
    
    if [[ ! -f "$docs_tar" ]]; then
        log_warn "documents.tar.gz no encontrado, saltando"
        return 0
    fi
    
    # Verificar si ya hay documents
    if [[ -d "$DOCUMENTS_DIR" && -n "$(ls -A "$DOCUMENTS_DIR" 2>/dev/null)" ]]; then
        log_warn "Directorio documents ya tiene contenido"
        read -p "¿Sobrescribir? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "Restauración documents cancelada por el usuario"
            return 0
        fi
        rm -rf "$DOCUMENTS_DIR"/*
    fi
    
    mkdir -p "$DOCUMENTS_DIR"
    
    log_info "Extrayendo documents..."
    tar -xzf "$docs_tar" -C "$DOCUMENTS_DIR" --strip-components=1
    
    # Permisos
    local apache_user="www-data"
    id "www-data" >/dev/null 2>&1 || apache_user="apache"
    chown -R "${apache_user}:${apache_user}" "$DOCUMENTS_DIR"
    chmod -R 775 "$DOCUMENTS_DIR"
    
    local doc_count
    doc_count=$(find "$DOCUMENTS_DIR" -type f | wc -l)
    log_info "Archivos restaurados: $doc_count"
}

verify_restoration() {
    log_step "Verificando restauración..."
    
    # Verificar BD
    local tables
    tables=$(mysql -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" -p"$DB_PASS" -e "USE $DB_NAME; SHOW TABLES;" 2>/dev/null | tail -n +2 | wc -l)
    log_info "Tablas en BD: $tables"
    
    # Verificar conf.php existe
    if [[ -f "${DOLIBARR_ROOT}/conf/conf.php" ]]; then
        log_info "conf.php: ✓"
    else
        log_warn "conf.php: NO ENCONTRADO (ejecutar install-dolibarr.sh primero)"
    fi
    
    # Verificar install.lock
    if [[ -f "${DOCUMENTS_DIR}/install.lock" ]]; then
        log_info "install.lock: ✓"
    else
        log_warn "install.lock: NO ENCONTRADO"
    fi
    
    log_info "Verificación completada"
}

print_summary() {
    echo ""
    echo "=========================================="
    echo "  RESTAURACIÓN DOLIBARR COMPLETADA"
    echo "=========================================="
    echo ""
    echo "Backup origen:  ${BACKUP_DIR}"
    echo "BD destino:     ${DB_NAME}@${DB_HOST}:${DB_PORT}"
    echo "Documents:      ${DOCUMENTS_DIR}"
    echo ""
    echo "Próximos pasos:"
    echo "  1. Verificar conf.php tiene credenciales correctas"
    echo "  2. Configurar Apache: sudo ./scripts/configure-apache-dolibarr.sh"
    echo "  3. Healthcheck: ./scripts/dolibarr-health.sh"
    echo "  4. Probar REST API: curl http://localhost:8080/api/index.php/thirdparties"
    echo ""
}

# =============================================================================
# MAIN
# =============================================================================

main() {
    log_info "=== Restauración Dolibarr Host Nativo ==="
    log_info "Backup: ${BACKUP_DIR}"
    echo ""
    
    check_backup
    check_mariadb
    restore_database
    restore_documents
    verify_restoration
    print_summary
    
    log_info "✅ Restauración completada"
}

main "$@"