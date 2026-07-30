---
name: milanuncios-bot
description: Bot Playwright para renovación diaria automática de anuncios en Milanuncios (orgánico, cero presupuesto). Incluye rate-limit, stealth, re-login, métricas Prometheus y alertas Telegram.
version: "1.0.0"
author: Hermes Agent
category: marketing
tags:
  - marketing
  - automation
  - playwright
  - milanuncios
  - organic
requires:
  - python>=3.11
  - playwright>=1.40
  - redis>=5.0
  - postgresql>=15
  - docker
entrypoint: bot/renew_all.py
schedule: "0 6 * * *"
config:
  MILANUNCIOS_USER: "required"
  MILANUNCIOS_PASS: "required"
  DATABASE_URL: "required"
  REDIS_URL: "redis://redis:6379/1"
  TELEGRAM_ALERT_CHAT_ID: "optional"
  TELEGRAM_BOT_TOKEN: "optional"
  RATE_LIMIT_PER_HOUR: "30"
  RATE_LIMIT_PER_MINUTE: "5"
  HEADLESS: "true"
  STEALTH_LEVEL: "high"
  STORAGE_STATE_PATH: "/app/storage_state.json"
  LOG_LEVEL: "INFO"
---

# Milanuncios Bot - Renovación Diaria Automática

Bot headless Playwright que renueva anuncios de perros en Milanuncios cada mañana a las 06:00.

## Arquitectura

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│  Cron 06:00 │────▶│  Playwright  │────▶│  Milanuncios    │
│  Trigger    │     │  Runner      │     │  (headless)     │
└─────────────┘     └──────────────┘     └─────────────────┘
                          │
                          ▼
                   ┌──────────────┐
                   │  Estado/Logs │
                   │  Redis + PG  │
                   └──────────────┘
```

## Flujo principal (`renew_all.py`)

1. Cargar anuncios con `status='active'` y `next_renewal <= now()` desde PostgreSQL
2. Para cada anuncio (rate-limited):
   - Abrir página con Playwright + stealth
   - Verificar si ya renovado hoy → skip
   - Click botón "Renovar" (selectores resilientes)
   - Confirmar modal si existe
   - Esperar toast éxito
   - Actualizar `last_renewed`, `renew_count++` en BD
3. Métricas Prometheus + alerta Telegram si errores críticos

## Manejo de bordes

| Problema | Mitigación |
|---|---|
| Captcha / challenge | `playwright-stealth` + UA rotativo + proxy residencial opcional. Pausa 15min + alerta |
| Login expirado / 2FA | `storage_state.json` persistente. Re-login auto si URL contiene `/login`. 2FA → alerta humano |
| Rate limit (30/h) | Token bucket Redis (`ratelimit:milanuncios:global`). Sleep exponencial + jitter |
| Anuncio borrado/caducado | Marcar `status='deleted'|'expired'`, no reintentar |
| Cambio UI selectores | Tests visuales semanales (screenshot diff) en CI |

## Estructura del skill

```
milanuncios-bot/
├── bot/
│   ├── __init__.py
│   ├── browser.py       # Playwright setup + stealth + storage_state
│   ├── auth.py          # login / load storage_state / re-login
│   ├── renew.py         # lógica renovación individual (robusta)
│   ├── renew_all.py     # orquestador + rate-limit + métricas
│   ├── models.py        # SQLAlchemy models (async)
│   ├── metrics.py       # Prometheus counters/histograms
│   └── alerts.py        # Telegram bot alerts
├── tests/
│   ├── test_browser.py
│   ├── test_auth.py
│   └── test_renew_flow.py
├── Dockerfile
├── requirements.txt
└── SKILL.md
```

## Despliegue

```yaml
# docker-compose.milanuncios.yml
services:
  milanuncios-bot:
    build: .
    container_name: milanuncios-bot
    environment:
      - MILANUNCIOS_USER=${MILANUNCIOS_USER}
      - MILANUNCIOS_PASS=${MILANUNCIOS_PASS}
      - DATABASE_URL=${DATABASE_URL}
      - REDIS_URL=${REDIS_URL}
      - TELEGRAM_ALERT_CHAT_ID=${TELEGRAM_ALERT_CHAT_ID}
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
      - HEADLESS=true
      - LOG_LEVEL=INFO
    volumes:
      - ./storage_state.json:/app/storage_state.json
    depends_on: [redis, db]
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 512M
```

## Métricas Prometheus (puerto 9090/metrics)

- `milanuncios_renew_ok_total` - renovaciones exitosas
- `milanuncios_renew_error_total` - errores por tipo (captcha, login, not_found, other)
- `milanuncios_renew_duration_seconds` - histograma latencia
- `milanuncios_captcha_hits_total` - desafíos detectados
- `milanuncios_active_ads` - gauge anuncios activos

## Alertas Telegram

Críticas (inmediato):
- Captcha detectado → pausa bot 15min
- Login fallido tras 3 reintentos
- Rate limit global alcanzado

Diarias (resumen 07:00):
- Renovados OK / errores / pendientes

## Próximos pasos

1. `docker compose -f docker-compose.milanuncios.yml up -d --build`
2. Verificar logs: `docker logs -f milanuncios-bot`
3. Probar 1 renovación manual en staging (headful: `HEADLESS=false`)
4. Configurar alertas Telegram reales