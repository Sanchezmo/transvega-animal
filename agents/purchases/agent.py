"""
Agente de Compras y Gastos - Gestión de facturas de proveedores.
"""
import asyncio
from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List, Optional, Any
from uuid import uuid4
import structlog

logger = structlog.get_logger()


class PurchasesAgent:
    """
    Agente de Compras y Gastos.
    
    Responsabilidades:
    - Leer facturas recibidas desde Gmail o Drive
    - Extraer proveedor, NIF, fecha, número, base, impuestos y total
    - Detectar duplicados
    - Proponer categoría
    - Proponer cuenta contable
    - Crear borrador de factura de proveedor
    - Adjuntar documento
    - Detectar incoherencias
    - Solicitar revisión humana
    
    Debe bloquear o escalar:
    - Proveedor nuevo
    - Datos fiscales incompletos
    - IVA incoherente
    - Factura duplicada
    - Factura rectificativa
    - Gastos personales
    - Inmovilizado
    - Operaciones internacionales
    - Deducibilidad dudosa
    """
    
    def __init__(self, config: Dict):
        self.config = config
        self.agent_id = "purchases"
        self.agent_name = "Purchases Agent"
        self.capabilities = [
            "parse_invoice_email",
            "parse_invoice_document",
            "extract_invoice_data",
            "detect_duplicates",
            "propose_category",
            "propose_account",
            "create_draft_purchase_invoice",
            "attach_document",
            "detect_incoherences",
            "request_human_review",
        ]
        self.restrictions = [
            "cannot_validate_without_approval",
            "cannot_pay_without_approval",
            "must_block_new_vendor",
            "must_escalate_incoherences",
        ]
    
    async def start(self):
        logger.info("starting_purchases_agent")
    
    async def stop(self):
        pass
    
    async def process_task(self, task: Dict) -> Dict:
        task_type = task.get("task_type")
        
        handlers = {
            "parse_invoice_email": self._parse_invoice_email,
            "parse_invoice_document": self._parse_invoice_document,
            "extract_invoice_data": self._extract_invoice_data,
            "detect_duplicates": self._detect_duplicates,
            "propose_category": self._propose_category,
            "propose_account": self._propose_account,
            "create_draft_purchase_invoice": self._create_draft_purchase_invoice,
            "detect_incoherences": self._detect_incoherences,
            "request_human_review": self._request_human_review,
        }
        
        handler = handlers.get(task.get("task_type"))
        if not handler:
            return {"success": False, "error": f"Unknown task type: {task.get('task_type')}"}
        
        try:
            return await handler(task.get("input_data", {}))
        except Exception as e:
            logger.error("task_failed", task_type=task.get("task_type"), error=str(e))
            return {"success": False, "error": str(e)}
    
    async def _parse_invoice_email(self, data: Dict) -> Dict:
        """Parsear factura desde email (Gmail)."""
        email_data = data.get("email", {})
        
        # TODO: Implementar parsing con regex/ML
        # 1. Identificar si es factura (keywords: factura, invoice, proveedor)
        # 2. Extraer adjuntos (PDF, XML)
        # 3. OCR/parseo del contenido
        
        # Simulación
        extracted = {
            "vendor_name": "Proveedor Ejemplo S.L.",
            "vendor_vat": "ESB12345678",
            "invoice_number": "FAC-2024-001",
            "date": date.today().isoformat(),
            "due_date": (datetime.now() + timedelta(days=30)).date().isoformat(),
            "lines": [
                {"description": "Alimento premium perros", "qty": 50, "unit_price": 45.00, "vat_rate": 21.0},
                {"description": "Material veterinario", "qty": 10, "unit_price": 120.00, "vat_rate": 21.0},
            ],
            "total_ht": 4050.00,
            "total_vat": 850.50,
            "total_ttc": 4900.50,
        }
        
        return {
            "success": True,
            "extracted_data": extracted,
            "confidence": 0.85,
            "requires_review": True,
        }
    
    async def _parse_invoice_document(self, data: Dict) -> Dict:
        """Parsear factura desde documento (PDF/XML en Drive/Gmail)."""
        document_id = data.get("document_id")
        mime_type = data.get("mime_type", "application/pdf")
        
        # TODO: OCR con Tesseract + LayoutLM
        # Para XML (FacturaE): parseo directo
        
        return {
            "success": True,
            "message": "Parsing documento iniciado",
            "document_id": document_id,
            "status": "processing",
        }
    
    async def _extract_invoice_data(self, data: Dict) -> Dict:
        """Extraer datos estructurados de factura parseada."""
        raw_text = data.get("raw_text", "")
        
        # TODO: NLP/Regex para extraer campos
        # - Proveedor (nombre, NIF, dirección)
        # - Número factura, fecha, vencimiento
        # - Líneas (descripción, cantidad, precio, IVA)
        # - Totales (base, IVA, total)
        # - Forma de pago, cuenta bancaria
        
        return {
            "success": True,
            "extracted": {
                "vendor": "Proveedor Extraído",
                "vat": "ESB12345678",
                "number": "FAC-001",
                "date": date.today().isoformat(),
                "total": 1000.00,
            },
            "confidence": 0.90,
        }
    
    async def _detect_duplicates(self, data: Dict) -> Dict:
        """Detectar facturas duplicadas."""
        invoice_data = data.get("invoice_data", {})
        vendor_vat = invoice_data.get("vendor_vat")
        invoice_number = invoice_data.get("invoice_number")
        date_str = invoice_data.get("date")
        
        # TODO: Buscar en BD por proveedor + número + fecha
        # duplicate = await db.find_duplicate(vendor_vat, invoice_number, date_str)
        
        # Simulación
        is_duplicate = False
        existing = None
        
        return {
            "success": True,
            "is_duplicate": is_duplicate,
            "existing_invoice": existing,
            "confidence": 0.95 if is_duplicate else 0.99,
        }
    
    async def _propose_category(self, data: Dict) -> Dict:
        """Proponer categoría contable según descripción."""
        description = data.get("description", "").lower()
        
        categories = {
            "alimento": {"account": "600000", "name": "Compras de mercaderías - Alimentos"},
            "pienso": {"account": "600000", "name": "Compras de mercaderías - Alimentos"},
            "veterinario": {"account": "623000", "name": "Servicios profesionales - Veterinario"},
            "medicamento": {"account": "607000", "name": "Trabajos realizados por otras empresas"},
            "material": {"account": "607000", "name": "Trabajos realizados por otras empresas"},
            "transporte": {"account": "624000", "name": "Transportes"},
            "alquiler": {"account": "621000", "name": "Alquileres y cánones"},
            "luz": {"account": "625000", "name": "Suministros"},
            "agua": {"account": "625000", "name": "Suministros"},
            "telefono": {"account": "626000", "name": "Comunicaciones"},
            "internet": {"account": "626000", "name": "Comunicaciones"},
            "seguros": {"account": "628000", "name": "Primas de seguros"},
            "publicidad": {"account": "627000", "name": "Publicidad, propaganda y relaciones públicas"},
            "formacion": {"account": "649000", "name": "Gastos de formación"},
            "inmovilizado": {"account": "210000", "name": "Inmovilizado material"},
        }
        
        for keyword, cat in categories.items():
            if keyword in description.lower():
                return {
                    "success": True,
                    "category": cat["name"],
                    "account": cat["account"],
                    "confidence": 0.85,
                }
        
        return {
            "success": True,
            "category": "Otros gastos",
            "account": "629000",
            "confidence": 0.30,
        }
    
    async def _propose_account(self, data: Dict) -> Dict:
        """Proponer cuenta contable (alias de propose_category)."""
        return await self._propose_category(data)
    
    async def _create_draft_purchase_invoice(self, data: Dict) -> Dict:
        """Crear borrador de factura de proveedor en Dolibarr."""
        invoice_data = data.get("invoice_data", {})
        
        # Validaciones
        required = ["vendor_vat", "vendor_name", "invoice_number", "date", "lines"]
        for field in required:
            if not invoice_data.get(field):
                return {"success": False, "error": f"Campo requerido: {field}"}
        
        # Validar líneas
        for i, line in enumerate(invoice_data.get("lines", [])):
            if line.get("qty", 0) <= 0:
                return {"success": False, "error": f"Línea {i+1}: cantidad inválida"}
            if line.get("unit_price", 0) < 0:
                return {"success": False, "error": f"Línea {i+1}: precio negativo"}
        
        # Detectar duplicados
        dup_check = await self._detect_duplicates({"invoice_data": invoice_data})
        if dup_check.get("is_duplicate"):
            return {"success": False, "error": "Factura duplicada detectada", "existing": dup_check["existing_invoice"]}
        
        # Verificar proveedor existe
        # vendor = await dolibarr.get_thirdparty_by_vat(invoice_data["vendor_vat"])
        # if not vendor:
        #     return {"success": False, "error": "Proveedor nuevo - requiere alta manual", "requires_vendor_creation": True}
        
        # Proponer categoría por defecto
        first_line_desc = invoice_data.get("lines", [{}])[0].get("description", "")
        category = await self._propose_category({"description": first_line_desc})
        
        # Crear borrador
        invoice = {
            "vendor_vat": invoice_data["vendor_vat"],
            "vendor_name": invoice_data["vendor_name"],
            "invoice_number": invoice_data["invoice_number"],
            "date": invoice_data["date"],
            "due_date": invoice_data.get("due_date"),
            "lines": invoice_data["lines"],
            "payment_term": invoice_data.get("payment_term", "30"),
            "proposed_category": category.get("category"),
            "proposed_account": category.get("account"),
            "status": "draft",
            "source": "auto_extracted",
        }
        
        # TODO: Crear en Dolibarr
        # result = await dolibarr.create_purchase_invoice(invoice)
        
        return {
            "success": True,
            "message": "Factura de proveedor creada en borrador",
            "invoice_id": str(uuid4()),
            "proposed_category": category.get("category"),
            "proposed_account": category.get("account"),
            "requires_human_review": True,
        }
    
    async def _detect_incoherences(self, data: Dict) -> Dict:
        """Detectar incoherencias en factura de proveedor."""
        invoice = data.get("invoice", {})
        
        issues = []
        warnings = []
        
        # Validar totales
        lines = invoice.get("lines", [])
        calculated_ht = sum(Decimal(str(l.get("qty", 0))) * Decimal(str(l.get("unit_price", 0))) * (Decimal("1") - Decimal(str(l.get("discount", 0))) / Decimal("100")) for l in lines)
        declared_ht = Decimal(str(invoice.get("total_ht", 0)))
        
        if abs(calculated_ht - declared_ht) > Decimal("0.02"):
            issues.append({
                "code": "TOTAL_MISMATCH",
                "severity": "high",
                "message": f"Base imponible no cuadra: calculado {calculated_ht}, declarado {declared_ht}",
            })
        
        # IVA
        calculated_vat = sum(
            (Decimal(str(l.get("qty", 0))) * Decimal(str(l.get("unit_price", 0))) * (Decimal("1") - Decimal(str(l.get("discount", 0))) / Decimal("100"))) * (Decimal(str(l.get("vat_rate", 21))) / Decimal("100"))
            for l in lines
        )
        declared_vat = Decimal(str(invoice.get("total_vat", 0)))
        
        if abs(calculated_vat - declared_vat) > Decimal("0.02"):
            issues.append({
                "code": "VAT_MISMATCH",
                "severity": "high",
                "message": f"IVA no cuadra: calculado {calculated_vat}, declarado {declared_vat}",
            })
        
        # Proveedor nuevo
        if invoice.get("vendor_new"):
            warnings.append({
                "code": "NEW_VENDOR",
                "severity": "medium",
                "message": "Proveedor no registrado en Dolibarr",
            })
        
        # Factura rectificativa
        if invoice.get("is_rectificative"):
            warnings.append({
                "code": "RECTIFICATIVE_INVOICE",
                "severity": "medium",
                "message": "Factura rectificativa - requiere aprobación",
            })
        
        # Gasto personal potencial
        personal_keywords = ["restaurante", "hotel", "taxi", "parking", "comida", "cena", "ocio"]
        for line in invoice.get("lines", []):
            desc = line.get("description", "").lower()
            if any(kw in desc for kw in personal_keywords):
                warnings.append({
                    "code": "POTENTIAL_PERSONAL_EXPENSE",
                    "severity": "medium",
                    "message": f"Posible gasto personal detectado: {line.get('description')}",
                })
        
        # Inmovilizado
        for line in invoice.get("lines", []):
            if line.get("unit_price", 0) > 3000:
                warnings.append({
                    "code": "POTENTIAL_FIXED_ASSET",
                    "severity": "medium",
                    "message": f"Posible inmovilizado (>3000€): {line.get('description')}",
                })
        
        # Operaciones internacionales
        if invoice.get("vendor_country") != "ES":
            warnings.append({
                "code": "INTERNATIONAL_OPERATION",
                "severity": "medium",
                "message": "Operación intracomunitaria/extracomunitaria - verificar IVA",
            })
        
        # Deducibilidad dudosa
        nondeductible_keywords = ["representación", "regalo", "multa", "sanción", "donativo"]
        for line in invoice.get("lines", []):
            desc = line.get("description", "").lower()
            if any(kw in desc for kw in nondeductible_keywords):
                warnings.append({
                    "code": "DEDUCTIBILITY_DOUBTFUL",
                    "severity": "high",
                    "message": f"Posible gasto no deducible: {line.get('description')}",
                })
        
        return {
            "success": True,
            "issues": issues,
            "warnings": warnings,
            "blocked": len(issues) > 0,
            "requires_review": len(issues) > 0 or len(warnings) > 0,
        }
    
    async def _request_human_review(self, data: Dict) -> Dict:
        """Solicitar revisión humana para factura problemática."""
        invoice_id = data.get("invoice_id")
        reason = data.get("reason", "Revisión requerida por agente")
        priority = data.get("priority", "normal")
        
        # approval_id = await approval_service.request({
        #     "action": "review_purchase_invoice",
        #     "resource_type": "purchase_invoice",
        #     "resource_id": invoice_id,
        #     "reason": reason,
        #     "priority": priority,
        # })
        
        return {
            "success": True,
            "message": "Revisión humana solicitada",
            "approval_id": str(uuid4()),
            "status": "pending_review",
        }