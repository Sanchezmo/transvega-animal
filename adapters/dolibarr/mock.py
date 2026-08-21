"""
Mock Dolibarr API para desarrollo - Simula endpoints Dolibarr reales.
"""

import json
import os
from datetime import date, datetime
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Mock Dolibarr API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MOCK_API_KEY = os.getenv("MOCK_API_KEY", "mock-dolibarr-key-12345")
MOCK_DELAY_MS = int(os.getenv("MOCK_DELAY_MS", "100"))
MOCK_ERROR_RATE = float(os.getenv("MOCK_ERROR_RATE", "0.0"))

# Base de datos en memoria
mock_data = {
    "thirdparties": [],
    "products": [],
    "expedientes_animal": [],
    "invoices": [],
    "orders": [],
    "propals": [],
    "shipments": [],
}

# Cargar fixtures si existen
FIXTURES_PATH = "/app/fixtures"


def load_fixtures():
    """Cargar datos de prueba desde archivos JSON."""
    global mock_data
    if os.path.exists(FIXTURES_PATH):
        for filename in os.listdir(FIXTURES_PATH):
            if filename.endswith(".json"):
                key = filename.replace(".json", "")
                # Skip thirdparties fixture to keep generated data + test entries
                if key == "thirdparties":
                    continue
                with open(os.path.join(FIXTURES_PATH, filename)) as f:
                    mock_data[key] = json.load(f)
    
    # Add test supplier and client for staging tests


def add_test_supplier():
    """Add the staging test supplier and client to mock data if not exists."""
    global mock_data
    test_vat = "B99999999"
    exists_supplier = any(t.get("vat_number") == test_vat for t in mock_data.get("thirdparties", []))
    if not exists_supplier:
        new_id = max([t["id"] for t in mock_data.get("thirdparties", [])], default=0) + 1
        test_supplier = {
            "id": new_id,
            "ref": f"STAGING-TEST-{new_id:03d}",
            "name": "STAGING SUPPLIER TEST",
            "name_alias": "STAGING TEST",
            "email": "test@staging.com",
            "phone": "+34911111111",
            "address": "Calle Test 123, 28001 Madrid",
            "zip": "28001",
            "town": "Madrid",
            "country_id": 195,
            "country_code": "ES",
            "client": 0,
            "supplier": 1,
            "status": 1,
            "vat_number": test_vat,
            "default_lang": "es_ES",
            "datec": "2026-08-20T21:13:21.149935",
            "datem": "2026-08-20T21:13:21.149943"
        }
        mock_data.setdefault("thirdparties", []).append(test_supplier)
        print(f"Added test supplier: {test_supplier['name']} (VAT: {test_vat})")
    
    # Also add a test client for seed_fake_data
    test_client_vat = "C88888888"
    exists_client = any(t.get("vat_number") == test_client_vat for t in mock_data.get("thirdparties", []))
    if not exists_client:
        new_id = max([t["id"] for t in mock_data.get("thirdparties", [])], default=0) + 1
        test_client = {
            "id": new_id,
            "ref": f"STAGING-CLIENT-{new_id:03d}",
            "name": "STAGING CLIENT TEST",
            "name_alias": "STAGING CLIENT",
            "email": "client@staging.com",
            "phone": "+34911111112",
            "address": "Calle Client 456, 28002 Madrid",
            "zip": "28002",
            "town": "Madrid",
            "country_id": 195,
            "country_code": "ES",
            "client": 1,
            "supplier": 0,
            "status": 1,
            "vat_number": test_client_vat,
            "default_lang": "es_ES",
            "datec": "2026-08-20T21:13:21.149935",
            "datem": "2026-08-20T21:13:21.149943"
        }
        mock_data.setdefault("thirdparties", []).append(test_client)
        print(f"Added test client: {test_client['name']} (VAT: {test_client_vat})")


load_fixtures()


def verify_api_key(dolibarr_api_key: str = Header(..., alias="DOLAPIKEY")):
    """Verificar API key Dolibarr."""
    if dolibarr_api_key != MOCK_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return dolibarr_api_key


def simulate_delay():
    """Simular latencia de red."""
    import asyncio
    import random

    if MOCK_DELAY_MS > 0:
        delay = MOCK_DELAY_MS / 1000 * (0.5 + random.random())
        return asyncio.sleep(delay)
    return asyncio.sleep(0)


def maybe_error():
    """Simular errores aleatorios."""
    import random

    if random.random() < MOCK_ERROR_RATE:
        raise HTTPException(status_code=500, detail="Simulated Dolibarr error")


# =============================================================================
# MODELOS PYDANTIC (Simplificados)
# =============================================================================


class ThirdPartyBase(BaseModel):
    name: str
    name_alias: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    zip: str | None = None
    town: str | None = None
    country_id: int | None = None
    country_code: str | None = None
    state_id: int | None = None
    client: int = 1
    supplier: int = 0
    status: int = 1
    vat_number: str | None = None
    default_lang: str | None = "es_ES"


class ThirdPartyCreate(ThirdPartyBase):
    pass


class ThirdParty(ThirdPartyBase):
    id: int
    ref: str
    ref_ext: str | None = None
    canvas: str | None = None
    datec: datetime
    datem: datetime
    fk_user_author: int = 1
    fk_user_modif: int = 1

    class Config:
        from_attributes = True


class ProductBase(BaseModel):
    ref: str
    label: str
    description: str | None = None
    price: float = 0.0
    price_ttc: float = 0.0
    tva_tx: float = 21.0
    buy_price: float = 0.0
    weight: float = 0.0
    weight_units: int = 1
    status: int = 1
    type: int = 0  # 0=product, 1=service
    fk_product_type: int | None = None


class ProductCreate(ProductBase):
    pass


class Product(ProductBase):
    id: int
    ref_ext: str | None = None
    datec: datetime
    datem: datetime

    class Config:
        from_attributes = True


class ExpedienteAnimalBase(BaseModel):
    """Modelo para expediente animal personalizado."""

    name: str
    species: str = "perro"
    breed: str
    sex: str  # M/H
    birth_date: date
    color: str
    weight_kg: float
    microchip: str
    breeder_id: int | None = None
    breeder_registration: str | None = None
    zoological_nucleus: str | None = None
    country_origin: str = "ES"
    place_origin: str | None = None
    sire_name: str | None = None
    dam_name: str | None = None
    pedigree: str | None = None
    vet_status: str = "healthy"
    vaccines: list[dict[str, Any]] = []
    deworming: list[dict[str, Any]] = []
    passport: str | None = None
    certificates: list[dict[str, Any]] = []
    photos: list[str] = []
    videos: list[str] = []
    purchase_price: float = 0.0
    sale_price: float = 0.0
    associated_costs: float = 0.0
    commercial_status: str = "draft"  # draft, pending_docs, pending_review, available, published, reserved, paid, preparing_transport, in_transport, delivered, post_sale, unavailable, archived
    client_id: int | None = None
    reservation_id: int | None = None
    order_id: int | None = None
    invoice_id: int | None = None
    transport_id: int | None = None
    expected_delivery_date: date | None = None
    actual_delivery_date: date | None = None
    incidents: list[dict[str, Any]] = []
    post_sale_followup: list[dict[str, Any]] = []


class ExpedienteAnimalCreate(ExpedienteAnimalBase):
    pass


class ExpedienteAnimal(ExpedienteAnimalBase):
    id: int
    internal_id: str
    created_at: datetime
    updated_at: datetime
    created_by: int = 1
    updated_by: int = 1

    class Config:
        from_attributes = True


class InvoiceLine(BaseModel):
    product_id: int
    description: str
    qty: float = 1.0
    unit_price: float
    vat_rate: float = 21.0
    discount_percent: float = 0.0


class InvoiceBase(BaseModel):
    thirdparty_id: int
    date: date
    lines: list[InvoiceLine]
    status: int = 0  # 0=draft, 1=validated
    payment_term_id: int | None = None
    cond_reglement_id: int | None = None
    mode_reglement_id: int | None = None
    note_private: str | None = None
    note_public: str | None = None


class InvoiceCreate(InvoiceBase):
    pass


class Invoice(InvoiceBase):
    id: int
    ref: str
    total_ht: float
    total_tva: float
    total_ttc: float
    datec: datetime
    datem: datetime
    fk_user_author: int = 1
    fk_user_modif: int = 1

    class Config:
        from_attributes = True


# =============================================================================
# ENDPOINTS
# =============================================================================


@app.get("/health")
async def health_check():
    await simulate_delay()
    return {"status": "ok", "service": "mock-dolibarr", "version": "1.0.0"}


# -----------------------------------------------------------------------------
# TERCEROS (CLIENTES/PROVEEDORES)
# -----------------------------------------------------------------------------


@app.get("/thirdparties", dependencies=[Depends(verify_api_key)])
async def list_thirdparties(
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    sqlfilters: str | None = None,
    sortfield: str = "rowid",
    sortorder: str = "ASC",
):
    await simulate_delay()
    maybe_error()

    items = mock_data["thirdparties"][offset : offset + limit]
    return {"success": True, "data": items, "total": len(mock_data["thirdparties"])}


@app.get("/thirdparties/{thirdparty_id}", dependencies=[Depends(verify_api_key)])
async def get_thirdparty(thirdparty_id: int):
    await simulate_delay()
    maybe_error()

    tp = next((t for t in mock_data["thirdparties"] if t["id"] == thirdparty_id), None)
    if not tp:
        raise HTTPException(status_code=404, detail="Thirdparty not found")
    return {"success": True, "data": tp}


@app.post("/thirdparties", dependencies=[Depends(verify_api_key)])
async def create_thirdparty(thirdparty: ThirdPartyCreate):
    await simulate_delay()
    maybe_error()

    new_id = max([t["id"] for t in mock_data["thirdparties"]], default=0) + 1
    ref = f"CLI-{new_id:06d}"

    new_tp = {
        **thirdparty.dict(),
        "id": new_id,
        "ref": ref,
        "datec": datetime.now().isoformat(),
        "datem": datetime.now().isoformat(),
    }
    mock_data["thirdparties"].append(new_tp)

    return {"success": True, "data": new_tp, "id": new_id}


@app.put("/thirdparties/{thirdparty_id}", dependencies=[Depends(verify_api_key)])
async def update_thirdparty(thirdparty_id: int, thirdparty: ThirdPartyCreate):
    await simulate_delay()
    maybe_error()

    for i, tp in enumerate(mock_data["thirdparties"]):
        if tp["id"] == thirdparty_id:
            updated = {**tp, **thirdparty.dict(), "datem": datetime.now().isoformat()}
            mock_data["thirdparties"][i] = updated
            return {"success": True, "data": updated}

    raise HTTPException(status_code=404, detail="Thirdparty not found")


@app.delete("/thirdparties/{thirdparty_id}", dependencies=[Depends(verify_api_key)])
async def delete_thirdparty(thirdparty_id: int):
    await simulate_delay()
    maybe_error()

    global mock_data
    mock_data["thirdparties"] = [t for t in mock_data["thirdparties"] if t["id"] != thirdparty_id]
    return {"success": True}


# -----------------------------------------------------------------------------
# PRODUCTOS/SERVICIOS
# -----------------------------------------------------------------------------


@app.get("/products", dependencies=[Depends(verify_api_key)])
async def list_products(
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
):
    await simulate_delay()
    maybe_error()

    items = mock_data["products"][offset : offset + limit]
    return {"success": True, "data": items, "total": len(mock_data["products"])}


@app.get("/products/{product_id}", dependencies=[Depends(verify_api_key)])
async def get_product(product_id: int):
    await simulate_delay()
    maybe_error()

    prod = next((p for p in mock_data["products"] if p["id"] == product_id), None)
    if not prod:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"success": True, "data": prod}


@app.post("/products", dependencies=[Depends(verify_api_key)])
async def create_product(product: ProductCreate):
    await simulate_delay()
    maybe_error()

    new_id = max([p["id"] for p in mock_data["products"]], default=0) + 1
    new_prod = {
        **product.dict(),
        "id": new_id,
        "datec": datetime.now().isoformat(),
        "datem": datetime.now().isoformat(),
    }
    mock_data["products"].append(new_prod)
    return {"success": True, "data": new_prod, "id": new_id}


@app.put("/products/{product_id}", dependencies=[Depends(verify_api_key)])
async def update_product(product_id: int, product: ProductCreate):
    await simulate_delay()
    maybe_error()

    for i, p in enumerate(mock_data["products"]):
        if p["id"] == product_id:
            updated = {**p, **product.dict(), "datem": datetime.now().isoformat()}
            mock_data["products"][i] = updated
            return {"success": True, "data": updated}

    raise HTTPException(status_code=404, detail="Product not found")


# -----------------------------------------------------------------------------
# EXPEDIENTES ANIMALES (Módulo personalizado)
# -----------------------------------------------------------------------------


@app.get("/expedientes-animal", dependencies=[Depends(verify_api_key)])
async def list_expedientes(
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    status: str | None = None,
):
    await simulate_delay()
    maybe_error()

    items = mock_data["expedientes_animal"]
    if status:
        items = [e for e in items if e.get("commercial_status") == status]

    return {"success": True, "data": items[offset : offset + limit], "total": len(items)}


@app.get("/expedientes-animal/{expediente_id}", dependencies=[Depends(verify_api_key)])
async def get_expediente(expediente_id: int):
    await simulate_delay()
    maybe_error()

    exp = next((e for e in mock_data["expedientes_animal"] if e["id"] == expediente_id), None)
    if not exp:
        raise HTTPException(status_code=404, detail="Expediente not found")
    return {"success": True, "data": exp}


@app.post("/expedientes-animal", dependencies=[Depends(verify_api_key)])
async def create_expediente(expediente: ExpedienteAnimalCreate):
    await simulate_delay()
    maybe_error()

    new_id = max([e["id"] for e in mock_data["expedientes_animal"]], default=0) + 1
    internal_id = f"EXP-{datetime.now().year}-{new_id:06d}"

    new_exp = {
        **expediente.dict(),
        "id": new_id,
        "internal_id": internal_id,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }
    mock_data["expedientes_animal"].append(new_exp)
    return {"success": True, "data": new_exp, "id": new_id}


@app.put("/expedientes-animal/{expediente_id}", dependencies=[Depends(verify_api_key)])
async def update_expediente(expediente_id: int, expediente: ExpedienteAnimalCreate):
    await simulate_delay()
    maybe_error()

    for i, e in enumerate(mock_data["expedientes_animal"]):
        if e["id"] == expediente_id:
            updated = {**e, **expediente.dict(), "updated_at": datetime.now().isoformat()}
            mock_data["expedientes_animal"][i] = updated
            return {"success": True, "data": updated}

    raise HTTPException(status_code=404, detail="Expediente not found")


@app.delete("/expedientes-animal/{expediente_id}", dependencies=[Depends(verify_api_key)])
async def delete_expediente(expediente_id: int):
    await simulate_delay()
    maybe_error()

    global mock_data
    mock_data["expedientes_animal"] = [e for e in mock_data["expedientes_animal"] if e["id"] != expediente_id]
    return {"success": True}


# -----------------------------------------------------------------------------
# FACTURAS
# -----------------------------------------------------------------------------


@app.get("/invoices", dependencies=[Depends(verify_api_key)])
async def list_invoices(
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    status: int | None = None,
):
    await simulate_delay()
    maybe_error()

    items = mock_data["invoices"]
    if status is not None:
        items = [i for i in items if i.get("status") == status]

    return {"success": True, "data": items[offset : offset + limit], "total": len(items)}


@app.get("/invoices/{invoice_id}", dependencies=[Depends(verify_api_key)])
async def get_invoice(invoice_id: int):
    await simulate_delay()
    maybe_error()

    inv = next((i for i in mock_data["invoices"] if i["id"] == invoice_id), None)
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return {"success": True, "data": inv}


@app.post("/invoices", dependencies=[Depends(verify_api_key)])
async def create_invoice(invoice: InvoiceCreate):
    await simulate_delay()
    maybe_error()

    new_id = max([i["id"] for i in mock_data["invoices"]], default=0) + 1
    ref = f"FAC-{datetime.now().year}-{new_id:06d}"

    # Calcular totales
    total_ht = sum(l.qty * l.unit_price * (1 - l.discount_percent / 100) for l in invoice.lines)
    total_tva = sum(l.qty * l.unit_price * (1 - l.discount_percent / 100) * l.vat_rate / 100 for l in invoice.lines)
    total_ttc = total_ht + total_tva

    new_inv = {
        **invoice.dict(),
        "id": new_id,
        "ref": ref,
        "total_ht": round(total_ht, 2),
        "total_tva": round(total_tva, 2),
        "total_ttc": round(total_ttc, 2),
        "datec": datetime.now().isoformat(),
        "datem": datetime.now().isoformat(),
    }
    mock_data["invoices"].append(new_inv)
    return {"success": True, "data": new_inv, "id": new_id}


@app.put("/invoices/{invoice_id}/validate", dependencies=[Depends(verify_api_key)])
async def validate_invoice(invoice_id: int):
    """Validar factura (cambiar estado a validado)."""
    await simulate_delay()
    maybe_error()

    for i, inv in enumerate(mock_data["invoices"]):
        if inv["id"] == invoice_id:
            if inv["status"] != 0:
                raise HTTPException(status_code=400, detail="Invoice already validated")
            updated = {**inv, "status": 1, "datem": datetime.now().isoformat()}
            mock_data["invoices"][i] = updated
            return {"success": True, "data": updated}

    raise HTTPException(status_code=404, detail="Invoice not found")


# -----------------------------------------------------------------------------
# DOCUMENTOS ADJUNTOS
# -----------------------------------------------------------------------------


@app.post("/documents/upload", dependencies=[Depends(verify_api_key)])
async def upload_document(
    modulepart: str = "expediente_animal",
    ref_id: int = 0,
    # file: UploadFile = File(...)
):
    """Simular subida de documento."""
    await simulate_delay()
    maybe_error()

    doc_id = str(uuid4())
    return {
        "success": True,
        "data": {
            "id": doc_id,
            "filename": f"document_{doc_id}.pdf",
            "modulepart": modulepart,
            "ref_id": ref_id,
            "url": f"/documents/download/{doc_id}",
            "uploaded_at": datetime.now().isoformat(),
        },
    }


# -----------------------------------------------------------------------------
# WEBHOOKS (para notificaciones Dolibarr -> API)
# -----------------------------------------------------------------------------


@app.post("/webhooks/dolibarr", dependencies=[Depends(verify_api_key)])
async def dolibarr_webhook(event: dict[str, Any]):
    """Recibir webhooks de Dolibarr (creación/actualización de entidades)."""
    await simulate_delay()

    # Log del evento recibido
    print(f"Webhook Dolibarr recibido: {event}")

    return {"success": True, "message": "Webhook procesado"}


# -----------------------------------------------------------------------------
# INICIALIZACIÓN
# -----------------------------------------------------------------------------


@app.on_event("startup")
async def startup():
    """Inicializar datos de prueba si SEED_FAKE_DATA=true."""
    if os.getenv("SEED_FAKE_DATA", "true").lower() == "true":
        await seed_fake_data()
        add_test_supplier()


async def seed_fake_data():
    """Poblar con datos ficticios realistas."""
    import random

    from faker import Faker

    fake = Faker(["es_ES"])

    # Terceros (clientes)
    if not mock_data["thirdparties"]:
        for i in range(20):
            is_breeder = i < 5
            mock_data["thirdparties"].append(
                {
                    "id": i + 1,
                    "ref": f"{'CRI' if is_breeder else 'CLI'}-{i + 1:06d}",
                    "name": fake.company() if is_breeder else fake.name(),
                    "name_alias": fake.company_suffix() if is_breeder else None,
                    "email": fake.email(),
                    "phone": fake.phone_number(),
                    "address": fake.street_address(),
                    "zip": fake.postcode(),
                    "town": fake.city(),
                    "country_id": 195,  # España
                    "country_code": "ES",
                    "client": 1 if not is_breeder else 0,
                    "supplier": 1 if is_breeder else 0,
                    "status": 1,
                    "vat_number": f"ES{fake.random_number(digits=8, fix_len=True)}{fake.random_letter()}",
                    "default_lang": "es_ES",
                    "datec": datetime.now().isoformat(),
                    "datem": datetime.now().isoformat(),
                }
            )

    # Productos (perros como productos/servicios)
    if not mock_data["products"]:
        breeds = [
            ("Golden Retriever", "Perro", 1500.0, 21.0),
            ("Labrador Retriever", "Perro", 1400.0, 21.0),
            ("Pastor Alemán", "Perro", 1600.0, 21.0),
            ("Bulldog Francés", "Perro", 2500.0, 21.0),
            ("Border Collie", "Perro", 1200.0, 21.0),
            ("Cane Corso", "Perro", 1800.0, 21.0),
            ("Rottweiler", "Perro", 1500.0, 21.0),
            ("Yorkshire Terrier", "Perro", 1300.0, 21.0),
        ]

        for i, (breed, type_, base_price, vat) in enumerate(breeds):
            mock_data["products"].append(
                {
                    "id": i + 1,
                    "ref": f"DOG-{breed.upper().replace(' ', '-')}",
                    "label": f"Cachorro {breed} LOE",
                    "description": f"Cachorro de raza {breed} con pedigree LOE, vacunado, desparasitado, con microchip y garantías.",
                    "price": base_price,
                    "price_ttc": round(base_price * (1 + vat / 100), 2),
                    "tva_tx": vat,
                    "buy_price": round(base_price * 0.6, 2),
                    "weight": 0.0,
                    "weight_units": 1,
                    "status": 1,
                    "type": 0,
                    "datec": datetime.now().isoformat(),
                    "datem": datetime.now().isoformat(),
                }
            )

    # Expedientes animales
    if not mock_data["expedientes_animal"]:
        statuses = [
            "draft",
            "pending_docs",
            "pending_review",
            "available",
            "published",
            "reserved",
            "paid",
            "preparing_transport",
            "in_transport",
            "delivered",
        ]
        colors = ["Dorado", "Negro", "Chocolate", "Blanco", "Gris", "Leonado", "Atigrado"]
        sexes = ["M", "H"]

        for i in range(30):
            breed = random.choice([b[0] for b in breeds])
            breeder = random.choice([t for t in mock_data["thirdparties"] if t["supplier"] == 1])
            client = random.choice([t for t in mock_data["thirdparties"] if t["client"] == 1])
            status = random.choice(statuses)

            mock_data["expedientes_animal"].append(
                {
                    "id": i + 1,
                    "internal_id": f"EXP-2024-{i + 1:06d}",
                    "name": f"{fake.first_name()} {fake.last_name()[:1]}.",
                    "species": "perro",
                    "breed": breed,
                    "sex": random.choice(sexes),
                    "birth_date": fake.date_between(start_date="-1y", end_date="-2m").isoformat(),
                    "color": random.choice(colors),
                    "weight_kg": round(random.uniform(2.0, 45.0), 1),
                    "microchip": f"9410000{random.randint(1000000, 9999999)}",
                    "breeder_id": breeder["id"],
                    "breeder_registration": f"ES{random.randint(10000, 99999)}",
                    "zoological_nucleus": f"ES{random.randint(100000, 999999)}",
                    "country_origin": "ES",
                    "place_origin": fake.city(),
                    "sire_name": f"CH {fake.first_name()} of {fake.last_name()}",
                    "dam_name": f"CH {fake.first_name()} of {fake.last_name()}",
                    "pedigree": f"LOE-{random.randint(100000, 999999)}",
                    "vet_status": "healthy",
                    "vaccines": [
                        {
                            "name": "Polivalente",
                            "date": fake.date_between(start_date="-6m", end_date="-1m").isoformat(),
                            "batch": f"L{random.randint(10000, 99999)}",
                        },
                        {
                            "name": "Rabia",
                            "date": fake.date_between(start_date="-6m", end_date="-1m").isoformat(),
                            "batch": f"L{random.randint(10000, 99999)}",
                        },
                    ],
                    "deworming": [
                        {
                            "product": "Milbemax",
                            "date": fake.date_between(start_date="-3m", end_date="-1m").isoformat(),
                        },
                    ],
                    "passport": f"ES{random.randint(10000000, 99999999)}",
                    "certificates": [
                        {
                            "type": "veterinary_health",
                            "date": fake.date_between(start_date="-1m", end_date="today").isoformat(),
                            "vet": fake.name(),
                        },
                    ],
                    "photos": [
                        f"https://example.com/photos/dog_{i}_1.jpg",
                        f"https://example.com/photos/dog_{i}_2.jpg",
                    ],
                    "videos": [f"https://example.com/videos/dog_{i}.mp4"],
                    "purchase_price": round(random.uniform(800, 1500), 2),
                    "sale_price": round(random.uniform(1500, 3000), 2),
                    "associated_costs": round(random.uniform(200, 500), 2),
                    "commercial_status": status,
                    "client_id": client["id"] if status in ["reserved", "paid", "delivered"] else None,
                    "reservation_id": random.randint(1, 100) if status in ["reserved", "paid"] else None,
                    "order_id": random.randint(1, 100) if status in ["paid", "delivered"] else None,
                    "invoice_id": random.randint(1, 50) if status == "delivered" else None,
                    "transport_id": random.randint(1, 20)
                    if status in ["preparing_transport", "in_transport", "delivered"]
                    else None,
                    "expected_delivery_date": fake.date_between(start_date="today", end_date="+30d").isoformat()
                    if status in ["preparing_transport", "in_transport"]
                    else None,
                    "actual_delivery_date": fake.date_between(start_date="-30d", end_date="today").isoformat()
                    if status == "delivered"
                    else None,
                    "incidents": [],
                    "post_sale_followup": [],
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat(),
                }
            )

    # Facturas
    if not mock_data["invoices"]:
        for i in range(15):
            delivered_expedientes = [
                e for e in mock_data["expedientes_animal"] if e["commercial_status"] == "delivered"
            ]
            if not delivered_expedientes:
                break

            exp = random.choice(delivered_expedientes)
            client = next(
                (t for t in mock_data["thirdparties"] if t["id"] == exp["client_id"]), mock_data["thirdparties"][5]
            )

            lines = [
                {
                    "product_id": 1,
                    "description": f"Cachorro {exp['breed']} - {exp['internal_id']}",
                    "qty": 1,
                    "unit_price": exp["sale_price"],
                    "vat_rate": 21.0,
                    "discount_percent": 0.0,
                }
            ]

            total_ht = exp["sale_price"]
            total_tva = total_ht * 0.21
            total_ttc = total_ht + total_tva

            mock_data["invoices"].append(
                {
                    "id": i + 1,
                    "ref": f"FAC-2024-{i + 1:06d}",
                    "thirdparty_id": client["id"],
                    "date": datetime.now().date().isoformat(),
                    "lines": lines,
                    "total_ht": round(total_ht, 2),
                    "total_tva": round(total_tva, 2),
                    "total_ttc": round(total_ttc, 2),
                    "status": 1,
                    "datec": datetime.now().isoformat(),
                    "datem": datetime.now().isoformat(),
                }
            )

    print(
        f"Datos ficticios cargados: {len(mock_data['thirdparties'])} terceros, {len(mock_data['products'])} productos, {len(mock_data['expedientes_animal'])} expedientes, {len(mock_data['invoices'])} facturas"
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
