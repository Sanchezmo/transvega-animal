#!/bin/bash
# Script de configuración inicial del entorno de desarrollo
# Transvega Animal - Setup Development Environment

set -e

echo "🚀 Configurando entorno de desarrollo Transvega Animal..."

# Colores para output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Función para logging
log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Verificar prerrequisitos
check_prerequisites() {
    log_info "Verificando prerrequisitos..."
    
    # Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker no está instalado"
        exit 1
    fi
    log_info "Docker: $(docker --version)"
    
    # Docker Compose
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        log_error "Docker Compose no está instalado"
        exit 1
    fi
    log_info "Docker Compose: $(docker compose version)"
    
    # Python
    if ! command -v python3 &> /dev/null; then
        log_error "Python 3 no está instalado"
        exit 1
    fi
    log_info "Python: $(python3 --version)"
    
    # Git
    if ! command -v git &> /dev/null; then
        log_warn "Git no está instalado (recomendado)"
    fi
}

# Crear archivo .env.local si no existe
setup_env_file() {
    log_info "Configurando variables de entorno..."
    
    if [ ! -f .env.local ]; then
        if [ -f .env.example ]; then
            cp .env.example .env.local
            log_info "Archivo .env.local creado desde .env.example"
            log_warn "IMPORTANTE: Edita .env.local con tus valores reales antes de continuar"
        else
            log_error "No se encuentra .env.example"
            exit 1
        fi
    else
        log_info ".env.local ya existe"
    fi
}

# Generar secretos si no existen
generate_secrets() {
    log_info "Generando secretos criptográficos..."
    
    # Función para generar secreto si no existe en .env.local
    generate_if_missing() {
        local var_name=$1
        local generator=$2
        local description=$3
        
        if ! grep -q "^${var_name}=" .env.local || grep -q "^${var_name}=$" .env.local || grep -q "^${var_name}=your-" .env.local; then
            local value=$(eval $generator)
            # Escapar para sed
            value_escaped=$(printf '%s\n' "$value" | sed 's/[[\.*^$()+?{|/]/\\&/g')
            sed -i "s|^${var_name}=.*|${var_name}=${value_escaped}|" .env.local
            log_info "Generado: ${var_name} (${description})"
        fi
    }
    
    generate_if_missing "AUDIT_DB_PASSWORD" "openssl rand -base64 32" "PostgreSQL audit DB"
    generate_if_missing "REDIS_PASSWORD" "openssl rand -base64 32" "Redis"
    generate_if_missing "JWT_SECRET_KEY" "openssl rand -base64 64" "JWT signing"
    generate_if_missing "FERNET_KEY" "python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'" "Encryption"
    generate_if_missing "GRAFANA_ADMIN_PASSWORD" "openssl rand -base64 16" "Grafana admin"
    generate_if_missing "BACKUP_ENCRYPTION_KEY" "openssl rand -base64 32" "Backup encryption"
    
    # API Keys por agente
    for agent in SUPERVISOR PRODUCTS COMPLIANCE PUBLISHING SALES INVOICING PURCHASES BANKING ACCOUNTING TAX MARKETING TECHNICAL; do
        var="AGENT_API_KEY_${agent}"
        if ! grep -q "^${var}=" .env.local || grep -q "^${var}=$" .env.local || grep -q "^${var}=your-" .env.local; then
            value="tvsk_$(openssl rand -hex 16)"
            sed -i "s|^${var}=.*|${var}=${value}|" .env.local
            log_info "Generado: ${var}"
        fi
    done
}

# Crear directorios necesarios
create_directories() {
    log_info "Creando directorios necesarios..."
    
    mkdir -p backups logs tmp data
    mkdir -p infrastructure/docker
    mkdir -p infrastructure/monitoring/grafana-dashboards
    mkdir -p infrastructure/cloudflare
    mkdir -p scripts
    
    log_info "Directorios creados"
}

# Levantar servicios de desarrollo
start_services() {
    log_info "Levantando servicios de desarrollo..."
    
    docker compose -f docker-compose.yml up -d --build
    
    log_info "Esperando health checks..."
    sleep 15
    
    # Verificar servicios
    check_service "API" "http://localhost:8000/health"
    check_service "Mock Dolibarr" "http://localhost:8001/health"
    check_service "Dashboard" "http://localhost:3000/health"
    check_service "Approvals" "http://localhost:8002/health"
    check_service "Grafana" "http://localhost:3001/api/health"
    check_service "Prometheus" "http://localhost:9090/-/healthy"
}

check_service() {
    local name=$1
    local url=$2
    local max_attempts=10
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if curl -sf "$url" > /dev/null 2>&1; then
            log_info "✅ $name está disponible"
            return 0
        fi
        sleep 2
        attempt=$((attempt + 1))
    done
    
    log_warn "⚠️ $name no responde en $url (continuando...)"
    return 1
}

# Sembrar datos de prueba
seed_data() {
    log_info "Sembrando datos de prueba..."
    
    docker compose exec -T api python scripts/seed_fake_data.py
    
    log_info "Datos de prueba sembrados"
}

# Ejecutar tests
run_tests() {
    log_info "Ejecutando tests..."
    
    docker compose exec -T api pytest tests/ -v --tb=short
    
    log_info "Tests completados"
}

# Menú principal
show_menu() {
    echo ""
    echo "========================================"
    echo "  Transvega Animal - Setup Dev"
    echo "========================================"
    echo ""
    echo "1) Setup completo (prerequisitos + env + secretos + directorios + servicios + seed)"
    echo "2) Solo configurar .env.local y secretos"
    echo "3) Solo levantar servicios"
    echo "4) Solo sembrar datos de prueba"
    echo "4) Ejecutar tests"
    echo "5) Ver logs"
    echo "6) Parar servicios"
    echo "7) Limpiar todo (CUIDADO: borra volúmenes)"
    echo "0) Salir"
    echo ""
    read -p "Selecciona opción: " option
}

main() {
    case ${1:-menu} in
        full|1)
            check_prerequisites
            setup_env_file
            generate_secrets
            create_directories
            start_services
            seed_data
            log_info "✅ Setup completo finalizado"
            echo ""
            echo "🌐 Servicios disponibles:"
            echo "   API:           http://localhost:8000"
            echo "   Docs:          http://localhost:8000/docs"
            echo "   Mock Dolibarr: http://localhost:8001"
            echo "   Dashboard:     http://localhost:3000"
            echo "   Aprobaciones:  http://localhost:8002"
            echo "   Grafana:       http://localhost:3001 (admin / ver .env.local)"
            echo "   Prometheus:    http://localhost:9090"
            echo "   Mailhog:       http://localhost:8025"
            echo ""
            ;;
        env|2)
            setup_env_file
            generate_secrets
            ;;
        up|3)
            start_services
            ;;
        seed|4)
            seed_data
            ;;
        test|5)
            run_tests
            ;;
        logs|6)
            docker compose logs -f
            ;;
        down|6)
            docker compose down
            log_info "Servicios parados"
            ;;
        clean|7)
            read -p "⚠️  Esto borrará TODOS los datos (BD, Redis, volúmenes). ¿Seguro? (y/N): " confirm
            if [ "$confirm" = "y" ] || [ "$confirm" = "Y" ]; then
                docker compose down -v --rmi all
                rm -rf backups/* logs/* tmp/*
                log_info "Limpieza completada"
            else
                log_info "Cancelado"
            fi
            ;;
        menu|0|*)
            show_menu
            read -p "Selecciona opción: " option
            main $option
            ;;
    esac
}

# Ejecutar
main "$@"