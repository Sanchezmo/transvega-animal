# Transvega Animal - Despliegue en Producción

Este documento describe el proceso de despliegue en producción.

## Arquitectura de Producción

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           INTERNET                                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        CLOUDFLARE (Edge)                                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │    DNS      │  │    WAF      │  │   Access    │  │   Tunnel    │        │
│  │  *.empresa. │  │  DDoS/Rate  │  │  OIDC/Google│  │  *.erp/api  │        │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘        │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
        ┌──────────────────┐ ┌──────────────┐ ┌──────────────┐
        │   VPS Dolibarr   │ │  VPS API/    │ │  Equipo Local│
        │   (Producción)   │ │  Workers     │ │  (Hermes)    │
        │                  │ │              │ │              │
        │ ┌──────────────┐ │ │ ┌──────────┐ │ │ ┌──────────┐ │
        │ │  Nginx + SSL │ │ │ │  Nginx   │ │ │ │  Hermes  │ │
        │ │  Dolibarr    │ │ │ │  FastAPI │ │ │ │  Ollama  │ │
        │ │  MariaDB     │ │ │ │  Redis   │ │ │ │  Agentes │ │
        │ │  Redis       │ │ │ │  Workers │ │ │ └──────────┘ │
        │ └──────────────┘ │ │ └──────────┘ │ └──────────────┘
        └──────────────────┘ └──────────────┘
```

## Requisitos Previos

### VPS Dolibarr (Producción)
- Ubuntu 22.04/24.04 LTS
- 4 vCPU, 8GB RAM, 100GB SSD
- Docker 24+, Docker Compose 2+
- Dominio configurado en Cloudflare

### VPS API/Workers (Producción)
- Ubuntu 22.04/24.04 LTS
- 4 vCPU, 16GB RAM, 100GB SSD
- Docker 24+, Docker Compose 2+
- GPU opcional (para vLLM/Ollama)

### Equipo Local (Hermes)
- Ubuntu 22.04/24.04 o Windows 11 WSL2
- 32GB RAM, GPU NVIDIA (RTX 3080+ recomendado)
- Docker 24+

## Despliegue Paso a Paso

### 1. Configurar Cloudflare

```bash
# 1. Añadir dominio a Cloudflare
# 2. Cambiar nameservers en registrar
# 3. Crear Cloudflare Tunnel:
cloudflared tunnel login
cloudflared tunnel create transvega-prod
cloudflared tunnel route dns transvega-prod erp.empresa.es
cloudflared tunnel route dns transvega-prod api.empresa.es
cloudflared tunnel route dns transvega-prod api.empresa.es
cloudflared tunnel route dns transvega-prod hermes.empresa.es
cloudflared tunnel route dns transvega-prod status.empresa.es

# 3. Configurar Access Policies:
# - Email domain: empresa.es (Google Workspace)
# - Groups: admins, agents, accounting
```

### 2. Preparar VPS Dolibarr

```bash
# En VPS Dolibarr
sudo apt update && sudo apt upgrade -y
sudo apt install -y docker.io docker-compose-plugin git curl

# Clonar repo
git clone https://github.com/empresa/transvega-animal.git /opt/transvega
cd /opt/transvega

# Configurar variables
cp .env.example .env.prod
# Editar .env.prod con valores de producción

# Levantar
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### 2.1 docker-compose.prod.yml (Dolibarr)

```yaml
version: '3.8'

services:
  dolibarr-db:
    image: mariadb:10.11
    container_name: dolibarr-db-prod
    environment:
      MARIADB_ROOT_PASSWORD: ${DOLIBARR_DB_ROOT_PASSWORD}
      MARIADB_DATABASE: ${DOLIBARR_DB_NAME}
      MARIADB_USER: ${DOLIBARR_DB_USER}
      MARIADB_PASSWORD: ${DOLIBARR_DB_PASSWORD}
    volumes:
      - dolibarr-db-data:/var/lib/mysql
      - ./init-db.sql:/docker-entrypoint-initdb.d/init-db.sql:ro
    networks:
      - dolibarr-network
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 2G
        reservations:
          memory: 1G

  dolibarr:
    build:
      context: .
      dockerfile: infrastructure/docker/Dockerfile.dolibarr-prod
    container_name: dolibarr-prod
    environment:
      DOLI_DB_HOST: dolibarr-db
      DOLI_DB_NAME: ${DOLIBARR_DB_NAME}
      DOLI_DB_USER: ${DOLIBARR_DB_USER}
      DOLI_DB_PASSWORD: ${DOLIBARR_DB_PASSWORD}
      DOLI_DB_PREFIX: llx_
      DOLI_ADMIN_LOGIN: ${DOLIBARR_ADMIN_LOGIN}
      DOLI_ADMIN_PASSWORD: ${DOLIBARR_ADMIN_PASSWORD}
      DOLI_URL_ROOT: https://erp.empresa.es
      PHP_INI_MEMORY_LIMIT: 512M
      PHP_INI_MAX_EXECUTION_TIME: 300
    volumes:
      - dolibarr-documents:/var/www/documents
      - ./infra/docker/dolibarr-conf.php:/var/www/html/conf/conf.php:ro
      - ./infra/docker/php-prod.ini:/usr/local/etc/php/conf.d/prod.ini:ro
    ports:
      - "80:80"
    depends_on:
      dolibarr-db:
        condition: service_healthy
    networks:
      - dolibarr-network
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 2G
        reservations:
          memory: 1G

  nginx:
    image: nginx:alpine
    container_name: dolibarr-nginx
    volumes:
      - ./infra/nginx/conf.d:/etc/nginx/conf.d:ro
      - ./infra/nginx/ssl:/etc/nginx/ssl:ro
      - ./infra/nginx/certbot:/var/www/certbot:ro
    ports:
      - "80:80"
      - "443:443"
    depends_on:
      - dolibarr
    networks:
      - dolibarr-network
    restart: unless-stopped

  certbot:
    image: certbot/certbot
    container_name: dolibarr-certbot
    volumes:
      - ./infra/nginx/ssl:/etc/letsencrypt
      - ./infra/nginx/certbot:/var/www/certbot
    entrypoint: "/bin/sh -c 'trap exit TERM; while :; do certbot renew; sleep 12h & wait $${!}; done'"

volumes:
  dolibarr-db-data:
  dolibarr-documents:

networks:
  dolibarr-network:
    driver: bridge
```

### 2. Preparar VPS API/Workers

```bash
# En VPS API
sudo apt update && sudo apt upgrade -y
sudo apt install -y docker.io docker-compose-plugin git curl nginx certbot

# Clonar repo
git clone https://github.com/empresa/transvega-animal.git /opt/transvega
cd /opt/transvega

# Configurar
cp .env.example .env.prod
# Editar .env.prod

# Levantar
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### 2.1 docker-compose.prod.yml (API/Workers)

```yaml
version: '3.8'

services:
  # Base de datos auditoría
  audit-db:
    image: postgres:16-alpine
    container_name: audit-db-prod
    environment:
      POSTGRES_DB: audit
      POSTGRES_USER: audit
      POSTGRES_PASSWORD: ${AUDIT_DB_PASSWORD}
    volumes:
      - audit-db-data:/var/lib/postgresql/data
      - ./infrastructure/docker/init-audit-db.sql:/docker-entrypoint-initdb.d/init.sql:ro
    networks:
      - transvega-internal
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 2G
        reservations:
          memory: 1G

  # Redis
  redis:
    image: redis:7-alpine
    container_name: redis-prod
    command: redis-server --requirepass ${REDIS_PASSWORD} --maxmemory 2gb --maxmemory-policy allkeys-lru
    volumes:
      - redis-data:/data
    networks:
      - transvega-internal
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 3G
        reservations:
          memory: 1G

  # API Integración
  api:
    build:
      context: .
      dockerfile: infrastructure/docker/Dockerfile.api
    container_name: api-prod
    environment:
      - ENVIRONMENT=production
      - AUDIT_DB_URL=postgresql://audit:${AUDIT_DB_PASSWORD}@audit-db:5432/audit
      - REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0
      - DOLIBARR_API_URL=https://erp.empresa.es/api/index.php
      - DOLIBARR_API_KEY=${DOLIBARR_API_KEY}
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}
      - FERNET_KEY=${FERNET_KEY}
    volumes:
      - ./services/integration-api:/app:ro
      - ./adapters:/app/adapters:ro
      - ./shared:/app/shared:ro
    depends_on:
      audit-db:
        condition: service_healthy
      redis:
        condition: service_healthy
    networks:
      - transvega-internal
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 2G
        reservations:
          memory: 1G

  # Worker Celery
  worker:
    build:
      context: .
      dockerfile: infrastructure/docker/Dockerfile.worker
    container_name: worker-prod
    environment:
      - CELERY_BROKER_URL=redis://:${REDIS_PASSWORD}@redis:6379/0
      - CELERY_RESULT_BACKEND=redis://:${REDIS_PASSWORD}@redis:6379/2
      - AUDIT_DB_URL=postgresql://audit:${AUDIT_DB_PASSWORD}@audit-db:5432/audit
      - DOLIBARR_API_URL=https://erp.empresa.es/api/index.php
      - DOLIBARR_API_KEY=${DOLIBARR_API_KEY}
    volumes:
      - ./services/integration-api:/app:ro
      - ./adapters:/app/adapters:ro
      - ./shared:/app/shared:ro
      - ./agents:/app/agents:ro
    depends_on:
      redis:
        condition: service_healthy
      audit-db:
        condition: service_healthy
    networks:
      - transvega-internal
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 4G
        reservations:
          memory: 2G

  # Servicio Aprobaciones
  approvals:
    build:
      context: .
      dockerfile: infrastructure/docker/Dockerfile.approvals
    container_name: approvals-prod
    environment:
      - AUDIT_DB_URL=postgresql://audit:${AUDIT_DB_PASSWORD}@audit-db:5432/audit
      - REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/1
      - NOTIFICATION_WEBHOOK_URL=${NOTIFICATION_WEBHOOK_URL}
    volumes:
      - ./services/approval-service:/app:ro
    depends_on:
      audit-db:
        condition: service_healthy
      redis:
        condition: service_healthy
    networks:
      - transvega-internal
    restart: unless-stopped

  # Dashboard
  dashboard:
    build:
      context: .
      dockerfile: infrastructure/docker/Dockerfile.dashboard
    container_name: dashboard-prod
    environment:
      - API_URL=https://api.empresa.es
      - APPROVALS_URL=https://api.empresa.es/approvals
    volumes:
      - ./services/dashboard:/app:ro
    depends_on:
      - api
      - approvals
    networks:
      - transvega-internal
    restart: unless-stopped

  # Ollama (Modelos locales)
  ollama:
    image: ollama/ollama:latest
    container_name: ollama-prod
    volumes:
      - ollama-data:/root/.ollama
    ports:
      - "11434:11434"
    environment:
      - OLLAMA_MODELS=llama3.1:8b,mistral:7b,codellama:7b
    deploy:
      resources:
        limits:
          memory: 16G
        reservations:
          memory: 8G
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    networks:
      - transvega-internal
    restart: unless-stopped

  # vLLM (opcional, para producción alta carga)
  # vllm:
  #   image: vllm/vllm-openai:latest
  #   container_name: vllm-prod
  #   command: --model meta-llama/Meta-Llama-3.1-8B-Instruct --gpu-memory-utilization 0.9 --max-model-len 8192
  #   ports:
  #     - "8003:8000"
  #   deploy:
  #     resources:
  #       reservations:
  #         devices:
  #           - driver: nvidia
  #             count: 1
  #             capabilities: [gpu]
  #   networks:
  #     - transvega-internal
  #   restart: unless-stopped

  # Nginx Reverse Proxy
  nginx:
    image: nginx:alpine
    container_name: nginx-prod
    volumes:
      - ./infra/nginx/prod.conf:/etc/nginx/nginx.conf:ro
      - ./infra/nginx/ssl:/etc/nginx/ssl:ro
      - ./infra/nginx/certbot:/var/www/certbot:ro
    ports:
      - "80:80"
      - "443:443"
    depends_on:
      - api
      - approvals
      - dashboard
    networks:
      - transvega-internal
    restart: unless-stopped

  # Certbot
  certbot:
    image: certbot/certbot
    container_name: certbot-prod
    volumes:
      - ./infra/nginx/ssl:/etc/letsencrypt
      - ./infra/nginx/certbot:/var/www/certbot
    entrypoint: "/bin/sh -c 'trap exit TERM; while :; do certbot renew; sleep 12h & wait $${!}; done'"

volumes:
  audit-db-data:
  redis-data:
  ollama-data:

networks:
  transvega-internal:
    driver: bridge
```

### 3. Configurar Nginx (API)

```nginx
# infra/nginx/prod.conf
user nginx;
worker_processes auto;
error_log /var/log/nginx/error.log warn;
pid /var/run/nginx.pid;

events {
    worker_connections 1024;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;
    
    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" "$http_x_forwarded_for"';
    
    access_log /var/log/nginx/access.log main;
    
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;
    client_max_body_size 50M;
    
    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api:10m rate=100r/s;
    limit_req_zone $binary_remote_addr zone=login:10m rate=10r/m;
    
    # Upstreams
    upstream api_backend {
        server api:8000;
        keepalive 32;
    }
    
    upstream approvals_backend {
        server approvals:8002;
        keepalive 16;
    }
    
    upstream dashboard_backend {
        server dashboard:3000;
        keepalive 16;
    }
    
    # HTTP -> HTTPS redirect
    server {
        listen 80;
        server_name api.empresa.es dashboard.empresa.es approvals.empresa.es;
        
        location /.well-known/acme-challenge/ {
            root /var/www/certbot;
        }
        
        location / {
            return 301 https://$server_name$request_uri;
        }
    }
    
    # API
    server {
        listen 443 ssl http2;
        server_name api.empresa.es;
        
        ssl_certificate /etc/nginx/ssl/fullchain.pem;
        ssl_certificate_key /etc/nginx/ssl/privkey.pem;
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers HIGH:!aNULL:!MD5;
        
        # Security headers
        add_header X-Frame-Options DENY;
        add_header X-Content-Type-Options nosniff;
        add_header X-XSS-Protection "1; mode=block";
        add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
        
        # Rate limiting
        limit_req zone=api burst=200 nodelay;
        
        location /health {
            proxy_pass http://api_backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
        }
        
        location / {
            limit_req zone=api burst=200 nodelay;
            
            proxy_pass http://api_backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            
            proxy_http_version 1.1;
            proxy_set_header Connection "";
            proxy_buffering off;
            proxy_cache off;
        }
    }
    
    # Approvals
    server {
        listen 443 ssl http2;
        server_name approvals.empresa.es;
        
        ssl_certificate /etc/nginx/ssl/fullchain.pem;
        ssl_certificate_key /etc/nginx/ssl/privkey.pem;
        
        location / {
            limit_req zone=login burst=10 nodelay;
            
            proxy_pass http://approvals_backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
    }
    
    # Dashboard
    server {
        listen 443 ssl http2;
        server_name dashboard.empresa.es;
        
        ssl_certificate /etc/nginx/ssl/fullchain.pem;
        ssl_certificate_key /etc/nginx/ssl/privkey.pem;
        
        location / {
            proxy_pass http://dashboard_backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
        }
    }
}
```

### 4. Configurar Nginx (Dolibarr)

```nginx
# infra/nginx/dolibarr.conf
user nginx;
worker_processes auto;
error_log /var/log/nginx/error.log warn;
pid /var/run/nginx.pid;

events {
    worker_connections 1024;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;
    
    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" "$http_x_forwarded_for"';
    
    access_log /var/log/nginx/access.log main;
    
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;
    client_max_body_size 100M;
    
    # Rate limiting
    limit_req_zone $binary_remote_addr zone=dolibarr:10m rate=50r/s;
    limit_req_zone $binary_remote_addr zone=login:10m rate=5r/m;
    
    upstream dolibarr_backend {
        server dolibarr:80;
        keepalive 32;
    }
    
    # HTTP -> HTTPS
    server {
        listen 80;
        server_name erp.empresa.es;
        
        location /.well-known/acme-challenge/ {
            root /var/www/certbot;
        }
        
        location / {
            return 301 https://$server_name$request_uri;
        }
    }
    
    # HTTPS
    server {
        listen 443 ssl http2;
        server_name erp.empresa.es;
        
        ssl_certificate /etc/nginx/ssl/fullchain.pem;
        ssl_certificate_key /etc/nginx/ssl/privkey.pem;
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers HIGH:!aNULL:!MD5;
        
        # Security headers
        add_header X-Frame-Options SAMEORIGIN;
        add_header X-Content-Type-Options nosniff;
        add_header X-XSS-Protection "1; mode=block";
        add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
        add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:; connect-src 'self'; frame-ancestors 'self';";
        
        # Rate limiting
        limit_req zone=dolibarr burst=100 nodelay;
        limit_req zone=login burst=5 nodelay;
        
        # Proxy to Dolibarr
        location / {
            proxy_pass http://dolibarr_backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_set_header X-Forwarded-Host $host;
            proxy_set_header X-Forwarded-Port 443;
            
            proxy_http_version 1.1;
            proxy_set_header Connection "";
            proxy_buffering off;
            proxy_cache off;
            
            # Timeouts
            proxy_connect_timeout 60s;
            proxy_send_timeout 60s;
            proxy_read_timeout 120s;
        }
        
        # Static files caching
        location ~* \.(jpg|jpeg|png|gif|ico|css|js|pdf|woff|woff2)$ {
            proxy_pass http://dolibarr_backend;
            proxy_cache_valid 200 30d;
            add_header X-Cache-Status $upstream_cache_status;
        }
        
        # API endpoints - no cache
        location /api/ {
            proxy_pass http://dolibarr_backend;
            proxy_cache off;
            proxy_no_cache 1;
            proxy_cache_bypass 1;
        }
        
        # Health check
        location /health {
            access_log off;
            return 200 "healthy\n";
            add_header Content-Type text/plain;
        }
    }
}
```

### 5. Variables de Entorno Producción (.env.prod)

```bash
# .env.prod - VALORES REALES DE PRODUCCIÓN

# =============================================================================
# DOMINIO Y CLOUDFLARE
# =============================================================================
DOMAIN=empresa.es
CLOUDFLARE_API_TOKEN=cf_token_con_permisos_zone_dns_access
CLOUDFLARE_ACCOUNT_ID=account_id
CLOUDFLARE_ZONE_ID=zone_id
CLOUDFLARE_TUNNEL_TOKEN=tunnel_token

# =============================================================================
# VPS DOLIBARR
# =============================================================================
DOLIBARR_DB_ROOT_PASSWORD=clave_root_muy_segura
DOLIBARR_DB_NAME=dolibarr
DOLIBARR_DB_USER=dolibarr
DOLIBARR_DB_PASSWORD=clave_dolibarr_segura
DOLIBARR_ADMIN_LOGIN=admin
DOLIBARR_ADMIN_PASSWORD=clave_admin_muy_segura
DOLIBARR_API_KEY=clave_api_dolibarr_larga_y_segura
DOLIBARR_VERSION=20.0

# =============================================================================
# VPS API/WORKERS
# =============================================================================
AUDIT_DB_PASSWORD=clave_postgres_auditoria_muy_segura
REDIS_PASSWORD=clave_redis_muy_segura
JWT_SECRET_KEY=clave_jwt_muy_larga_y_aleatoria_64_chars_minimo
FERNET_KEY=clave_fernet_32_bytes_base64
JWT_ALGORITHM=HS256
JWT_EXPIRATION_MINUTES=30
JWT_REFRESH_EXPIRATION_DAYS=7

# API Keys por agente (generar con: openssl rand -base64 32)
AGENT_API_KEY_SUPERVISOR=tvsk_xxx
AGENT_API_KEY_PRODUCTS=tvsk_xxx
AGENT_API_KEY_COMPLIANCE=tvsk_xxx
AGENT_API_KEY_PUBLISHING=tvsk_xxx
AGENT_API_KEY_SALES=tvsk_xxx
AGENT_API_KEY_INVOICING=tvsk_xxx
AGENT_API_KEY_PURCHASES=tvsk_xxx
AGENT_API_KEY_BANKING=tvsk_xxx
AGENT_API_KEY_ACCOUNTING=tvsk_xxx
AGENT_API_KEY_TAX=tvsk_xxx
AGENT_API_KEY_MARKETING=tvsk_xxx
AGENT_API_KEY_TECHNICAL=tvsk_xxx

# Dolibarr
DOLIBARR_API_URL=https://erp.empresa.es/api/index.php
DOLIBARR_API_KEY=clave_api_dolibarr_produccion
DOLIBARR_TIMEOUT=30

# Google Workspace
GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=xxx
GOOGLE_WORKSPACE_DOMAIN=empresa.es
GOOGLE_ADMIN_EMAIL=admin@empresa.es

# Cloudflare
CLOUDFLARE_API_TOKEN=cf_token_produccion
CLOUDFLARE_ACCOUNT_ID=account_id
CLOUDFLARE_ZONE_ID=zone_id
CLOUDFLARE_TUNNEL_TOKEN=tunnel_token

# Notificaciones
NOTIFICATION_WEBHOOK_URL=https://hooks.slack.com/services/xxx/xxx/xxx
NOTIFICATION_WEBHOOK_SECRET=secreto_webhook

# Backups
BACKUP_ENCRYPTION_KEY=clave_encriptacion_backups_32_bytes_base64
BACKUP_GDRIVE_FOLDER_ID=id_carpeta_gdrive
BACKUP_S3_ENDPOINT=https://s3.region.amazonaws.com
BACKUP_S3_BUCKET=bucket-backups
BACKUP_S3_ACCESS_KEY=access_key
BACKUP_S3_SECRET_KEY=secret_key

# VeriFactu
VERIFACTU_PROVIDER=modulo_dolibarr
VERIFACTU_CERT_PATH=/etc/ssl/certs/verifactu.pem
VERIFACTU_KEY_PATH=/etc/ssl/private/verifactu.key
VERIFACTU_TEST_MODE=false

# Gestoría
GESTORIA_CONTACT_EMAIL=gestoria@empresa.es
GESTORIA_CONTACT_NAME=Gestoría XYZ
GESTORIA_COMPARISON_SCHEDULE=0 9 1 * *

# Monitoreo
GRAFANA_ADMIN_PASSWORD=clave_grafana_admin
PROMETHEUS_PORT=9090
GRAFANA_PORT=3001
LOKI_PORT=3100
TEMPO_PORT=3200
MIMIR_PORT=9009

# IA Local
OLLAMA_MODELS=llama3.1:8b,mistral:7b,codellama:7b
OLLAMA_HOST=ollama
OLLAMA_PORT=11434
VLLM_HOST=vllm
VLLM_PORT=8000

# Backups
BACKUP_SCHEDULE=0 2 * * *
BACKUP_RETENTION_DAYS=30
BACKUP_LOCAL_PATH=/backups

# Logs
LOG_LEVEL=INFO
LOG_FORMAT=json
```

### 5. Scripts de Despliegue

```bash
# scripts/deploy-prod.sh
#!/bin/bash
# Despliegue a producción

set -e

ENVIRONMENT=${1:-production}
COMPOSE_FILES="-f docker-compose.yml"

if [ "$ENVIRONMENT" = "production" ]; then
    COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.prod.yml"
fi

echo "🚀 Desplegando a $ENVIRONMENT..."

# 1. Pull imágenes
docker compose $COMPOSE_FILES pull

# 2. Build imágenes locales
docker compose $COMPOSE_FILES build --pull

# 3. Migraciones BD (si hay cambios)
# docker compose $COMPOSE_FILES run --rm api alembic upgrade head

# 4. Desplegar con zero-downtime
docker compose $COMPOSE_FILES up -d --remove-orphans

# 5. Health checks
sleep 30
./scripts/health-check.sh

# 6. Limpiar imágenes antiguas
docker image prune -f

echo "✅ Despliegue completado"
```

```bash
# scripts/health-check.sh
#!/bin/bash

check_service() {
    local name=$1
    local url=$2
    local max_attempts=5
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if curl -sf "$url" > /dev/null 2>&1; then
            echo "✅ $name: OK"
            return 0
        fi
        sleep 5
        attempt=$((attempt + 1))
    done
    
    echo "❌ $name: FALLÓ"
    return 1
}

echo "🔍 Verificando health checks..."

check_service "API" "https://api.empresa.es/health"
check_service "Aprobaciones" "https://approvals.empresa.es/health"
check_service "Dashboard" "https://dashboard.empresa.es/health"
check_service "Dolibarr" "https://erp.empresa.es/health"
check_service "Prometheus" "http://localhost:9090/-/healthy"
check_service "Grafana" "http://localhost:3001/api/health"
```

### 6. Backups Automatizados

```bash
# scripts/backup.sh
#!/bin/bash

set -e

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backups"
ENCRYPTION_KEY=$(cat /run/secrets/backup_encryption_key)

mkdir -p $BACKUP_DIR

# 1. Backup PostgreSQL (Auditoría)
echo "📦 Backup PostgreSQL..."
docker exec audit-db-prod pg_dump -U audit audit | gzip | \
    openssl enc -aes-256-cbc -salt -pbkdf2 -pass pass:"$ENCRYPTION_KEY" \
    > $BACKUP_DIR/audit_${DATE}.sql.gz.enc

# 2. Backup Redis
echo "📦 Backup Redis..."
docker exec redis-prod redis-cli -a $REDIS_PASSWORD --rdb /data/dump.rdb
docker cp redis-prod:/data/dump.rdb $BACKUP_DIR/redis_${DATE}.rdb
openssl enc -aes-256-cbc -salt -pbkdf2 -pass pass:"$ENCRYPTION_KEY" \
    -in $BACKUP_DIR/redis_${DATE}.rdb \
    -out $BACKUP_DIR/redis_${DATE}.rdb.enc
rm $BACKUP_DIR/redis_${DATE}.rdb

# 3. Backup Dolibarr (documentos + BD)
echo "📦 Backup Dolibarr..."
docker exec dolibarr-db-prod mysqldump -u dolibarr -p$DOLIBARR_DB_PASSWORD dolibarr | gzip | \
    openssl enc -aes-256-cbc -salt -pbkdf2 -pass pass:"$ENCRYPTION_KEY" \
    > $BACKUP_DIR/dolibarr_db_${DATE}.sql.gz.enc

docker cp dolibarr-prod:/var/www/documents $BACKUP_DIR/dolibarr_docs_${DATE}
tar czf $BACKUP_DIR/dolibarr_docs_${DATE}.tar.gz -C $BACKUP_DIR dolibarr_docs_${DATE}
openssl enc -aes-256-cbc -salt -pbkdf2 -pass pass:"$ENCRYPTION_KEY" \
    -in $BACKUP_DIR/dolibarr_docs_${DATE}.tar.gz \
    -out $BACKUP_DIR/dolibarr_docs_${DATE}.tar.gz.enc
rm -rf $BACKUP_DIR/dolibarr_docs_${DATE} $BACKUP_DIR/dolibarr_docs_${DATE}.tar.gz

# 4. Backup configuración
tar czf $BACKUP_DIR/config_${DATE}.tar.gz \
    .env.prod docker-compose.yml docker-compose.prod.yml \
    infra/ scripts/ config/

# 5. Subir a almacenamiento remoto (Google Drive / S3)
echo "☁️ Subiendo a almacenamiento remoto..."
# rclone copy $BACKUP_DIR gdrive:transvega-backups/ --include "*${DATE}*"
# aws s3 sync $BACKUP_DIR s3://bucket-backups/transvega/ --include "*${DATE}*"

# 5. Limpieza local (retener 30 días)
find $BACKUP_DIR -type f -mtime +30 -delete

echo "✅ Backup completado: $DATE"
```

```bash
# Crontab para backups
# 0 2 * * * /opt/transvega/scripts/backup.sh >> /var/log/backup.log 2>&1
```

### 7. Monitoreo y Alertas

```yaml
# infra/monitoring/alertmanager.yml
global:
  resolve_timeout: 5m
  smtp_smarthost: 'smtp.gmail.com:587'
  smtp_from: 'alertas@empresa.es'
  smtp_auth_username: 'alertas@empresa.es'
  smtp_auth_password: '${SMTP_PASSWORD}'

route:
  group_by: ['alertname', 'severity']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  receiver: 'default'
  routes:
    - match:
        severity: critical
      receiver: 'critical-alerts'
      continue: true
    - match:
        severity: warning
      receiver: 'warning-alerts'

receivers:
  - name: 'default'
    email_configs:
      - to: 'devops@empresa.es'
        send_resolved: true
    slack_configs:
      - api_url: '${SLACK_WEBHOOK_URL}'
        channel: '#alerts'
        send_resolved: true

  - name: 'critical-alerts'
    email_configs:
      - to: 'oncall@empresa.es'
        send_resolved: true
    slack_configs:
      - api_url: '${SLACK_WEBHOOK_URL}'
        channel: '#critical-alerts'
        send_resolved: true
    pagerduty_configs:
      - service_key: '${PAGERDUTY_KEY}'
        severity: critical

  - name: 'warning-alerts'
    email_configs:
      - to: 'devops@empresa.es'
        send_resolved: true
    slack_configs:
      - api_url: '${SLACK_WEBHOOK_URL}'
        channel: '#warnings'
        send_resolved: true

inhibit_rules:
  - source_match:
      severity: 'critical'
    target_match:
      severity: 'warning'
    equal: ['alertname', 'instance']
```

### 8. Checklist Pre-Producción

```markdown
## ✅ Checklist Pre-Producción

### Infraestructura
- [ ] VPS Dolibarr aprovisionado (4 vCPU, 8GB RAM, 100GB SSD)
- [ ] VPS API/Workers aprovisionado (4 vCPU, 16GB RAM, 100GB SSD)
- [ ] Equipo local Hermes configurado (32GB RAM, GPU RTX 3080+)
- [ ] Docker 24+ y Docker Compose 2+ en todos los servidores
- [ ] Dominio configurado en Cloudflare con NS delegados
- [ ] Cloudflare Tunnel creado y rutas DNS configuradas
- [ ] Cloudflare Access configurado con Google Workspace
- [ ] Certificados SSL via Let's Encrypt (Certbot)

### Seguridad
- [ ] Firewall configurado (solo puertos 80, 443, 22)
- [ ] Fail2ban configurado
- [ ] SSH solo con claves, root login deshabilitado
- [ ] Fail2ban para nginx/php
- [ ] Cloudflare WAF activado (OWASP Top 10)
- [ ] Rate limiting en nginx
- [ ] Secrets en archivos, no en variables de entorno
- [ ] Rotación de secretos documentada (90 días)

### Datos
- [ ] Dolibarr instalado y configurado (v20+)
- [ ] Módulo `expediente_animal` instalado y activado
- [ ] API Dolibarr habilitada y probada
- [ ] Usuarios API creados con permisos mínimos
- [ ] Módulos Dolibarr activados: facturacion, proveedores, productos, expediciones, contratos, banco, tva, sii, facturae, verifactu, fidelidad, importacion
- [ ] Datos ficticios eliminados, solo estructura

### API/Workers
- [ ] API FastAPI desplegada y health checks OK
- [ ] Workers Celery conectados a Redis
- [ ] Base de datos auditoría PostgreSQL inicializada
- [ ] Redis con persistencia AOF + RDB
- [ ] Aprobaciones funcionando (webhook notificaciones)
- [ ] Dashboard accesible via Cloudflare Access
- [ ] Ollama/Models cargados (llama3.1:8b, mistral:7b)
- [ ] vLLM opcional para alta carga

### Integraciones
- [ ] Google Workspace OAuth configurado
- [ ] Cloudflare Access policies por grupo
- [ ] Webhooks Dolibarr -> API configurados
- [ ] Email transaccional configurado (SendGrid/Mailgun/SMTP)
- [ ] Slack/Telegram para alertas

### Backup/DR
- [ ] Backup automático diario (2:00 AM)
- [ ] Backups cifrados (AES-256)
- [ ] Backups en 3 ubicaciones (local, GDrive, S3)
- [ ] Test de restauración mensual documentado
- [ ] Retención 30 días local, 1 año remoto
- [ ] Script de restauración documentado y probado

### Monitoreo
- [ ] Prometheus + Grafana + Loki + Tempo + Mimir
- [ ] Dashboards: Sistema, API, Business, Agentes
- [ ] Alertmanager configurado (email + Slack + PagerDuty)
- [ ] Alertas críticas: CPU>90%, RAM>90%, Disco>85%, API down, DB down
- [ ] Alertas warning: CPU>75%, RAM>80%, Cola>100 tareas
- [ ] Logs centralizados en Loki (retención 30 días)
- [ ] Traces en Tempo (retención 7 días)
- [ ] Métricas business: leads, reservas, ventas, facturación

### VeriFactu/Fiscal
- [ ] Módulo VeriFactu Dolibarr instalado
- [ ] Certificados FNMT/ACCV instalados
- [ ] Entorno pruebas AEAT configurado
- [ ] Gestoría validada para presentación oficial

### Documentación
- [ ] Runbooks para incidencias críticas
- [ ] Diagrama arquitectura actualizado
- [ ] Inventario de secretos y rotación
- [ ] Contactos de emergencia (DevOps, Gestoría, Proveedor VPS)
- [ ] Plan de contingencia (RTO < 4h, RPO < 1h)

### Testing
- [ ] Tests unitarios pasando (cobertura > 80%)
- [ ] Tests integración pasando
- [ ] Tests E2E pasando (happy path)
- [ ] Tests seguridad (bandit, trivy, dependency check)
- [ ] Load testing API (100 RPS sostenidos)
- [ ] Chaos engineering básico (matar contenedor, verificar recovery)
```

---

## 🚀 Comandos Rápidos de Referencia

```bash
# Ver logs
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f api

# Reiniciar servicio
docker compose -f docker-compose.yml -f docker-compose.prod.yml restart api

# Escalar workers
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --scale worker=4

# Ver estado
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps

# Backup manual
./scripts/backup.sh

# Restaurar backup
./scripts/restore.sh backup_20240115_020000

# Ver métricas
curl http://localhost:9090/api/v1/query?query=up

# Ver colas
docker exec redis-prod redis-cli -a $REDIS_PASSWORD CLIENT LIST
docker exec redis-prod redis-cli -a $REDIS_PASSWORD LLEN celery
```