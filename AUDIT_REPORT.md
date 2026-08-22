# AUDITORÍA COMPLETA - Transvega Animal
## Refactorización Infraestructura: Docker → Nativo (Kali/Debian)
**Fecha**: 2026-08-22  
**Objetivo**: Migrar progresivamente a arquitectura nativa sin romper funcionalidades existentes

---

## 1. ARQUITECTURA INICIAL ENCONTRADA

### 1.1 Servicios Docker Actuales

| Servicio | Compose Files | Puerto(s) | Estado | Dependencias |
|----------|---------------|-----------|--------|--------------|
| **postgres (Hermes)** | `docker-compose.yml` | 5432 (bind) | ACTIVO | - |
| **redis** | `docker-compose.yml`, `.dev.yml`, `.staging.yml`, `.prod.yml` | 6379 | ACTIVO | - |
| **ollama** | Todos | 11434 (interno) | ACTIVO | - |
| **hermes (API principal)** | `docker-compose.yml` | 8000 | ACTIVO | postgres, redis, ollama |
| **invoice_worker** | `docker-compose.yml` | - | ACTIVO | redis |
| **audit-db** | `.dev.yml`, `.staging.yml`, `.prod.yml` | 5432/5433/55432 | ACTIVO | - |
| **mock-dolibarr** | `.dev.yml`, `.test.yml` | 8001 | ACTIVO (solo dev/test) | - |
| **api (integración)** | `.dev.yml`, `.staging.yml`, `.prod.yml` | 8000/8010 | ACTIVO | audit-db, redis, ollama, Dolibarr nativo |
| **worker (Celery)** | `.dev.yml`, `.staging.yml`, `.prod.yml` | - | ACTIVO | redis, audit-db, api, ollama |
| **approvals** | `.dev.yml`, `.staging.yml`, `.prod.yml` | 8002/8012 | ACTIVO | audit-db, redis |
| **dashboard** | `.staging.yml`, `.prod.yml` | 3000/3010 | ACTIVO | api, approvals |
| **cloudflared** | `.staging.yml`, `.prod.yml` | - | ACTIVO | api, approvals, dashboard |

### 1.2 Servicios Nativos Ya Existentes
| Servicio | Ubicación | Estado |
|----------|-----------|--------|
| **Apache2** | Host (systemd) | ✅ CORRIENDO (puerto 80) |
| **Dolibarr 23.0.4** | `/home/saulo/transvega-animal/dolibarr-23.0.4/htdocs` | ✅ COPIADO MANUALMENTE |
| **MariaDB** | Host (systemd) | ❌ NO INSTALADO (requerido por Dolibarr) |
| **cloudflared** | Host (systemd) | ❌ SOLO EN DOCKER |

### 1.3 Estructura de Directorios Críticos
```
/home/saulo/transvega-animal/
├── dolibarr-23.0.4/          # NUEVO - Dolibarr 23.0.4 copiado manualmente (versionado en Git)
├── dolibarr/                 # VIEJO - Referenciado en scripts (20.0.4), ya no existe
├── postgres_data/            # Bind mount postgres (Hermes)
├── redis_data/               # Bind mount redis
├── ollama_data/              # Bind mount ollama
├── hermes_data/              # Bind mount hermes
├── hermes_logs/              # Bind mount hermes logs
├── invoice_worker_logs/      # Bind mount worker logs
├── services/
│   ├── integration-api/      # FastAPI principal (puerto 8000)
│   ├── approval-service/     # Servicio aprobaciones (puerto 8002)
│   ├── task-queue/           # Celery worker tasks
│   ├── audit-service/        # Auditoría
│   └── dashboard/            # Dashboard interno
├── adapters/
│   └── dolibarr/             # Cliente Dolibarr + Mock
├── infrastructure/
│   └── docker/               # 5 Dockerfiles + init-audit-db.sql
└── scripts/                  # 20+ scripts bash/python
```

---

## 2. MAPA DE DEPENDENCIAS DETALLADO

### 2.1 Base de Datos PostgreSQL (audit-db)
**Función**: Auditoría inmutable + aprobaciones + task queue + agent sessions  
**Quién la usa**:
- `services/integration-api` (FastAPI) → `app/core/database.py` → `audit_log`, `approval_requests`, `task_queue`, `agent_sessions`
- `services/approval-service` → `app.py` (en memoria, pero schema existe en `init-audit-db.sql`)
- `services/task-queue` → `celery_app.py` (usa `AUDIT_DB_URL` para beat schedule)

**Datos almacenados**:
- `audit_log`: Registro inmutable de todas las operaciones (request/response, trazabilidad)
- `approval_requests`: Solicitudes de aprobación humana para acciones sensibles
- `task_queue`: Cola de tareas asíncronas (expedientes, publicaciones, facturación, notificaciones)
- `agent_sessions`: JWT refresh tokens

**Persistencia**: Volumen Docker `audit-db-data` (dev/staging/prod) o bind mount `./postgres_data` (compose.yml base)

**Migración nativa**: **TRIVIAL** - PostgreSQL nativo en Debian/Kali es estándar. Solo requiere:
- Instalar `postgresql-16` (o versión Kali)
- Crear DB `audit`, usuario `audit`, ejecutar `init-audit-db.sql`
- Actualizar variables `.env`: `AUDIT_DB_HOST=127.0.0.1`, `AUDIT_DB_PORT=5432`

**RIESGO**: **BAJO** - Servicio estándar, sin dependencias de código específicas de Docker.

---

### 2.2 Redis
**Función**: Celery broker/result backend + cache + idempotency + sessions  
**Quién la usa**:
- `services/integration-api` → `app/core/database.py` (`get_redis`, `get_redis_client`)
- `services/task-queue` → `celery_app.py` (`CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`)
- `services/approval-service` → `app.py` (`APPROVALS_REDIS_URL`)
- Workers Celery (facturación, expedientes, publicaciones, notificaciones)

**Datos almacenados**:
- Colas Celery: `high`, `default`, `low`, `approvals`, `notifications`
- Resultados de tareas (TTL 1h, comprimidos gzip)
- Idempotency keys (Telegram updates, API calls)
- Rate limiting counters
- Cache temporal

**Persistencia**: Volumen Docker `redis-data` (RDB/AOF)

**Migración nativa**: **TRIVIAL** - Redis nativo en Debian/Kali es estándar. Solo requiere:
- Instalar `redis-server`
- Configurar `requirepass`, `maxmemory`, `maxmemory-policy` en `/etc/redis/redis.conf`
- Actualizar variables `.env`: `REDIS_HOST=127.0.0.1`, `REDIS_PORT=6379`

**RIESGO**: **BAJO** - Servicio estándar. Atención: `maxmemory 512mb` en dev, `1gb` en prod.

---

### 2.3 Ollama
**Función**: LLM local para procesamiento de facturas (LOCAL_ONLY - datos sensibles)  
**Quién la usa**:
- `services/integration-api` → `OLLAMA_ENDPOINT=http://ollama:11434` (Docker) / `http://127.0.0.1:11434` (nativo)
- Workers Celery (facturación) → mismo endpoint
- `scripts/ollama-entrypoint.sh` → Crea modelo `transvega-local` desde `qwen3.5:4b-q4_K_M` usando Modelfile

**Modelo**: `transvega-local` (multimodal, creado al arrancar)

**Persistencia**: Volumen Docker `ollama-data` (`/root/.ollama`)

**Migración nativa**: **TRIVIAL** - Ollama tiene instalador nativo y systemd service. Requiere:
- Instalar Ollama nativo (`curl -fsSL https://ollama.com/install.sh | sh`)
- Servicio systemd `ollama.service` (ya incluido en instalador)
- Crear modelo `transvega-local` una vez (persistente en `~/.ollama`)
- Actualizar variable: `OLLAMA_ENDPOINT=http://127.0.0.1:11434`

**RIESGO**: **BAJO** - Servicio independiente. Modelo se persiste en filesystem.

---

### 2.4 API Integración (FastAPI) - `services/integration-api`
**Función**: Punto central de integración - única vía de acceso a Dolibarr  
**Puertos**: 8000 (dev), 8010 (staging), interno (prod)  
**Dependencias**: PostgreSQL (audit-db), Redis, Ollama, Dolibarr REST API  
**Entry point**: `app/main.py` → `uvicorn app.main:app`  
**Configuración**: `app/core/config.py` (Pydantic Settings, env_file `.env.local`)

**Endpoints clave**:
- `/health`, `/health/ready` - Health checks
- `/api/v1/expedientes`, `/terceros`, `/productos`, `/dogs`, `/publicaciones`, `/comercial`, `/facturacion`, `/aprobaciones`, `/proveedores`, `/telegram`
- Webhook Telegram: `/api/v1/telegram/webhook`

**Inicialización (lifespan)**:
1. `init_db()` - Crea tablas auditoría
2. Redis client
3. Supervisor agent (para Telegram webhook)

**Migración nativa**: **MEDIA** - Requiere:
- Python 3.11+ virtualenv (`.venv`)
- Instalar dependencias (`services/integration-api/requirements.txt`)
- Configurar `PYTHONPATH` para imports (`adapters/`, `agents/`, `services/task-queue/`)
- Service systemd `hermes.service` con `WorkingDirectory`, `EnvironmentFile=.env`
- Verificar imports funcionan fuera de Docker (paths relativos)

**RIESGO**: **MEDIO** - Complejidad de imports y PYTHONPATH. El código usa `sys.path.insert(0, "/app")` en Docker.

---

### 2.5 Worker Celery - `services/task-queue`
**Función**: Procesamiento background (facturas, expedientes, publicaciones, notificaciones)  
**Dependencias**: Redis (broker), PostgreSQL (audit-db), Ollama, API interna  
**Entry point**: `celery -A tasks.celery_app worker`  
**Colas**: `high`, `default`, `low`, `approvals`, `notifications`  
**Beat schedule**: 7 tareas periódicas (cada hora/diario/semanal)

**Tasks**:
- `expedientes`: verificar vencidos, limpiar antiguas, renovar publicaciones
- `facturacion`: generar periódicas, detectar vencidas
- `notificaciones`: reporte diario

**Playwright**: Instalado en Dockerfile.worker para automatización navegador

**Migración nativa**: **MEDIA-ALTA** - Requiere:
- Mismo virtualenv que API
- Playwright nativo (`playwright install chromium --with-deps`)
- Service systemd `hermes-worker.service`
- Verificar que `celery_app.py` encuentra settings correctamente fuera de Docker

**RIESGO**: **MEDIO-ALTO** - Playwright y paths de tasks. El Dockerfile copia código a `/app/tasks/`.

---

### 2.6 Servicio Aprobaciones - `services/approval-service`
**Función**: Aprobación humana para acciones sensibles (publicar, precios, facturas, impuestos, pagos, etc.)  
**Puerto**: 8002 (dev), 8012 (staging)  
**Dependencias**: PostgreSQL (audit-db), Redis, Webhook notificaciones  
**Entry point**: `uvicorn app.main:app` (tiene su propio `app.py` y `alembic`)  
**Estado actual**: **EN MEMORIA** (dict `self.approvals`), pero schema SQL existe en `init-audit-db.sql`

**Migración nativa**: **BAJA** - Servicio Python simple. Requiere:
- Virtualenv compartido o propio
- Service systemd `approvals.service`
- Migrar de dict en memoria a PostgreSQL (ya tiene schema)

**RIESGO**: **BAJO** - Código simple, sin dependencias complejas.

---

### 2.7 Dashboard - `services/dashboard`
**Función**: Panel interno (React/Node.js)  
**Puerto**: 3000 (staging), interno (prod)  
**Dependencias**: API, Aprobaciones  
**Dockerfile**: `Dockerfile.dashboard` (Node.js 20)

**Migración nativa**: **BAJA** - Node.js nativo + systemd. O mantener en Docker si no aporta valor migrarlo.

---

### 2.8 Mock Dolibarr - `adapters/dolibarr/mock.py`
**Función**: Simulador API Dolibarr para desarrollo/tests  
**Puerto**: 8001 (dev), 56379 (test)  
**Uso**: Tests unitarios/integración, desarrollo sin Dolibarr real  
**Fixtures**: `tests/fixtures/dolibarr/`

**Decisión**: **MANTENER EN DOCKER SOLO PARA TESTS/CI** - No levantar en `make start` nativo.

---

### 2.9 Dolibarr Real (Nativo) - `dolibarr-23.0.4/htdocs`
**Función**: ERP/CRM oficial - fuente de verdad  
**Versión**: 23.0.4 (copiado manualmente, versionado en Git)  
**Base de datos**: **MariaDB** (requerido)  
**Servidor web**: **Apache2** (ya corriendo nativo en puerto 80, necesita vhost en 8080)  
**API REST**: `/api/index.php`  
**Directorio documents**: `dolibarr-23.0.4/documents/` (protegido, no servido directo)

**Scripts existentes**:
- `scripts/install-dolibarr.sh` - Instalador idempotente (v20.0.4, necesita actualizar a 23.0.4)
- `scripts/configure-apache-dolibarr.sh` - VirtualHost Apache puerto 8080
- `scripts/dolibarr-health.sh` - Healthcheck granular (Apache, Dolibarr, MariaDB, REST API, Documents, Cloudflare)
- `scripts/backup-dolibarr.sh` / `restore-dolibarr.sh` - Migración Docker → nativo

**Estado actual**: Apache corriendo en puerto 80. Falta:
1. MariaDB instalado y configurado
2. Dolibarr 23.0.4 instalado en `dolibarr/` (simlink o renombrar `dolibarr-23.0.4`)
3. `conf.php` generado con credenciales MariaDB
4. VirtualHost Apache en puerto 8080
5. API key Dolibarr configurada

**Migración nativa**: **EN PROGRESO** - Apache ya nativo. Falta MariaDB + Dolibarr instalado.

---

### 2.10 Cloudflare Tunnel
**Función**: Único punto de entrada externo (HTTPS → localhost)  
**Modo actual**: Docker (`cloudflare/cloudflared:latest`) con token  
**Script nativo**: `scripts/configure-cloudflare-dolibarr.sh` - Configura ingress via API Cloudflare  
**Túneles**:
- `dolibarr-staging.mascotalegal.es` → `http://localhost:8080`
- `hermes.transvega-animal.es` → API (staging/prod)
- Telegram webhook → API

**Migración nativa**: **BAJA** - `cloudflared` tiene binario nativo + systemd service. Requiere:
- Instalar `cloudflared` (`.deb` o binario)
- `cloudflared tunnel login` (manual, una vez)
- `cloudflared tunnel run --token $TOKEN` como systemd service
- Configurar ingress preservando reglas existentes (script ya lo hace)

**RIESGO**: **BAJO** - Binario nativo maduro.

---

### 2.11 MariaDB (NUEVO - Requerido para Dolibarr)
**Función**: Base de datos de Dolibarr 23.0.4  
**Estado**: **NO INSTALADO**  
**Requisitos Dolibarr 23.0.4**: MariaDB 10.6+ / MySQL 8.0+  
**Variables necesarias**: `DOLIBARR_DB_HOST`, `DOLIBARR_DB_PORT`, `DOLIBARR_DB_NAME`, `DOLIBARR_DB_USER`, `DOLIBARR_DB_PASSWORD`, `DOLIBARR_DB_ROOT_PASSWORD`

**Migración nativa**: **OBLIGATORIA** - Dolibarr NO funciona sin MariaDB/MySQL.

---

## 3. VARIABLES DE ENTORNO - CONSOLIDACIÓN NECESARIA

### 3.1 Variables Duplicadas/Confusas Detectadas

| Concepto | Variables Actuales | Consolidación Propuesta |
|----------|-------------------|------------------------|
| **Dolibarr API URL** | `DOLIBARR_API_URL`, `DOLIBARR_LOCAL_URL` | `DOLIBARR_API_URL` (local), `DOLIBARR_PUBLIC_URL` (Cloudflare) |
| **Dolibarr DB** | `DOLIBARR_DB_PASSWORD`, `DOLIBARR_DB_ROOT_PASSWORD` | Mantener ambas (user/root) |
| **PostgreSQL Audit** | `AUDIT_DB_HOST`, `AUDIT_DB_PORT`, `AUDIT_DB_NAME`, `AUDIT_DB_USER`, `AUDIT_DB_PASSWORD`, `AUDIT_DB_URL` | Mantener individuales + computed `AUDIT_DB_URL` |
| **Redis** | `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`, `REDIS_URL` | Mantener individuales + computed `REDIS_URL` |
| **Ollama** | `OLLAMA_HOST`, `OLLAMA_PORT`, `OLLAMA_ENDPOINT`, `OLLAMA_MODEL`, `OLLAMA_BASE_MODEL` | `OLLAMA_HOST=http://127.0.0.1`, `OLLAMA_PORT=11434`, `OLLAMA_MODEL` |
| **API Keys Agentes** | 15 variables individuales | Mantener (requeridas para arranque) |

### 3.2 Archivos .env Actuales
| Archivo | Propósito | Secretos Reales |
|---------|-----------|-----------------|
| `.env.example` | Template documentado | NO |
| `.env.local` | Desarrollo local | **SÍ** (Telegram, Cloudflare, NVIDIA, claves generadas) |
| `.env.staging` | Staging local | Placeholders |
| `.env.staging.example` | Template staging | NO |
| `.env.test` | Tests integración | Fixtures (no reales) |

---

## 4. PUERTOS UTILIZADOS

### 4.1 Puertos Expuestos (Host)
| Puerto | Servicio | Compose | Notas |
|--------|----------|---------|-------|
| 80 | Apache (default) | - | Ya corriendo |
| 8080 | Apache (Dolibarr vhost) | - | Script `configure-apache-dolibarr.sh` |
| 5432 | PostgreSQL (audit-db) | `.dev.yml` | Bind 0.0.0.0 |
| 5433 | PostgreSQL (audit-db staging) | `.staging.yml` | Bind 127.0.0.1 |
| 55432 | PostgreSQL (test) | `.test.yml` | Bind 127.0.0.1 |
| 6379 | Redis (dev) | `.dev.yml` | Bind 0.0.0.0 |
| 6380 | Redis (staging) | `.staging.yml` | Bind 127.0.0.1 |
| 56379 | Redis (test) | `.test.yml` | Bind 127.0.0.1 |
| 8000 | API Integración (dev) | `.dev.yml` | Bind 0.0.0.0 |
| 8001 | Mock Dolibarr (dev) | `.dev.yml` | Bind 0.0.0.0 |
| 8002 | Approvals (dev) | `.dev.yml` | Bind 0.0.0.0 |
| 8010 | API Integración (staging) | `.staging.yml` | Bind 127.0.0.1 |
| 8012 | Approvals (staging) | `.staging.yml` | Bind 127.0.0.1 |
| 3010 | Dashboard (staging) | `.staging.yml` | Bind 127.0.0.1 |
| 11434 | Ollama (dev) | `.dev.yml` | Solo red interna |
| 11435 | Ollama (staging) | `.staging.yml` | Bind 127.0.0.1 |

### 4.2 Puertos Internos (Red Docker)
| Servicio | Puerto Interno |
|----------|----------------|
| postgres (Hermes) | 5432 |
| redis | 6379 |
| ollama | 11434 |
| hermes | 8000 |
| api | 8000 |
| worker | - |
| approvals | 8002 |
| dashboard | 3000 |
| audit-db | 5432 |
| mock-dolibarr | 8001 |

---

## 5. SERVICIOS OBSOLETOS / A ELIMINAR

| Servicio/Archivo | Estado | Acción |
|------------------|--------|--------|
| `docker-compose.yml` (base) | Legacy - usa `postgres` para Hermes, no audit-db | **ELIMINAR** (reemplazado por arquitectura nativa) |
| `dolibarr/` (directorio viejo) | Referenciado en scripts, ya no existe | **LIMPIAR REFERENCIAS** |
| `mock-dolibarr` en `make up` | Solo dev/test | **NO LEVANTAR EN NATIVO** |
| `services/approval-service` en memoria | Debe usar PostgreSQL | **MIGRAR A POSTGRESQL** |
| `clean-all` target en Makefile | `docker system prune --volumes` destructivo | **ELIMINAR/REEMPLAZAR** |

---

## 6. RIESGOS DE MIGRACIÓN IDENTIFICADOS

| Riesgo | Severidad | Mitigación |
|--------|-----------|------------|
| **PYTHONPATH/imports rotos** al mover API/Worker a nativo | ALTO | Probar imports en `.venv` antes de systemd; usar `PYTHONPATH=${PROJECT_ROOT}` |
| **Playwright en Worker** (navegador headless) | MEDIO | `playwright install chromium --with-deps` nativo; verificar en systemd |
| **MariaDB no instalado** - Dolibarr no funcionará | CRÍTICO | Instalar MariaDB ANTES de configurar Dolibarr |
| **conf.php Dolibarr** - Sobrescribir configuración existente | MEDIO | Verificar existencia antes de generar; idempotencia |
| **Cloudflare Tunnel autenticación** - Requiere login manual | BAJO | Documentar paso manual; no bloquear `make install` |
| **Volúmenes Docker con datos** - Pérdida al eliminar | ALTO | Backup antes de `docker compose down -v`; migración PG/Redis |
| **Secrets en .env.local** - No commitear | CRÍTICO | Verificar `.gitignore`; separar dev/staging/prod |
| **Health checks** - Cambian de Docker a systemd/curl | MEDIO | Reescribir `make status`/`make check` para systemd + HTTP |

---

## 7. DECISIONES DE MIGRACIÓN POR SERVICIO

| Servicio | Decisión | Justificación |
|----------|----------|---------------|
| **Apache2** | ✅ YA NATIVO | Corriendo en puerto 80, solo necesita vhost 8080 |
| **MariaDB** | ✅ NATIVO (OBLIGATORIO) | Requerido por Dolibarr 23.0.4 |
| **Dolibarr 23.0.4** | ✅ NATIVO (EN PROGRESO) | Ya copiado en repo, Apache lo sirve |
| **PostgreSQL (audit-db)** | ✅ NATIVO | Trivial, estándar Debian |
| **Redis** | ✅ NATIVO | Trivial, estándar Debian |
| **Ollama** | ✅ NATIVO | Binario nativo + systemd maduro |
| **cloudflared** | ✅ NATIVO | Binario nativo + systemd; script ya existe |
| **API Integración (Hermes)** | ✅ NATIVO | FastAPI + virtualenv + systemd; verificar imports |
| **Worker Celery** | ✅ NATIVO | Mismo virtualenv; Playwright nativo; systemd |
| **Approvals** | ✅ NATIVO | Simple; migrar de memoria a PostgreSQL |
| **Dashboard** | ⚠️ DOCKER (TEMPORAL) | Node.js; migrar si tiempo, si no mantener Docker |
| **Mock Dolibarr** | 🐳 SOLO DOCKER (TESTS/CI) | No levantar en producción nativa |
| **Prometheus/Grafana/Loki** | 🐳 DOCKER (MONITORIZACIÓN) | Stack completo; no migrar en esta fase |

---

## 8. PLAN DE MIGRACIÓN FASES

### FASE 1 - Auditoría (ESTA) ✅ COMPLETADA

### FASE 2 - Scripts Base + .env
- Estructura `scripts/install/`, `scripts/configure/`, `scripts/services/`, `scripts/backup/`
- `.env.example` consolidado con variables nativas
- `config/` templates (Apache, systemd, Cloudflare)

### FASE 3 - MariaDB + Dolibarr
- `scripts/install/mariadb.sh` - Instalar MariaDB, crear DB/usuario Dolibarr
- `scripts/install/dolibarr.sh` - Actualizado a 23.0.4, usa `dolibarr-23.0.4/`
- `scripts/configure/apache.sh` - VirtualHost 8080 (ya existe, adaptar)
- `scripts/configure/dolibarr.sh` - Generar `conf.php` desde template

### FASE 4 - Apache
- Verificar módulos (ya en script)
- Habilitar sitio `transvega-dolibarr`
- `apachectl configtest` + reload

### FASE 5 - PostgreSQL (audit-db) + Redis Nativos
- `scripts/install/postgresql.sh` - Instalar PG16, ejecutar `init-audit-db.sql`
- `scripts/install/redis.sh` - Instalar Redis, configurar password/maxmemory

### FASE 6 - Python Virtualenv + API + Worker + Approvals
- `scripts/install/python.sh` - Python 3.11, crear `.venv`, instalar requirements
- `scripts/install/hermes.sh` - Instalar API + Worker + Approvals en `.venv`
- `scripts/configure/hermes.sh` - Generar systemd services

### FASE 7 - Ollama Nativo
- `scripts/install/ollama.sh` - Instalar Ollama, crear modelo `transvega-local`

### FASE 8 - Cloudflare Tunnel Nativo
- `scripts/install/cloudflare.sh` - Instalar cloudflared, configurar systemd
- `scripts/configure/cloudflare.sh` - Configurar ingress (adaptar script existente)

### FASE 9 - Systemd Services
- `config/systemd/hermes.service.template`
- `config/systemd/hermes-worker.service.template`
- `config/systemd/approvals.service.template`
- `config/systemd/ollama.service.template` (si no trae el instalador)
- `config/systemd/cloudflared.service.template`
- `scripts/configure/services.sh` - Instalar/activar todos

### FASE 10 - Makefile Simplificado
- Nuevo Makefile interfaz limpia (install, configure, start, stop, restart, status, check, backup, restore, test, lint)

### FASE 11 - Health Checks + Tests
- `scripts/check.sh` - Verificación profunda
- `scripts/services/status.sh` - Status systemd + HTTP health
- Ejecutar `make test`, `make lint`

### FASE 12 - Backup/Restore
- `scripts/backup/database.sh` - PG + MariaDB + Redis
- `scripts/backup/restore.sh` - Con confirmación

### FASE 13 - Documentación + Limpieza Legacy
- Actualizar README
- Eliminar Dockerfiles/compose legacy (excepto test/CI)
- Commit final

---

## 9. ARCHIVOS A CREAR / MODIFICAR / ELIMINAR

### 9.1 Nuevos Archivos (Estimado ~35)
```
scripts/
├── install/
│   ├── dependencies.sh      # apt packages base
│   ├── python.sh            # .venv + requirements
│   ├── mariadb.sh           # MariaDB para Dolibarr
│   ├── postgresql.sh        # PostgreSQL para audit
│   ├── redis.sh             # Redis nativo
│   ├── apache.sh            # Apache2 + módulos
│   ├── dolibarr.sh          # Dolibarr 23.0.4 (desde repo)
│   ├── ollama.sh            # Ollama nativo + modelo
│   ├── cloudflare.sh        # cloudflared binario + systemd
│   └── hermes.sh            # API + Worker + Approvals en .venv
├── configure/
│   ├── apache.sh            # VirtualHost Dolibarr (adaptar existente)
│   ├── dolibarr.sh          # conf.php desde template
│   ├── mariadb.sh           # Configurar MariaDB
│   ├── postgresql.sh        # Configurar audit DB
│   ├── redis.sh             # Configurar Redis
│   ├── cloudflare.sh        # Ingress Cloudflare (adaptar existente)
│   ├── hermes.sh            # Variables para systemd
│   └── services.sh          # Instalar units systemd
├── services/
│   ├── start.sh             # systemctl start todos
│   ├── stop.sh              # systemctl stop todos
│   ├── restart.sh           # systemctl restart todos
│   └── status.sh            # systemctl status + health HTTP
├── backup/
│   ├── database.sh          # PG + MariaDB + Redis
│   └── restore.sh           # Con confirmación
├── install.sh               # Orquestador fase 2-8
├── configure.sh             # Orquestador configure/*
└── check.sh                 # Verificación profunda

config/
├── apache/
│   └── dolibarr.conf.template
├── cloudflare/
│   └── config.yml.template
├── systemd/
│   ├── hermes.service.template
│   ├── hermes-worker.service.template
│   ├── approvals.service.template
│   ├── ollama.service.template
│   └── cloudflared.service.template
├── mariadb/
│   └── dolibarr.cnf.template
├── redis/
│   └── redis.conf.template
└── postgresql/
    └── audit-db.sql (copia de init-audit-db.sql)

.env.example                 # Consolidado documentado
Makefile                     # Nuevo simplificado
```

### 9.2 Archivos a Modificar (~15)
- `scripts/install-dolibarr.sh` → Actualizar a 23.0.4, usar `dolibarr-23.0.4/`
- `scripts/configure-apache-dolibarr.sh` → Adaptar a `config/apache/` template
- `scripts/dolibarr-health.sh` → Adaptar a estructura nativa
- `scripts/configure-cloudflare-dolibarr.sh` → Adaptar a `config/cloudflare/`
- `scripts/test-integration-local.sh` → Usar PostgreSQL/Redis nativos puertos 5432/6379
- `services/integration-api/app/core/config.py` → Soportar `.env` en root + computed URLs
- `services/task-queue/app/celery_app.py` → Funcionar fuera de Docker (paths)
- `services/approval-service/app.py` → Usar PostgreSQL (no memoria)
- `.gitignore` → Añadir `.venv/`, `backups/`, logs systemd
- `README.md` → Nueva guía instalación nativa
- `pyproject.toml` → Verificar paths para mypy/ruff fuera de Docker

### 9.3 Archivos a Eliminar (~15)
- `docker-compose.yml` (base legacy)
- `docker-compose.dev.yml` (reemplazado por nativo)
- `docker-compose.staging.yml` (reemplazado por nativo + cloudflared nativo)
- `docker-compose.prod.yml` (reemplazado por nativo + cloudflared nativo)
- `infrastructure/docker/Dockerfile.api`
- `infrastructure/docker/Dockerfile.worker`
- `infrastructure/docker/Dockerfile.approvals`
- `infrastructure/docker/Dockerfile.dashboard` (opcional, mantener si dashboard se queda en Docker)
- `infrastructure/docker/Dockerfile.mock-dolibarr` (mantener para CI)
- `infrastructure/docker/init-audit-db.sql` → mover a `config/postgresql/`
- Targets Makefile legacy (`up`, `down`, `logs-*`, `shell-*`, `clean`, `clean-all`, `staging-*`, `deploy-*`, `docs-serve`, `metrics`, `grafana`, `alerts`)

### 9.4 Archivos a Mantener (Docker solo para CI/Tests)
- `docker-compose.test.yml` - Tests integración (PostgreSQL/Redis en puertos 55432/56379)
- `Dockerfile.mock-dolibarr` - Para CI integration tests
- `.github/workflows/ci-cd.yml` - Adaptar para usar Docker solo en CI, tests nativos en lo posible

---

## 10. CRITERIOS DE VALIDACIÓN (DEFINICIÓN DE "TERMINADO")

La refactorización se considera completa cuando **TODOS** estos checks pasan:

```bash
# 1. Instalación limpia en Kali/Debian fresco
git clone <repo>
cd transvega-animal
cp .env.example .env
nano .env  # Solo secretos reales
make install     # ✅ Sin errores, idempotente
make start       # ✅ Todos los servicios systemd active
make status      # ✅ Todos [OK] con health checks reales
make check       # ✅ 0 FAIL, warnings accionables

# 2. Funcionalidad verificada
curl http://localhost:8080/                    # Dolibarr UI ✅
curl http://localhost:8080/api/index.php       # Dolibarr REST API ✅
curl http://127.0.0.1:8000/health              # Hermes API ✅
curl http://127.0.0.1:8000/health/ready        # Hermes ready ✅
curl http://127.0.0.1:8002/health/live         # Approvals ✅
curl http://127.0.0.1:11434/api/tags           # Ollama ✅
systemctl status mariadb                       # MariaDB ✅
systemctl status postgresql                    # PostgreSQL ✅
systemctl status redis                         # Redis ✅
systemctl status apache2                       # Apache ✅
systemctl status cloudflared                   # Cloudflare ✅

# 3. Tests
make test        # ✅ Unit + Integration pasan
make lint        # ✅ Ruff + MyPy pasan

# 4. Backup/Restore
make backup      # ✅ Crea backup PG + MariaDB
make restore     # ✅ Restaura con confirmación

# 5. Cloudflare (manual)
# cloudflared tunnel login (una vez)
# make configure  # Configura ingress
# https://dolibarr-staging.mascotalegal.es → Dolibarr ✅
```

---

## 11. PRÓXIMOS PASOS INMEDIATOS

1. **Crear estructura `scripts/` y `config/`** según plan
2. **Actualizar `.env.example`** consolidado con variables nativas
3. **Escribir `scripts/install/dependencies.sh`** (apt packages)
4. **Escribir `scripts/install/mariadb.sh`** (CRÍTICO - Dolibarr lo necesita)
5. **Adaptar `scripts/install-dolibarr.sh`** a 23.0.4 y usar `dolibarr-23.0.4/`
6. **Verificar Apache vhost** funciona con Dolibarr 23.0.4
7. **Probar health checks** end-to-end

---

## 12. NOTAS CRÍTICAS PARA EL EQUIPO

> **NO ELIMINAR VOLÚMENES DOCKER HASTA CONFIRMAR MIGRACIÓN EXITOSA**
> - `docker volume ls` → identificar `audit-db-data`, `redis-data`, `ollama-data`, etc.
> - Backup PostgreSQL: `pg_dump` antes de `docker compose down -v`
> - Backup Redis: `redis-cli --rdb` antes de eliminar volumen
> - Ollama: modelos persisten en `~/.ollama` nativo tras migración

> **SECRETS MANAGEMENT**
> - `.env.local` tiene secretos REALES (Telegram bot token, Cloudflare token, NVIDIA API key)
> - NUNCA commitear `.env.local` - ya en `.gitignore`
> - Producción usará secrets propios (GitHub Secrets, Vault, etc.)

> **DOLIBARR 23.0.4 VERSIONADO EN GIT**
> - `dolibarr-23.0.4/` ya está en Git (commit anterior)
> - Scripts deben usar esta carpeta, NO descargar otra versión
> - `custom/` es para extensiones propias (versionado)

> **MOCK DOLIBARR SOLO PARA TESTS**
> - No incluir en `make start` nativo
> - Mantener `docker-compose.test.yml` y `Dockerfile.mock-dolibarr` para CI
> - Tests unitarios/integración siguen usando mock

---

*Fin del informe de auditoría. Proceder con FASE 2 - Scripts Base.*