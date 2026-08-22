#!/usr/bin/env bash
# scripts/install/redis.sh
# Instala y configura Redis nativo (idempotente)
# Uso: ./scripts/install/redis.sh

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
REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
REDIS_PORT="${REDIS_PORT:-6379}"
REDIS_PASSWORD="${REDIS_PASSWORD:-}"
REDIS_MAXMEMORY="${REDIS_MAXMEMORY:-512mb}"
REDIS_MAXMEMORY_POLICY="${REDIS_MAXMEMORY_POLICY:-allkeys-lru}"

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
    if [[ -z "$REDIS_PASSWORD" ]]; then
        log_error "Falta REDIS_PASSWORD en .env"
        log_info "Generar con: openssl rand -base64 32"
        exit 1
    fi
}

install_redis() {
    log_step "Instalando Redis..."

    if dpkg -l | grep -q "^ii  redis-server "; then
        log_info "Redis ya instalado"
        return 0
    fi

    apt-get update -qq
    apt-get install -y -qq redis-server

    log_info "Redis instalado"
}

configure_redis() {
    log_step "Configurando Redis..."

    local redis_conf="/etc/redis/redis.conf"
    [[ -f "${redis_conf}.orig" ]] || cp "$redis_conf" "${redis_conf}.orig"

    cat > "$redis_conf" <<EOF
# Redis configuración Transvega
# Generado automáticamente por scripts/install/redis.sh

# Red
bind ${REDIS_HOST}
port ${REDIS_PORT}
timeout 0
tcp-backlog 511

# General
daemonize yes
supervised systemd
pidfile /var/run/redis/redis-server.pid
loglevel notice
logfile /var/log/redis/redis-server.log
databases 16
always-show-logo no

# Snapshots (RDB)
save 900 1
save 300 10
save 60 10000
stop-writes-on-bgsave-error yes
rdbcompression yes
rdbchecksum yes
dbfilename dump.rdb
dir /var/lib/redis

# Replication
replica-serve-stale-data yes
replica-read-only yes
repl-diskless-sync no
repl-diskless-sync-delay 5
repl-disable-tcp-nodelay no

# Seguridad
requirepass ${REDIS_PASSWORD}
# rename-command CONFIG ""  # Descomentar para mayor seguridad
# rename-command FLUSHDB ""
# rename-command FLUSHALL ""

# Clientes
maxclients 10000

# Memoria
maxmemory ${REDIS_MAXMEMORY}
maxmemory-policy ${REDIS_MAXMEMORY_POLICY}

# Lazy freeing
lazyfree-lazy-eviction no
lazyfree-lazy-expire no
lazyfree-lazy-server-del no
replica-lazy-flush no

# Append only file (AOF)
appendonly yes
appendfilename "appendonly.aof"
appendfsync everysec
no-appendfsync-on-rewrite no
auto-aof-rewrite-percentage 100
auto-aof-rewrite-min-size 64mb
aof-load-truncated yes
aof-use-rdb-preamble yes

# Slow log
slowlog-log-slower-than 10000
slowlog-max-len 128

# Latency monitor
latency-monitor-threshold 0

# Event notification
notify-keyspace-events ""

# Advanced
hash-max-ziplist-entries 512
hash-max-ziplist-value 64
list-max-ziplist-size -2
list-compress-depth 0
set-max-intset-entries 512
zset-max-ziplist-entries 128
zset-max-ziplist-value 64
hll-sparse-max-bytes 3000
stream-node-max-bytes 4096
stream-node-max-entries 100
activerehashing yes
client-output-buffer-limit normal 0 0 0
client-output-buffer-limit replica 256mb 64mb 60
client-output-buffer-limit pubsub 32mb 8mb 60
hz 10
dynamic-hz yes
aof-rewrite-incremental-fsync yes
rdb-save-incremental-fsync yes
EOF

    log_info "Configuración Redis actualizada en ${redis_conf}"
}

verify_redis() {
    log_step "Verificando Redis..."

    # Test conexión
    if redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}" -a "${REDIS_PASSWORD}" ping | grep -q "PONG"; then
        log_info "Conexión Redis: OK"
    else
        log_error "Conexión Redis: FALLIDA"
        return 1
    fi

    # Verificar configuración
    local maxmemory
    maxmemory=$(redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}" -a "${REDIS_PASSWORD}" CONFIG GET maxmemory | tail -1)
    log_info "Maxmemory: ${maxmemory}"

    local policy
    policy=$(redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}" -a "${REDIS_PASSWORD}" CONFIG GET maxmemory-policy | tail -1)
    log_info "Maxmemory-policy: ${policy}"

    # Verificar memoria usada
    local used_memory
    used_memory=$(redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}" -a "${REDIS_PASSWORD}" INFO memory | grep "used_memory_human:" | cut -d: -f2 | tr -d '\r')
    log_info "Memoria usada: ${used_memory}"

    return 0
}

enable_service() {
    log_step "Habilitando servicio Redis..."

    systemctl enable redis-server >/dev/null 2>&1
    systemctl restart redis-server

    if systemctl is-active --quiet redis-server; then
        log_info "Servicio Redis activo"
    else
        log_error "Servicio Redis no se inició"
        systemctl status redis-server --no-pager
        return 1
    fi
}

main() {
    log_info "=== Instalador Redis ==="
    log_info "Host: ${REDIS_HOST}:${REDIS_PORT} | MaxMemory: ${REDIS_MAXMEMORY} | Policy: ${REDIS_MAXMEMORY_POLICY}"
    echo ""

    check_root
    validate_env
    install_redis
    configure_redis
    enable_service

    if verify_redis; then
        log_info "✅ Redis configurado correctamente"
    else
        log_error "❌ Error en verificación Redis"
        exit 1
    fi
}

main "$@"