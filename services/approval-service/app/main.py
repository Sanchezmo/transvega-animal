"""Approval Service - Main FastAPI application."""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import structlog

from app.core.config import settings
from app.core.database import init_db, close_db
from app.routes import approvals, health

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("starting_approval_service", version=settings.APP_VERSION, environment=settings.ENVIRONMENT)
    await init_db()
    logger.info("approval_service_started")
    
    yield
    
    # Shutdown
    logger.info("shutting_down_approval_service")
    await close_db()
    logger.info("approval_service_stopped")


app = FastAPI(
    title="Transvega Animal - Approval Service",
    description="Human approval workflow for sensitive operations",
    version="0.1.0",
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "error": exc.detail},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.exception("unhandled_exception", path=request.url.path, error=str(exc))
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": "Internal server error"},
    )


# Include routers
app.include_router(health.router, prefix="/health", tags=["Health"])
app.include_router(approvals.router, tags=["Approvals"])


@app.get("/")
async def root():
    return {
        "service": "approval-service",
        "version": "0.1.0",
        "status": "running",
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8002, reload=True)