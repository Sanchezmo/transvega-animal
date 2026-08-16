# Makefile - Transvega Animal
# Comandos de desarrollo, testing, despliegue y mantenimiento

.PHONY: help up down restart logs status shell-api shell-worker shell-db shell-redis shell-mock shell-approvals test test-unit test-integration test-security test-e2e test-cov lint format type-check security-scan pre-commit seed seed-clean reset-db backup backup-full restore verify-backup staging-up staging-down staging-restart staging-status staging-config staging-logs staging-logs-api staging-logs-cloudflare staging-logs-dolibarr staging-logs-redis staging-logs-db staging-health telegram-webhook-configure telegram-webhook-status staging-first-run deploy-staging deploy-prod rotate-secrets verify-secrets audit-permissions clean clean-all docs-serve docs-build metrics grafana alerts

# Variables
COMPOSE_FILE = docker-compose.dev.yml
COMPOSE_STAGING = docker-compose.staging.yml
COMPOSE_PROD = docker-compose.prod.yml
ENV_FILE = .env.local

# Colores para output
GREEN = \033[0;32m
YELLOW = \033[1;33m
RED = \033[0;31m
NC = \033[0m

help: ## Mostrar esta ayuda
	@echo "$(GREEN)Transvega Animal - Comandos disponibles$(NC)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "$(GREEN)%-28s$(NC) %s\n", $$1, $$2}'

# =============================================================================
# DESARROLLO LOCAL
# =============================================================================

up: ## Levantar entorno de desarrollo completo
	@echo "$(GREEN)Levantando entorno de desarrollo...$(NC)"
	@docker compose -f $(COMPOSE_FILE) --env-file $(ENV_FILE) up -d --build
	@echo "$(GREEN)Esperando health checks...$(NC)"
	@sleep 10
	@make status

up-minimal: ## Levantar solo servicios esenciales (api, db, redis, approvals, mock-dolibarr)
	@echo "$(GREEN)Levantando servicios mínimos...$(NC)"
	@docker compose -f $(COMPOSE_FILE) --env-file $(ENV_FILE) up -d --build api audit-db redis approvals mock-dolibarr
	@sleep 5
	@make status

down: ## Parar entorno de desarrollo
	@echo "$(YELLOW)Parando entorno...$(NC)"
	@docker compose -f $(COMPOSE_FILE) down

restart: ## Reiniciar servicios
	@make down
	@make up

logs: ## Ver logs de todos los servicios
	@docker compose -f $(COMPOSE_FILE) logs -f --tail=100

logs-api: ## Ver logs solo de la API
	@docker compose -f $(COMPOSE_FILE) logs -f api --tail=100

logs-worker: ## Ver logs solo del worker
	@docker compose -f $(COMPOSE_FILE) logs -f worker --tail=100

logs-approvals: ## Ver logs solo del servicio aprobaciones
	@docker compose -f $(COMPOSE_FILE) logs -f approvals --tail=100

logs-db: ## Ver logs de base de datos auditoría
	@docker compose -f $(COMPOSE_FILE) logs -f audit-db --tail=100

logs-mock: ## Ver logs de mock Dolibarr
	@docker compose -f $(COMPOSE_FILE) logs -f mock-dolibarr --tail=100

status: ## Ver estado de todos los contenedores
	@echo "$(GREEN)Estado de contenedores:$(NC)"
	@docker compose -f $(COMPOSE_FILE) ps
	@echo ""
	@echo "$(GREEN)Health checks:$(NC)"
	@docker compose -f $(COMPOSE_FILE) ps --format "table {{.Name}}	{{.Status}}	{{.Ports}}"

# =============================================================================
# SHELLS Y DEBUG
# =============================================================================

shell-api: ## Shell en contenedor API
	@docker compose -f $(COMPOSE_FILE) exec api bash

shell-worker: ## Shell en contenedor Worker
	@docker compose -f $(COMPOSE_FILE) exec worker bash

shell-db: ## Shell en PostgreSQL auditoría
	@docker compose -f $(COMPOSE_FILE) exec audit-db psql -U audit -d audit

shell-redis: ## Shell en Redis
	@docker compose -f $(COMPOSE_FILE) exec redis redis-cli -a $$REDIS_PASSWORD

shell-mock: ## Shell en Mock Dolibarr
	@docker compose -f $(COMPOSE_FILE) exec mock-dolibarr bash

shell-approvals: ## Shell en servicio aprobaciones
	@docker compose -f $(COMPOSE_FILE) exec approvals bash

# =============================================================================
# TESTING
# =============================================================================

test: test-unit test-integration test-security ## Ejecutar todos los tests

test-unit: ## Tests unitarios
	@echo "$(GREEN)Ejecutando tests unitarios...$(NC)"
	@docker compose -f $(COMPOSE_FILE) exec -T -e PYTHONPATH=/app api pytest tests/unit -v --tb=short

test-integration: ## Tests de integración
	@echo "$(GREEN)Ejecutando tests de integración...$(NC)"
	@docker compose -f $(COMPOSE_FILE) exec -T -e PYTHONPATH=/app api pytest tests/integration -v --tb=short

test-security: ## Tests de seguridad
	@echo "$(GREEN)Ejecutando tests de seguridad...$(NC)"
	@docker compose -f $(COMPOSE_FILE) exec -T -e PYTHONPATH=/app api pytest tests/security_tests.py -v --tb=short

test-e2e: ## Tests end-to-end
	@echo "$(GREEN)Ejecutando tests E2E...$(NC)"
	@docker compose -f $(COMPOSE_FILE) exec -T -e PYTHONPATH=/app api pytest tests/e2e_tests.py -v --tb=short

test-cov: ## Tests con cobertura
	@docker compose -f $(COMPOSE_FILE) exec -T api pytest tests/ --cov=app --cov-report=term-missing --cov-report=html

# =============================================================================
# CALIDAD DE CÓDIGO
# =============================================================================

lint: ## Linting con ruff
	@echo "$(GREEN)Ejecutando linting...$(NC)"
	@docker compose -f $(COMPOSE_FILE) exec -T api ruff check .

format: ## Formateo con ruff
	@echo "$(GREEN)Formateando código...$(NC)"
	@docker compose -f $(COMPOSE_FILE) exec -T api ruff format .

type-check: ## Verificación de tipos con mypy
	@echo "$(GREEN)Verificando tipos...$(NC)"
	@docker compose -f $(COMPOSE_FILE) exec -T api mypy .

security-scan: ## Escaneo de seguridad con bandit
	@echo "$(GREEN)Escaneando seguridad...$(NC)"
	@docker compose -f $(COMPOSE_FILE) exec -T api bandit -r . -f json -o bandit-report.json || true

pre-commit: lint format type-check ## Ejecutar todos los checks pre-commit

# =============================================================================
# DATOS Y SEEDING
# =============================================================================

seed: ## Sembrar datos ficticios de prueba
	@echo "$(GREEN)Sembrando datos de prueba...$(NC)"
	@docker compose -f $(COMPOSE_FILE) exec -T api python scripts/seed_fake_data.py

seed-clean: ## Limpiar y resembrar datos
	@echo "$(YELLOW)Limpiando y resembrando...$(NC)"
	@docker compose -f $(COMPOSE_FILE) exec -T audit-db psql -U audit -d audit -c "TRUNCATE TABLE audit_log, approval_requests, task_queue CASCADE;"
	@make seed

reset-db: ## Resetear base de datos auditoría completamente
	@echo "$(RED)RESETEANDO BASE DE DATOS AUDITORÍA$(NC)"
	@docker compose -f $(COMPOSE_FILE) down -v audit-db
	@docker compose -f $(COMPOSE_FILE) up -d audit-db
	@sleep 5
	@make seed

# =============================================================================
# BACKUP Y RESTAURACIÓN
# =============================================================================

backup: ## Backup de base de datos auditoría
	@echo "$(GREEN)Creando backup auditoría...$(NC)"
	@mkdir -p backups
	@docker compose -f $(COMPOSE_FILE) exec -T audit-db pg_dump -U audit audit | gzip > backups/audit_$(shell date +%Y%m%d_%H%M%S).sql.gz
	@echo "$(GREEN)Backup guardado en backups/$(NC)"

backup-full: ## Backup completo (auditoría + Redis + config)
	@echo "$(GREEN)Backup completo...$(NC)"
	@mkdir -p backups/full_$(shell date +%Y%m%d_%H%M%S)
	@make backup
	@docker compose -f $(COMPOSE_FILE) exec -T redis redis-cli -a $$REDIS_PASSWORD --rdb /data/dump.rdb
	@docker cp $$(docker compose -f $(COMPOSE_FILE) ps -q redis):/data/dump.rdb backups/full_$(shell date +%Y%m%d_%H%M%S)/redis.rdb
	@cp -r config backups/full_$(shell date +%Y%m%d_%H%M%S)/
	@cp .env.local backups/full_$(shell date +%Y%m%d_%H%M%S)/.env.local.bak

restore: ## Restaurar backup auditoría (especificar BACKUP_FILE=archivo)
	@if [ -z "$(BACKUP_FILE)" ]; then echo "$(RED)Especificar BACKUP_FILE=archivo.sql.gz$(NC)"; exit 1; fi
	@echo "$(YELLOW)Restaurando $(BACKUP_FILE)...$(NC)"
	@gunzip -c $(BACKUP_FILE) | docker compose -f $(COMPOSE_FILE) exec -T audit-db psql -U audit -d audit
	@echo "$(GREEN)Restauración completada$(NC)"

verify-backup: ## Verificar integridad de backups
	@echo "$(GREEN)Verificando backups...$(NC)"
	@ls -la backups/
	@for f in backups/*.sql.gz; do echo "Verificando $$f..."; gunzip -t $$f && echo "OK" || echo "CORRUPTO"; done

# =============================================================================
# STAGING LOCAL
# =============================================================================

staging-check-env: ## Verificar que existe .env.staging
	@if [ ! -f .env.staging ]; then \
		echo "$(RED)ERROR: .env.staging not found.$(NC)"; \
		echo "Copy .env.staging.example to .env.staging and configure secrets."; \
		exit 1; \
	fi

staging-up: staging-check-env ## Levantar staging local (usa docker-compose.staging.yml + .env.staging)
	@./scripts/staging-up.sh

staging-down: staging-check-env ## Parar staging local
	@docker compose --env-file .env.staging -f docker-compose.staging.yml down

staging-restart: staging-check-env ## Reiniciar staging local
	@$(MAKE) staging-down
	@$(MAKE) staging-up

staging-status: staging-check-env ## Ver estado de servicios staging
	@./scripts/staging-status.sh

staging-config: staging-check-env ## Validar configuración docker-compose staging
	@docker compose --env-file .env.staging -f docker-compose.staging.yml config

staging-logs: staging-check-env ## Ver logs completos staging
	@docker compose --env-file .env.staging -f docker-compose.staging.yml logs -f --tail=100

staging-logs-api: staging-check-env ## Ver logs API staging
	@docker compose --env-file .env.staging -f docker-compose.staging.yml logs -f api --tail=100

staging-logs-cloudflare: staging-check-env ## Ver logs Cloudflare Tunnel staging
	@docker compose --env-file .env.staging -f docker-compose.staging.yml logs -f cloudflared --tail=100

staging-logs-dolibarr: staging-check-env ## Ver logs Dolibarr staging
	@docker compose --env-file .env.staging -f docker-compose.staging.yml logs -f dolibarr --tail=100

staging-logs-redis: staging-check-env ## Ver logs Redis staging
	@docker compose --env-file .env.staging -f docker-compose.staging.yml logs -f redis --tail=100

staging-logs-db: staging-check-env ## Ver logs DB auditoría staging
	@docker compose --env-file .env.staging -f docker-compose.staging.yml logs -f audit-db --tail=100

staging-health: staging-check-env ## Comprobar health/readiness endpoints staging
	@echo "$(GREEN)Comprobando health endpoints en staging...$(NC)"
	@API_PORT=$$(docker compose --env-file .env.staging -f docker-compose.staging.yml port api 8000 2>/dev/null | cut -d: -f2); \
	if [ -z "$$API_PORT" ]; then \
		echo "$(RED)ERROR: No se pudo obtener puerto de API$(NC)"; \
		exit 1; \
	fi; \
	echo "API puerto local: $$API_PORT"; \
	if curl -fsS "http://localhost:$$API_PORT/health" >/dev/null; then \
		echo "$(GREEN)✓ /health OK$(NC)"; \
	else \
		echo "$(RED)✗ /health FAIL$(NC)"; \
		exit 1; \
	fi; \
	if curl -fsS "http://localhost:$$API_PORT/health/ready" >/dev/null; then \
		echo "$(GREEN)✓ /health/ready OK$(NC)"; \
	else \
		echo "$(RED)✗ /health/ready FAIL$(NC)"; \
		exit 1; \
	fi

telegram-webhook-configure: staging-check-env ## Configurar webhook Telegram para staging
	@./scripts/configure-telegram-webhook.sh

telegram-webhook-status: staging-check-env ## Ver estado webhook Telegram
	@./scripts/check-telegram-webhook.sh

staging-first-run: staging-config staging-up staging-status staging-health ## Primera validación completa de staging local

# =============================================================================
# DESPLIEGUE STAGING / PROD (VPS)
# =============================================================================

deploy-staging: ## Desplegar a staging (requiere VPS configurado)
	@echo "$(GREEN)Desplegando a staging...$(NC)"
	@./scripts/deploy-staging.sh

deploy-prod: ## Desplegar a producción (requiere confirmación)
	@echo "$(RED)DESPLIEGUE A PRODUCCIÓN - ¿Estás seguro? (y/N)$(NC)"
	@read -r confirm && [ "$$confirm" = "y" ] || exit 1
	@./scripts/deploy-prod.sh

# =============================================================================
# SECRETOS Y SEGURIDAD
# =============================================================================

rotate-secrets: ## Rotar secretos (ejecutar cada 90 días)
	@echo "$(GREEN)Rotando secretos...$(NC)"
	@./scripts/rotate-secrets.sh

verify-secrets: ## Verificar que no hay secretos en repo
	@echo "$(GREEN)Verificando secretos...$(NC)"
	@git secrets --scan || true
	@trufflehog git file://. --only-verified || true

audit-permissions: ## Auditar permisos de archivos sensibles
	@echo "$(GREEN)Auditoria de permisos...$(NC)"
	@find . -name "*.env*" -o -name "*.pem" -o -name "*.key" | xargs ls -la

# =============================================================================
# LIMPIEZA
# =============================================================================

clean: ## Limpiar contenedores, volúmenes y redes no usados
	@echo "$(YELLOW)Limpiando recursos Docker...$(NC)"
	@docker system prune -f --volumes

clean-all: ## Limpieza completa (CUIDADO: borra todo)
	@echo "$(RED)LIMPIEZA COMPLETA - ¿Seguro? (y/N)$(NC)"
	@read -r confirm && [ "$$confirm" = "y" ] || exit 1
	@docker compose -f $(COMPOSE_FILE) down -v --rmi all
	@docker system prune -af --volumes
	@rm -rf backups/* logs/* tmp/*

# =============================================================================
# DOCUMENTACIÓN
# =============================================================================

docs-serve: ## Servir documentación localmente
	@echo "$(GREEN)Sirviendo docs en http://localhost:8080$(NC)"
	@docker run --rm -p 8080:80 -v $(PWD)/docs:/usr/share/nginx/html:ro nginx:alpine

docs-build: ## Generar documentación estática
	@echo "$(GREEN)Generando docs...$(NC)"
	@mkdir -p docs/_build
	@pandoc docs/*.md -o docs/_build/transvega-animal.pdf --toc --pdf-engine=weasyprint || true

# =============================================================================
# MONITORIZACIÓN
# =============================================================================

metrics: ## Ver métricas Prometheus
	@echo "$(GREEN)Métricas en http://localhost:9090$(NC)"

grafana: ## Abrir Grafana
	@echo "$(GREEN)Grafana en http://localhost:3001$(NC)"

alerts: ## Ver Alertmanager
	@echo "$(GREEN)Alertmanager en http://localhost:9093$(NC)"

# =============================================================================
# COMANDOS POR DEFECTO
# =============================================================================

.DEFAULT_GOAL := help