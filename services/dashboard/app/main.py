"""
Dashboard Service - Main FastAPI application.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import structlog

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    logger.info("starting_dashboard", version="0.1.0")
    yield
    logger.info("shutting_down_dashboard")


app = FastAPI(
    title="Transvega Animal - Dashboard",
    description="Panel de control interno",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)


@app.get("/", response_class=HTMLResponse, tags=["Root"])
async def root():
    """Dashboard principal."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Transvega Animal - Dashboard</title>
        <style>
            body { font-family: system-ui; margin: 40px; background: #f5f5f5; }
            .container { max-width: 800px; margin: 0 auto; background: white; padding: 40px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            h1 { color: #1a1a2e; }
            .links { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; margin-top: 32px; }
            .link { padding: 20px; background: #f8f9fa; border-radius: 6px; text-decoration: none; color: #1a1a2e; border: 1px solid #e9ecef; transition: all 0.2s; }
            .link:hover { background: #e9ecef; border-color: #dee2e6; }
            .link h3 { margin: 0 0 8px; font-size: 18px; }
            .link p { margin: 0; font-size: 14px; color: #6c757d; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🐕 Transvega Animal - Dashboard</h1>
            <p>Panel de control interno para gestión de operaciones.</p>
            <div class="links">
                <a href="/api" class="link">
                    <h3>📚 API Docs (Swagger)</h3>
                    <p>Documentación interactiva de la API</p>
                </a>
                <a href="/redoc" class="link">
                    <h3>📖 ReDoc</h3>
                    <p>Documentación alternativa</p>
                </a>
                <a href="/health" class="link">
                    <h3>💚 Health Check</h3>
                    <p>Estado del servicio</p>
                </a>
                <a href="/metrics" class="link">
                    <h3>📊 Métricas</h3>
                    <p>Prometheus metrics endpoint</p>
                </a>
            </div>
        </div>
    </body>
    </html>
    """


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "dashboard",
        "version": "0.1.0",
    }


@app.get("/metrics", tags=["Metrics"])
async def metrics():
    """Prometheus metrics placeholder."""
    return "# Metrics placeholder\n"


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=3000, reload=True)