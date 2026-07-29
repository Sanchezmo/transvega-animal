# Transvega Animal - Sistema Empresarial Híbrido

Sistema de gestión para comercialización responsable y transporte de perros.

## Arquitectura

- **ERP/CRM**: Dolibarr (fuente oficial de datos)
- **Identidad/Colaboración**: Google Workspace
- **Seguridad/Red**: Cloudflare (DNS, WAF, Access, Tunnels)
- **Hosting**: VPS Hostinger (Dolibarr, API, MariaDB, Redis)
- **IA/Automatización**: Equipo local (Hermes + Agentes especializados)
- **API Intermedia**: FastAPI (única vía de acceso a Dolibarr)

## Requisitos

- Docker 24+
- Docker Compose 2+
- Python 3.11+
- Node.js 20+ (para dashboard)
- Cuenta Cloudflare con dominio delegado
- Google Workspace Business
- VPS Ubuntu 22.04/24.04

## Inicio Rápido

```bash
# 1. Configurar variables de entorno
cp .env.example .env.local
# Editar .env.local con valores reales

# 2. Levantar entorno de desarrollo
make up

# 3. Verificar servicios
make status

# 4. Ejecutar tests
make test

# 5. Sembrar datos de prueba
make seed
```

## Servicios en Desarrollo

| Servicio | Puerto | Descripción |
|----------|--------|-------------|
| API Integración | 8000 | FastAPI - API intermedia obligatoria |
| Mock Dolibarr | 8001 | Simulador Dolibarr para desarrollo |
| Dashboard | 3000 | Panel interno |
| Aprobaciones | 8002 | Sistema aprobaciones humanas |
| PostgreSQL (Auditoría) | 5433 | Base de datos auditoría |
| Redis | 6379 | Cola de tareas |

## Estructura del Proyecto

```
transvega-animal/
├── docs/                 # Documentación técnica
├── infrastructure/       # Docker, Cloudflare, Monitoring, Backups
├── services/             # Microservicios (API, Cola, Auditoría, Aprobaciones, Dashboard)
├── agents/               # Agentes especializados
├── adapters/             # Adaptadores externos (Dolibarr, Google, Cloudflare)
├── tests/                # Tests unitarios, integración, seguridad
├── scripts/              # Scripts de utilidad
├── config/               # Configuraciones YAML
└── docker-compose.yml    # Orquestación local
```

## Principios de Seguridad

- Dolibarr = única fuente oficial de datos
- Hermes NO accede directamente a BD Dolibarr
- Toda integración vía API controlada
- Aprobación humana obligatoria para acciones sensibles
- Secretos solo en `.env.local` (nunca en repo)
- Entornos separados: dev, staging, prod
- Auditoría inmutable en PostgreSQL separado

## Comandos Útiles

```bash
make up          # Levantar todo
make down        # Parar todo
make logs        # Ver logs
make test        # Ejecutar tests
make seed        # Datos ficticios
make shell-api   # Shell en contenedor API
make backup      # Backup auditoría
make restore     # Restaurar backup
```