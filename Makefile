# Makefile - Transvega Animal (NATIVO)
# Interfaz simple para gestión de infraestructura nativa
# Uso: make help

.PHONY: help install configure start stop restart status check backup restore test lint format type-check clean

# Variables
SCRIPTS_DIR = ./scripts
PROJECT_ROOT = $(shell pwd)

# Colores
GREEN = \033[0;32m
YELLOW = \033[1;33m
RED = \033[0;31m
BLUE = \033[0;34m
NC = \033[0m

help: ## Mostrar esta ayuda
	@echo "$(GREEN)Transvega Animal - Comandos Disponibles (NATIVO)$(NC)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "$(GREEN)%-20s$(NC) %s\n", $$1, $$2}'

# =============================================================================
# INSTALACIÓN Y CONFIGURACIÓN
# =============================================================================

install: ## Instalación completa nativa (requiere root)
	@echo "$(GREEN)=== Instalación Nativa Transvega ===$(NC)"
	@sudo $(SCRIPTS_DIR)/install.sh

install-deps: ## Solo dependencias base del sistema
	@sudo $(SCRIPTS_DIR)/install/dependencies.sh

install-db: ## Solo bases de datos (MariaDB, PostgreSQL, Redis)
	@sudo $(SCRIPTS_DIR)/install/mariadb.sh
	@sudo $(SCRIPTS_DIR)/install/postgresql.sh
	@sudo $(SCRIPTS_DIR)/install/redis.sh

install-php: ## Solo PHP + Apache
	@sudo $(SCRIPTS_DIR)/install/php.sh
	@sudo $(SCRIPTS_DIR)/install/apache.sh

install-dolibarr: ## Solo Dolibarr 23.0.4
	@sudo $(SCRIPTS_DIR)/install/dolibarr.sh

install-ollama: ## Solo Ollama nativo
	@sudo $(SCRIPTS_DIR)/install/ollama.sh

install-cloudflare: ## Solo Cloudflare Tunnel
	@sudo $(SCRIPTS_DIR)/install/cloudflare.sh

install-python: ## Solo Python virtualenv + dependencias
	@$(SCRIPTS_DIR)/install/python.sh

install-hermes: ## Solo Hermes (API + Worker + Approvals)
	@$(SCRIPTS_DIR)/install/hermes.sh

configure: ## Configuración post-instalación (requiere root)
	@echo "$(GREEN)=== Configuración Post-Instalación ===$(NC)"
	@sudo $(SCRIPTS_DIR)/configure.sh

configure-apache: ## Configurar Apache VirtualHost Dolibarr
	@sudo $(SCRIPTS_DIR)/configure/apache.sh

configure-dolibarr: ## Verificar/regenerar conf.php Dolibarr
	@sudo $(SCRIPTS_DIR)/configure/dolibarr.sh

configure-cloudflare: ## Configurar Cloudflare Tunnel ingress
	@$(SCRIPTS_DIR)/configure/cloudflare.sh

configure-services: ## Instalar servicios systemd
	@sudo $(SCRIPTS_DIR)/configure/services.sh

configure-hermes: ## Configurar variables entorno para Hermes systemd
	@$(SCRIPTS_DIR)/configure/hermes.sh

# =============================================================================
# GESTIÓN DE SERVICIOS
# =============================================================================

start: ## Iniciar todos los servicios (requiere root)
	@echo "$(GREEN)=== Iniciando Servicios ===$(NC)"
	@sudo $(SCRIPTS_DIR)/services/start.sh

stop: ## Detener todos los servicios (requiere root)
	@echo "$(YELLOW)=== Deteniendo Servicios ===$(NC)"
	@sudo $(SCRIPTS_DIR)/services/stop.sh

restart: ## Reiniciar todos los servicios (requiere root)
	@echo "$(BLUE)=== Reiniciando Servicios ===$(NC)"
	@sudo $(SCRIPTS_DIR)/services/restart.sh

status: ## Ver estado de todos los servicios con health checks
	@echo "$(GREEN)=== Estado Servicios Transvega ===$(NC)"
	@$(SCRIPTS_DIR)/services/status.sh

# =============================================================================
# VERIFICACIÓN Y DIAGNÓSTICO
# =============================================================================

check: ## Verificación profunda del entorno
	@echo "$(GREEN)=== Verificación Profunda ===$(NC)"
	@$(SCRIPTS_DIR)/check.sh

check-dolibarr: ## Healthcheck granular Dolibarr
	@$(SCRIPTS_DIR)/dolibarr-health.sh

check-apache: ## Verificar configuración Apache
	@sudo apache2ctl configtest

# =============================================================================
# BACKUP Y RESTAURACIÓN
# =============================================================================

backup: ## Backup completo (MariaDB + PostgreSQL + Redis + config)
	@echo "$(GREEN)=== Backup Completo ===$(NC)"
	@sudo $(SCRIPTS_DIR)/backup/database.sh

restore: ## Restaurar backup (especificar BACKUP_FILE=archivo.tar.gz)
	@if [ -z "$(BACKUP_FILE)" ]; then echo "$(RED)Especificar BACKUP_FILE=archivo.tar.gz$(NC)"; exit 1; fi
	@sudo $(SCRIPTS_DIR)/backup/restore.sh $(BACKUP_FILE)

# =============================================================================
# TESTING Y CALIDAD
# =============================================================================

test: test-unit test-integration ## Ejecutar todos los tests

test-unit: ## Tests unitarios (requiere .venv activado)
	@echo "$(GREEN)=== Tests Unitarios ===$(NC)"
	@source $(PROJECT_ROOT)/activate.sh && PYTHONPATH=$(PROJECT_ROOT):$(PROJECT_ROOT)/services/integration-api python -m pytest tests/unit -v --tb=short

test-integration: ## Tests de integración (requiere BD nativas corriendo)
	@echo "$(GREEN)=== Tests Integración ===$(NC)"
	@source $(PROJECT_ROOT)/activate.sh && PYTHONPATH=$(PROJECT_ROOT):$(PROJECT_ROOT)/services/integration-api python -m pytest tests/integration -v --tb=short --asyncio-mode=auto

test-cov: ## Tests con cobertura
	@source $(PROJECT_ROOT)/activate.sh && PYTHONPATH=$(PROJECT_ROOT):$(PROJECT_ROOT)/services/integration-api python -m pytest tests/ --cov=app --cov-report=term-missing --cov-report=html

lint: ## Linting con ruff
	@source $(PROJECT_ROOT)/activate.sh && ruff check $(PROJECT_ROOT)/services/integration-api/app $(PROJECT_ROOT)/tests/

format: ## Formateo con ruff
	@source $(PROJECT_ROOT)/activate.sh && ruff format $(PROJECT_ROOT)/services/integration-api/app $(PROJECT_ROOT)/tests/

type-check: ## Verificación de tipos con mypy
	@source $(PROJECT_ROOT)/activate.sh && mypy $(PROJECT_ROOT)/services/integration-api/app

pre-commit: lint format type-check ## Ejecutar todos los checks pre-commit

# =============================================================================
# UTILIDADES
# =============================================================================

shell: ## Activar virtualenv Transvega (ejecutar: source activate.sh && make shell)
	@echo "Ejecuta: source $(PROJECT_ROOT)/activate.sh"

logs-hermes: ## Ver logs Hermes API
	@journalctl -u hermes -f

logs-worker: ## Ver logs Hermes Worker
	@journalctl -u hermes-worker -f

logs-approvals: ## Ver logs Approvals
	@journalctl -u approvals -f

logs-apache: ## Ver logs Apache Dolibarr
	@sudo tail -f /var/log/apache2/transvega-dolibarr-error.log /var/log/apache2/transvega-dolibarr-access.log

logs-ollama: ## Ver logs Ollama
	@journalctl -u ollama -f

logs-cloudflare: ## Ver logs Cloudflare Tunnel
	@journalctl -u cloudflared -f

# =============================================================================
# LIMPIEZA (SEGURA - NO DESTRUCTIVA)
# =============================================================================

clean: ## Limpiar archivos temporales y cache (NO borra BD ni datos)
	@echo "$(YELLOW)=== Limpieza Segura ===$(NC)"
	@find $(PROJECT_ROOT) -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find $(PROJECT_ROOT) -type f -name "*.pyc" -delete 2>/dev/null || true
	@find $(PROJECT_ROOT) -type f -name "*.pyo" -delete 2>/dev/null || true
	@find $(PROJECT_ROOT) -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find $(PROJECT_ROOT) -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	@find $(PROJECT_ROOT) -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	@find $(PROJECT_ROOT) -type f -name ".coverage" -delete 2>/dev/null || true
	@rm -rf $(PROJECT_ROOT)/htmlcov 2>/dev/null || true
	@rm -rf $(PROJECT_ROOT)/.coverage 2>/dev/null || true
	@echo "$(GREEN)✅ Limpieza completada$(NC)"

clean-logs: ## Limpiar logs systemd (requiere root)
	@sudo journalctl --vacuum-time=7d

# =============================================================================
# DESARROLLO
# =============================================================================

dev-install: install-python install-hermes ## Instalación solo desarrollo (sin BD ni Apache)

dev-start: ## Iniciar solo servicios app (Hermes + Worker + Approvals) - requiere BD corriendo
	@echo "$(GREEN)=== Iniciando Servicios App ===$(NC)"
	@sudo systemctl start hermes hermes-worker approvals

dev-stop: ## Detener solo servicios app
	@echo "$(YELLOW)=== Deteniendo Servicios App ===$(NC)"
	@sudo systemctl stop hermes hermes-worker approvals

dev-restart: ## Reiniciar solo servicios app
	@echo "$(BLUE)=== Reiniciando Servicios App ===$(NC)"
	@sudo systemctl restart hermes hermes-worker approvals

# =============================================================================
# DOCKER (SOLO PARA TESTS/CI - NO PRODUCCIÓN)
# =============================================================================

docker-test-up: ## Levantar PostgreSQL/Redis de test en puertos 55432/56379
	@docker compose -f docker-compose.test.yml --env-file .env.test up -d

docker-test-down: ## Bajar servicios de test
	@docker compose -f docker-compose.test.yml --env-file .env.test down -v

docker-mock-up: ## Levantar Mock Dolibarr para tests
	@docker compose -f docker-compose.test.yml --env-file .env.test up -d mock-dolibarr

# =============================================================================
# COMANDO POR DEFECTO
# =============================================================================

.DEFAULT_GOAL := help