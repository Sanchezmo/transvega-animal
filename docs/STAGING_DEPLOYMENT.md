# Staging Deployment Guide

Guía para desplegar y operar el entorno de staging de Transvega Animal.

## 1. Prerrequisitos

- Docker y Docker Compose instalados
- Acceso a Cloudflare Dashboard para configurar túneles
- Bot de Telegram creado con @BotFather
- Dominio configurado en Cloudflare

## 2. Configuración inicial

### 2.1 Crear archivo de entorno

```bash
cp .env.staging.example .env.staging
```

Edita `.env.staging` y rellena **todos** los valores marcados como `CHANGE_ME`:

```bash
# Base de datos auditoría
AUDIT_DB_PASSWORD=tu_password_seguro

# Redis
REDIS_PASSWORD=tu_password_redis_seguro

# JWT y cifrado
JWT_SECRET_KEY=clave_jwt_muy_larga_y_aleatoria
FERNET_KEY=clave_fernet_base64_32_bytes

# API Keys de agentes (generar claves únicas)
AGENT_API_KEY_SUPERVISOR=sk_xxx
AGENT_API_KEY_DOG_INTAKE=sk_xxx
# ... resto de AGENT_API_KEY_*

# Dolibarr Database
DOLIBARR_DB_PASSWORD=password_dolibarr_db
DOLIBARR_DB_ROOT_PASSWORD=password_root_dolibarr

# Telegram (valores REALES de @BotFather)
TELEGRAM_BOT_TOKEN=123456789:ABC-DEF...
TELEGRAM_WEBHOOK_SECRET=clave_secreta_hex_32_bytes
TELEGRAM_WEBHOOK_PUBLIC_URL=https://telegram-staging.tu-dominio.com/api/v1/telegram/webhook

# Cloudflare
CLOUDFLARE_TUNNEL_TOKEN_STAGING=token_del_tunnel_staging
```

### 2.2 Variables críticas a generar

```bash
# Generar JWT_SECRET_KEY (64 chars hex)
openssl rand -hex 32

# Generar FERNET_KEY (32 bytes base64)
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Generar TELEGRAM_WEBHOOK_SECRET
openssl rand -hex 32
```

## 3. Levantar entorno de staging

```bash
# Validar configuración
docker compose --env-file .env.staging -f docker-compose.staging.yml config

# Levantar servicios
./scripts/staging-up.sh
```

Verificar estado:
```bash
./scripts/staging-status.sh
```

Servicios esperados (healthy):
- audit-db (PostgreSQL)
- redis
- mock-dolibarr (API mock Dolibarr)
- dolibarr-db (MariaDB)
- dolibarr (Dolibarr ERP real)
- ollama (Local LLM)
- api (FastAPI)
- worker (Celery)
- approvals
- dashboard
- cloudflared

## 4. Health checks

```bash
# API health
curl http://127.0.0.1:8010/health
curl http://127.0.0.1:8010/health/ready

# API docs (solo local)
curl http://127.0.0.1:8010/docs
```

## 5. Cloudflare Tunnel

### 5.1 Configurar túneles en Cloudflare Dashboard

Crear dos túneles en Cloudflare Zero Trust > Networks > Tunnels:

**Telegram Tunnel:**
- Name: `telegram-staging`
- Public hostname: `telegram-staging.tu-dominio.com`
- Path: `/api/v1/telegram/webhook`
- Service: HTTP
- Origin: `http://api:8000`
- **NO** Cloudflare Access

**Dolibarr Tunnel:**
- Name: `dolibarr-staging`
- Public hostname: `dolibarr-staging.tu-dominio.com`
- Service: HTTP
- Origin: `http://dolibarr:80`
- Cloudflare Access: **SÍ** (recomendado)

### 5.2 Verificar cloudflared

```bash
docker compose --env-file .env.staging -f docker-compose.staging.yml ps cloudflared
docker compose --env-file .env.staging -f docker-compose.staging.yml logs --tail=50 cloudflared
```

Debe mostrar conexión exitosa al túnel.

### 5.3 Probar conectividad interna

```bash
# Desde cloudflared hacia API
docker compose --env-file .env.staging -f docker-compose.staging.yml exec cloudflared wget -qO- http://api:8000/health

# Desde cloudflared hacia Dolibarr
docker compose --env-file .env.staging -f docker-compose.staging.yml exec cloudflared wget -qO- http://dolibarr:80
```

## 6. Configurar Webhook Telegram

### 6.1 Configurar .env.staging con URL pública

```bash
TELEGRAM_WEBHOOK_PUBLIC_URL=https://telegram-staging.tu-dominio.com/api/v1/telegram/webhook
```

### 6.2 Ejecutar script de configuración

```bash
./scripts/configure-telegram-webhook.sh
```

Debe responder:
```
[INFO] Webhook configurado correctamente
{
  "ok": true,
  "result": true,
  "description": "Webhook was set"
}
```

### 6.3 Verificar webhook

```bash
./scripts/check-telegram-webhook.sh
```

Salida esperada:
```
[INFO] URL configurada: https://telegram-staging.tu-dominio.com/api/v1/telegram/webhook
[INFO] Actualizaciones pendientes: 0
[INFO] Último error: ninguno
```

## 7. Probar bot real

1. Abre Telegram en tu móvil
2. Busca tu bot (@TuBotStaging)
3. Envía `/start`
4. Debe responder: "¡Nuevo ingreso de perro! ¿Cuál es el nombre del perro?"
5. Completa el flujo de alta de perro
6. Verifica que responde con confirmación final

## 8. Acceder a Dolibarr

1. Abre navegador en `https://dolibarr-staging.tu-dominio.com`
2. Cloudflare Access pedirá autenticación (si configurado)
3. Login en Dolibarr con credenciales configuradas

## 9. Ver logs

```bash
# Todos los servicios
docker compose --env-file .env.staging -f docker-compose.staging.yml logs -f

# Solo API
docker compose --env-file .env.staging -f docker-compose.staging.yml logs -f api

# Solo cloudflared
docker compose --env-file .env.staging -f docker-compose.staging.yml logs -f cloudflared
```

## 10. Parar staging

```bash
docker compose --env-file .env.staging -f docker-compose.staging.yml down

# Con volúmenes (CUIDADO: borra datos)
docker compose --env-file .env.staging -f docker-compose.staging.yml down -v
```

## 11. Troubleshooting

### API no responde
```bash
docker compose --env-file .env.staging -f docker-compose.staging.yml logs api
# Verificar healthcheck
curl http://127.0.0.1:8010/health/ready
```

### Cloudflared no conecta
```bash
docker compose --env-file .env.staging -f docker-compose.staging.yml logs cloudflared
# Verificar token válido
# Verificar redes: cloudflared debe estar en transvega-backend y transvega-frontend
```

### Dolibarr no accesible
```bash
# Verificar Dolibarr y su DB
docker compose --env-file .env.staging -f docker-compose.staging.yml ps dolibarr dolibarr-db
docker compose --env-file .env.staging -f docker-compose.staging.yml logs dolibarr
# Probar conexión interna
docker compose --env-file .env.staging -f docker-compose.staging.yml exec cloudflared wget -qO- http://dolibarr:80
```

### Ollama no descarga modelos
```bash
docker compose --env-file .env.staging -f docker-compose.staging.yml logs ollama
# Si falla por red, los modelos se descargan al primer uso desde API
```

## 12. Variables de entorno completas

Ver `.env.staging.example` para lista completa. Variables obligatorias:

| Variable | Descripción |
|----------|-------------|
| AUDIT_DB_PASSWORD | Password PostgreSQL auditoría |
| REDIS_PASSWORD | Password Redis |
| JWT_SECRET_KEY | Clave firma JWT (64 hex) |
| FERNET_KEY | Clave cifrado Fernet (base64 32 bytes) |
| AGENT_API_KEY_SUPERVISOR | API key supervisor |
| AGENT_API_KEY_DOG_INTAKE | API key dog intake |
| DOLIBARR_DB_PASSWORD | Password MariaDB Dolibarr |
| DOLIBARR_DB_ROOT_PASSWORD | Password root MariaDB |
| TELEGRAM_BOT_TOKEN | Token real @BotFather |
| TELEGRAM_WEBHOOK_SECRET | Secreto webhook (hex 32 bytes) |
| TELEGRAM_WEBHOOK_PUBLIC_URL | URL pública webhook |
| CLOUDFLARE_TUNNEL_TOKEN_STAGING | Token túnel Cloudflare |
| OLLAMA_MODEL | Modelo LLM multimodal (ej: transvega-local) |
| OLLAMA_BASE_MODEL | Modelo base Qwen (ej: qwen3.5:4b-q4_K_M) |