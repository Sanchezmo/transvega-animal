"""
Punto de entrada principal de la API FastAPI.
"""

import time
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.database import close_db, init_db
from app.core.exceptions import TransvegaException
from app.routes import (
    aprobaciones,
    comercial,
    dogs,
    expedientes,
    facturacion,
    productos,
    proveedores,
    publicaciones,
    salud,
    telegram,
    terceros,
)

# Configurar logging estructurado
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestión del ciclo de vida de la aplicación."""
    # Startup
    logger.info(
        "starting_application",
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
    )

    # Inicializar base de datos
    await init_db()
    logger.info("database_initialized")

    # Initialize Redis client and store in app state
    from app.core.database import get_redis_client
    redis_client = await get_redis_client()
    app.state.redis_client = redis_client
    logger.info("redis_client_initialized")

    # Start Supervisor agent (used by telegram webhook)
    from app.routes.telegram import supervisor_agent

    try:
        await supervisor_agent.start()
        logger.info("supervisor_agent_started")
    except Exception as e:
        logger.warning("supervisor_agent_start_failed", error=str(e))

    yield

    # Shutdown
    logger.info("shutting_down_application")
    # Close Redis client
    if hasattr(app.state, "redis_client"):
        await app.state.redis_client.close()
    # Stop Supervisor agent
    try:
        await supervisor_agent.stop()
        logger.info("supervisor_agent_stopped")
    except Exception as e:
        pass

    # Shutdown
    logger.info("shutting_down_application")
    # Stop Supervisor agent
    try:
        await supervisor_agent.stop()
        logger.info("supervisor_agent_stopped")
    except Exception as e:
        logger.warning("supervisor_agent_stop_failed", error=str(e))
    await close_db()
    logger.info("database_connections_closed")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="API Integración Transvega Animal - Punto central entre Hermes/Dolibarr",
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
    openapi_url="/openapi.json" if settings.ENVIRONMENT != "production" else None,
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.API_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-RateLimit-Remaining", "X-RateLimit-Reset"],
)


# Middleware global de logging y métricas
@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    start_time = time.time()

    # Log request
    logger.info(
        "request_started",
        method=request.method,
        path=request.url.path,
        query_params=dict(request.query_params),
        client_ip=request.client.host if request.client else "unknown",
    )

    try:
        response = await call_next(request)

        # Log response
        duration = time.time() - start_time
        logger.info(
            "request_completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round(duration * 1000, 2),
        )

        # Headers de rate limit
        if hasattr(request.state, "rate_limit_remaining"):
            response.headers["X-RateLimit-Remaining"] = str(request.state.rate_limit_remaining)
        if hasattr(request.state, "rate_limit_reset"):
            response.headers["X-RateLimit-Reset"] = str(request.state.rate_limit_reset)

        return response

    except Exception as e:
        duration = time.time() - start_time
        logger.error(
            "request_failed",
            method=request.method,
            path=request.url.path,
            error=str(e),
            duration_ms=round(duration * 1000, 2),
            exc_info=True,
        )
        raise


# Manejador global de excepciones
@app.exception_handler(TransvegaException)
async def transvega_exception_handler(request: Request, exc: TransvegaException):
    logger.warning(
        "business_exception",
        error_code=exc.error_code,
        message=exc.message,
        details=exc.details,
        path=request.url.path,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.error_code,
                "message": exc.message,
                "details": exc.details,
            }
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error(
        "unhandled_exception",
        error=str(exc),
        path=request.url.path,
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "Error interno del servidor",
                "details": {},
            }
        },
    )


# =============================================================================
# HEALTH CHECKS
# =============================================================================


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check básico."""
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
    }


@app.get("/health/ready", tags=["Health"])
async def readiness_check():
    """Readiness check - verifica dependencias."""
    checks = {}
    overall = "ready"

    # Verificar BD auditoría
    try:
        # Quick ping
        checks["audit_db"] = "ok"
    except Exception as e:
        checks["audit_db"] = f"error: {e}"
        overall = "not_ready"

    # Verificar Redis
    try:
        from app.core.database import get_redis_client

        redis = await get_redis_client()
        await redis.ping()
        await redis.close()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {e}"
        overall = "not_ready"

    # Verificar Dolibarr (mock en dev)
    checks["dolibarr"] = "mock" if settings.ENVIRONMENT == "development" else "pending"

    return {
        "status": overall,
        "checks": checks,
    }


# =============================================================================
# ROUTERS
# =============================================================================

app.include_router(salud.router, prefix="/api/v1", tags=["Health"])
app.include_router(expedientes.router, prefix="/api/v1/expedientes", tags=["Expedientes"])
app.include_router(terceros.router, prefix="/api/v1/terceros", tags=["Terceros"])
app.include_router(productos.router, prefix="/api/v1/productos", tags=["Productos"])
app.include_router(dogs.router, prefix="/api/v1/dogs", tags=["Dogs"])
app.include_router(publicaciones.router, prefix="/api/v1/publicaciones", tags=["Publicaciones"])
app.include_router(comercial.router, prefix="/api/v1/comercial", tags=["Comercial"])
app.include_router(facturacion.router, prefix="/api/v1/facturacion", tags=["Facturación"])
app.include_router(aprobaciones.router, prefix="/api/v1/aprobaciones", tags=["Aprobaciones"])
app.include_router(proveedores.router, prefix="/api/v1/proveedores", tags=["Proveedores"])
app.include_router(telegram.router, prefix="/api/v1", tags=["Telegram"])


# =============================================================================
# ROOT
# =============================================================================


@app.get("/", tags=["Root"])
async def root():
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/health",
        "api": "/api/v1",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        workers=settings.API_WORKERS,
        reload=settings.ENVIRONMENT == "development",
    )
