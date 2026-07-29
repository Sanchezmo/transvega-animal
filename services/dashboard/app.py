"""
Dashboard Service - Panel de control interno (FastAPI + HTMX/Alpine.js).
"""
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, date, timedelta
import structlog
import httpx

logger = structlog.get_logger()

app = FastAPI(
    title="Transvega Dashboard",
    description="Panel de control interno Transvega Animal",
    version="1.0.0",
)

# Templates y static files
templates = Jinja2Templates(directory="services/dashboard/templates")
# app.mount("/static", StaticFiles(directory="services/dashboard/static"), name="static")

# Configuración
API_URL = "http://api:8000"
APPROVALS_URL = "http://approvals:8002"

# =============================================================================
# MODELOS
# =============================================================================

class LoginRequest(BaseModel):
    username: str
    password: str

class ApprovalDecision(BaseModel):
    approved: bool
    comment: Optional[str] = None

# =============================================================================
# AUTENTICACIÓN SIMPLE (SESSION-BASED)
# =============================================================================

# En producción: JWT + secure cookies + Cloudflare Access
USERS_DB = {
    "admin": {"password": "admin123", "role": "admin", "name": "Administrador"},
    "supervisor": {"password": "super123", "role": "supervisor", "name": "Supervisor"},
    "comercial": {"password": "comercial123", "role": "sales", "name": "Comercial"},
    "logistica": {"password": "logistica123", "role": "logistics", "name": "Logística"},
}

def verify_user(username: str, password: str) -> Optional[Dict]:
    user = USERS_DB.get(username)
    if user and user["password"] == password:
        return {"username": username, **user}
    return None

def get_current_user(request: Request) -> Optional[Dict]:
    # En producción: validar JWT cookie
    # Por ahora: header simple
    auth = request.headers.get("X-User")
    if auth and auth in USERS_DB:
        return {"username": auth, **USERS_DB[auth]}
    return None

# =============================================================================
# HEALTH CHECKS
# =============================================================================

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "dashboard", "version": "1.0.0"}

# =============================================================================
# LOGIN / LOGOUT
# =============================================================================

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login(request: Request, username: str, password: str):
    user = verify_user(username, password)
    if not user:
        raise HTTPException(status_code=401, detail="Credenciales inválidas")
    
    # En producción: crear JWT token, set secure cookie
    response = JSONResponse({"success": True, "redirect": "/"})
    response.set_cookie("user", user["username"], httponly=True, secure=True)
    return response

@app.post("/logout")
async def logout():
    response = JSONResponse({"success": True})
    response.delete_cookie("user")
    return response

# =============================================================================
# DASHBOARD PRINCIPAL
# =============================================================================

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, user: Optional[Dict] = Depends(get_current_user)):
    if not user:
        return templates.TemplateResponse("login.html", {"request": request}, status_code=302)
    
    # Obtener métricas de la API
    async with httpx.AsyncClient() as client:
        try:
            # Health check API
            api_health = await client.get(f"{API_URL}/health/ready", timeout=5.0)
            api_status = "healthy" if api_health.status_code == 200 else "degraded"
        except:
            api_status = "down"
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user,
        "api_status": api_status,
        "current_date": datetime.now().strftime("%d/%m/%Y %H:%M"),
    })

# =============================================================================
# PANEL DE EXPEDIENTES
# =============================================================================

@app.get("/expedientes", response_class=HTMLResponse)
async def expedientes_page(request: Request, user: Optional[Dict] = Depends(get_current_user)):
    if not user:
        return templates.TemplateResponse("login.html", {"request": request}, status_code=302)
    
    # Obtener expedientes de la API
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{API_URL}/api/v1/expedientes", timeout=10.0)
            expedientes = resp.json().get("data", []) if resp.status_code == 200 else []
        except:
            expedientes = []
    
    return templates.TemplateResponse("expedientes.html", {
        "request": request,
        "user": user,
        "expedientes": expedientes,
    })

@app.get("/expedientes/{expediente_id}", response_class=HTMLResponse)
async def expediente_detail(request: Request, expediente_id: int, user: Optional[Dict] = Depends(get_current_user)):
    if not user:
        return templates.TemplateResponse("login.html", {"request": request}, status_code=302)
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{API_URL}/api/v1/expedientes/{expediente_id}", timeout=10.0)
            expediente = resp.json() if resp.status_code == 200 else None
        except:
            expediente = None
    
    if not expediente:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")
    
    return templates.TemplateResponse("expediente_detail.html", {
        "request": request,
        "user": user,
        "expediente": expediente,
    })

# =============================================================================
# PANEL DE APROBACIONES
# =============================================================================

@app.get("/aprobaciones", response_class=HTMLResponse)
async def aprobaciones_page(request: Request, user: Optional[Dict] = Depends(get_current_user)):
    if not user:
        return templates.TemplateResponse("login.html", {"request": request}, status_code=302)
    
    # Solo admins/supervisores
    if user["role"] not in ["admin", "supervisor"]:
        raise HTTPException(status_code=403, detail="No autorizado")
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{APPROVALS_URL}/api/v1/aprobaciones/pendientes", timeout=10.0)
            aprobaciones = resp.json().get("data", []) if resp.status_code == 200 else []
        except:
            aprobaciones = []
    
    return templates.TemplateResponse("aprobaciones.html", {
        "request": request,
        "user": user,
        "aprobaciones": aprobaciones,
    })

@app.post("/aprobaciones/{approval_id}/aprobar")
async def aprobar_aprobacion(approval_id: str, decision: ApprovalDecision, user: Optional[Dict] = Depends(get_current_user)):
    if not user or user["role"] not in ["admin", "supervisor"]:
        raise HTTPException(status_code=403, detail="No autorizado")
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{APPROVALS_URL}/api/v1/aprobaciones/{approval_id}/aprobar",
            json=decision.model_dump(),
            timeout=10.0,
        )
        return resp.json()

@app.post("/aprobaciones/{approval_id}/rechazar")
async def rechazar_aprobacion(approval_id: str, decision: ApprovalDecision, user: Optional[Dict] = Depends(get_current_user)):
    if not user or user["role"] not in ["admin", "supervisor"]:
        raise HTTPException(status_code=403, detail="No autorizado")
    
    if not decision.approved and not decision.comment:
        raise HTTPException(status_code=400, detail="Comentario requerido al rechazar")
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{APPROVALS_URL}/api/v1/aprobaciones/{approval_id}/rechazar",
            json=decision.model_dump(),
            timeout=10.0,
        )
        return resp.json()

# =============================================================================
# PANEL COMERCIAL
# =============================================================================

@app.get("/comercial", response_class=HTMLResponse)
async def comercial_page(request: Request, user: Optional[Dict] = Depends(get_current_user)):
    if not user:
        return templates.TemplateResponse("login.html", {"request": request}, status_code=302)
    
    if user["role"] not in ["admin", "supervisor", "sales"]:
        raise HTTPException(status_code=403, detail="No autorizado")
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{API_URL}/api/v1/comercial/leads", timeout=10.0)
            leads = resp.json().get("data", []) if resp.status_code == 200 else []
        except:
            leads = []
    
    return templates.TemplateResponse("comercial.html", {
        "request": request,
        "user": user,
        "leads": leads,
    })

# =============================================================================
# PANEL DE FACTURACIÓN
# =============================================================================

@app.get("/facturacion", response_class=HTMLResponse)
async def facturacion_page(request: Request, user: Optional[Dict] = Depends(get_current_user)):
    if not user:
        return templates.TemplateResponse("login.html", {"request": request}, status_code=302)
    
    if user["role"] not in ["admin", "supervisor", "accounting", "invoicing"]:
        raise HTTPException(status_code=403, detail="No autorizado")
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{API_URL}/api/v1/facturas", timeout=10.0)
            facturas = resp.json().get("data", []) if resp.status_code == 200 else []
        except:
            facturas = []
    
    return templates.TemplateResponse("facturacion.html", {
        "request": request,
        "user": user,
        "facturas": facturas,
    })

# =============================================================================
# PANEL DE MONITORIZACIÓN
# =============================================================================

@app.get("/monitoreo", response_class=HTMLResponse)
async def monitoreo_page(request: Request, user: Optional[Dict] = Depends(get_current_user)):
    if not user:
        return templates.TemplateResponse("login.html", {"request": request}, status_code=302)
    
    if user["role"] not in ["admin", "supervisor", "technical"]:
        raise HTTPException(status_code=403, detail="No autorizado")
    
    return templates.TemplateResponse("monitoreo.html", {
        "request": request,
        "user": user,
        "grafana_url": "http://grafana:3000",
        "prometheus_url": "http://prometheus:9090",
    })

# =============================================================================
# API ENDPOINTS PARA AJAX
# =============================================================================

@app.get("/api/dashboard/stats")
async def dashboard_stats(user: Optional[Dict] = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=401)
    
    async with httpx.AsyncClient() as client:
        try:
            # Obtener stats de varias APIs
            stats = {}
            
            # Expedientes
            resp = await httpx.AsyncClient().get(f"{API_URL}/api/v1/expedientes?limit=1", timeout=5.0)
            if resp.status_code == 200:
                stats["total_expedientes"] = resp.json().get("total", 0)
            
            # Leads
            resp = await httpx.AsyncClient().get(f"{API_URL}/api/v1/comercial/leads?limit=1", timeout=5.0)
            if resp.status_code == 200:
                stats["total_leads"] = resp.json().get("total", 0)
            
            # Facturas pendientes
            resp = await httpx.AsyncClient().get(f"{API_URL}/api/v1/facturas?status=0&limit=1", timeout=5.0)
            if resp.status_code == 200:
                stats["facturas_borrador"] = resp.json().get("total", 0)
            
            # Aprobaciones pendientes
            resp = await httpx.AsyncClient().get(f"{APPROVALS_URL}/api/v1/aprobaciones/pendientes?limit=1", timeout=5.0)
            if resp.status_code == 200:
                stats["aprobaciones_pendientes"] = resp.json().get("total", 0)
            
            return {"success": True, "stats": stats}
        except:
            return {"success": False, "error": "Error obteniendo estadísticas"}

@app.get("/api/aprobaciones/pendientes")
async def api_aprobaciones_pendientes(user: Optional[Dict] = Depends(get_current_user)):
    if not user or user["role"] not in ["admin", "supervisor"]:
        raise HTTPException(status_code=403)
    
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{APPROVALS_URL}/api/v1/aprobaciones/pendientes", timeout=10.0)
        if resp.status_code == 200:
            return resp.json()
        return {"success": False, "data": []}

# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)