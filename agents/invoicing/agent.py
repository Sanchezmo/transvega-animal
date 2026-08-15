"""
Agente de Facturación - Gestión de facturas y cobros.
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

import structlog

logger = structlog.get_logger()


class InvoicingAgent:
    """
    Agente de Facturación.

    Responsabilidades:
    - Comprobar que existe pedido aprobado
    - Validar datos fiscales del cliente
    - Comprobar líneas, precios e impuestos
    - Crear factura en borrador
    - Relacionar factura con pedido y expediente
    - Preparar PDF
    - Preparar envío al cliente
    - Registrar cobro
    - Detectar impagos
    - Gestionar el flujo con el futuro módulo VeriFactu

    Durante la fase inicial:
    - Solo puede crear borradores
    - No puede validar facturas definitivas
    - No puede crear facturas rectificativas
    - No puede modificar series
    - No puede cambiar impuestos
    - No puede borrar facturas
    """

    def __init__(self, config: dict):
        self.config = config
        self.agent_id = "invoicing"
        self.agent_name = "Invoicing Agent"
        self.capabilities = [
            "create_draft_invoice",
            "validate_invoice_data",
            "calculate_totals",
            "generate_pdf",
            "send_invoice",
            "register_payment",
            "detect_overdue",
            "create_rectification",
            "cancel_invoice",
        ]
        self.restrictions = [
            "cannot_validate_without_approval",
            "cannot_create_rectificative_without_approval",
            "cannot_modify_series",
            "cannot_change_taxes",
            "cannot_delete_invoices",
            "draft_only_in_phase_1",
        ]

    async def start(self):
        """Iniciar agente."""
        logger.info("starting_invoicing_agent")

    async def stop(self):
        """Detener agente."""
        pass

    async def process_task(self, task: dict) -> dict:
        """Procesar tarea asignada."""

        handlers = {
            "create_draft_invoice": self._create_draft_invoice,
            "validate_invoice_data": self._validate_invoice_data,
            "calculate_totals": self._calculate_totals,
            "generate_pdf": self._generate_pdf,
            "send_invoice": self._send_invoice,
            "register_payment": self._register_payment,
            "detect_overdue": self._detect_overdue,
            "create_rectification": self._create_rectification,
            "cancel_invoice": self._cancel_invoice,
        }

        handler = handlers.get(task.get("task_type"))
        if not handler:
            return {"success": False, "error": f"Unknown task type: {task.get('task_type')}"}

        try:
            return await handler(task.get("input_data", {}))
        except Exception as e:
            logger.error("task_failed", task_type=task.get("task_type"), error=str(e))
            return {"success": False, "error": str(e)}

    async def _create_draft_invoice(self, data: dict) -> dict:
        """Crear factura en borrador."""
        order_id = data.get("order_id")
        expediente_id = data.get("expediente_id")
        client_id = data.get("client_id")
        lines = data.get("lines", [])

        # Validaciones
        if not lines:
            return {"success": False, "error": "La factura debe tener al menos una línea"}

        # Verificar cliente
        # client = await dolibarr.get_thirdparty(client_id)
        # if not client:
        #     return {"success": False, "error": "Cliente no encontrado"}

        # Validar datos fiscales
        # if not client.get("vat_number") and client.get("country_code") != "ES":
        #     return {"success": False, "error": "NIF-IVA requerido para facturas intracomunitarias"}

        # Validar líneas
        for line in lines:
            if line.get("qty", 0) <= 0:
                return {"success": False, "error": "Cantidad debe ser positiva"}
            if line.get("unit_price", 0) < 0:
                return {"success": False, "error": "Precio unitario no puede ser negativo"}
            if not 0 <= line.get("vat_rate", 0) <= 100:
                return {"success": False, "error": "Tipo IVA inválido"}

        # Calcular totales
        totals = self._calculate_totals_internal(lines)

        # Determinar régimen IVA
        vat_regime = self._determine_vat_regime(data.get("client", {}))

        # Crear factura en Dolibarr (simulado)
        invoice = {
            "id": str(uuid4()),
            "ref": f"FAC-{datetime.now().year}-{datetime.now().strftime('%m%d')}-{uuid4().hex[:4]}",
            "order_id": order_id,
            "expediente_id": expediente_id,
            "client_id": client_id,
            "lines": lines,
            "vat_regime": vat_regime,
            **totals,
            "status": "draft",
            "date": date.today().isoformat(),
            "created_at": datetime.now().isoformat(),
        }

        # TODO: Crear en Dolibarr via API
        # result = await dolibarr.create_invoice(invoice)

        return {
            "success": True,
            "invoice": invoice,
            "message": "Factura creada en borrador",
            "requires_approval_for_validation": True,
        }

    async def _validate_invoice_data(self, data: dict) -> dict:
        """Validar datos de factura antes de crear."""
        invoice = data.get("invoice", {})

        errors = []
        warnings = []

        # Validar cliente
        client = data.get("client", {})
        if not client.get("vat_number") and client.get("country_code") != "ES":
            errors.append("NIF-IVA requerido para facturas intracomunitarias/exportación")

        # Validar líneas
        lines = invoice.get("lines", [])
        if not lines:
            errors.append("La factura debe tener al menos una línea")

        for i, line in enumerate(lines):
            if line.get("qty", 0) <= 0:
                errors.append(f"Línea {i + 1}: Cantidad debe ser positiva")
            if line.get("unit_price", 0) < 0:
                errors.append(f"Línea {i + 1}: Precio unitario no puede ser negativo")
            if line.get("vat_rate", 0) < 0 or line.get("vat_rate", 0) > 100:
                errors.append(f"Línea {i + 1}: Tipo IVA inválido")

        # Validar datos fiscales obligatorios
        required_client_fields = ["name", "address", "zip", "town", "country_code"]
        for field in required_client_fields:
            if not client.get(field):
                errors.append(f"Cliente: campo obligatorio faltante: {field}")

        # Validar régimen IVA
        vat_regime = invoice.get("vat_regime", "domestic")
        valid_regimes = ["domestic", "intra_community", "export", "distance_selling"]
        if vat_regime not in valid_regimes:
            errors.append(f"Régimen IVA inválido: {vat_regime}")

        # Advertencias
        if client.get("country_code") == "ES" and not client.get("vat_number"):
            warnings.append("Cliente español sin NIF/CIF - verificar exención")

        return {
            "success": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "vat_regime": vat_regime,
        }

    def _calculate_totals_internal(self, lines: list[dict]) -> dict:
        """Calcular totales de factura."""
        total_ht = Decimal("0")
        total_tva = Decimal("0")
        line_totals = []

        for line in lines:
            qty = Decimal(str(line.get("qty", 1)))
            unit_price = Decimal(str(line.get("unit_price", 0)))
            discount = Decimal(str(line.get("discount_percent", 0)))
            vat_rate = Decimal(str(line.get("vat_rate", 21)))

            line_ht = qty * unit_price * (Decimal("1") - discount / Decimal("100"))
            line_tva = line_ht * (vat_rate / Decimal("100"))

            total_ht += line_ht
            total_tva += line_tva

            line_totals.append(
                {
                    "line_ht": float(line_ht.quantize(Decimal("0.01"))),
                    "line_tva": float(line_tva.quantize(Decimal("0.01"))),
                    "line_ttc": float((line_ht + line_tva).quantize(Decimal("0.01"))),
                }
            )

        total_ttc = total_ht + total_tva

        return {
            "total_ht": float(total_ht.quantize(Decimal("0.01"))),
            "total_tva": float(total_tva.quantize(Decimal("0.01"))),
            "total_ttc": float(total_ttc.quantize(Decimal("0.01"))),
            "line_totals": line_totals,
        }

    async def _calculate_totals(self, data: dict) -> dict:
        """Calcular totales de factura (endpoint público)."""
        lines = data.get("lines", [])
        totals = self._calculate_totals_internal(lines)
        return {"success": True, "totals": totals}

    def _determine_vat_regime(self, client: dict) -> str:
        """Determinar régimen IVA según cliente."""
        country = client.get("country_code", "ES")
        is_business = client.get("is_business", True)
        has_vat = bool(client.get("vat_number"))

        if country == "ES":
            return "domestic"
        elif country in [
            "AT",
            "BE",
            "BG",
            "HR",
            "CY",
            "CZ",
            "DK",
            "EE",
            "FI",
            "FR",
            "DE",
            "GR",
            "HU",
            "IE",
            "IT",
            "LV",
            "LT",
            "LU",
            "MT",
            "NL",
            "AT",
            "PL",
            "PT",
            "RO",
            "SK",
            "SI",
            "SE",
        ]:
            # UE
            if is_business and has_vat:
                return "intra_community"  # Entrega intracomunitaria (IVA 0%, reverse charge)
            else:
                return "distance_selling"  # Venta a distancia (OSS si >10k€)
        else:
            return "export"  # Exportación fuera UE

    async def _generate_pdf(self, data: dict) -> dict:
        """Generar PDF de factura."""
        invoice_id = data.get("invoice_id")

        # TODO: Generar PDF con WeasyPrint o similar
        # 1. Obtener datos factura
        # 2. Renderizar plantilla HTML
        # 3. Convertir a PDF con WeasyPrint
        # 4. Subir a MinIO/S3

        return {
            "success": True,
            "invoice_id": invoice_id,
            "pdf_url": f"https://storage.empresa.es/invoices/factura_{invoice_id}.pdf",
            "filename": f"factura_{uuid4().hex[:8]}.pdf",
        }

    async def _send_invoice(self, data: dict) -> dict:
        """Enviar factura por email al cliente."""
        invoice_id = data.get("invoice_id")
        email = data.get("email")
        _ = data.get("attach_pdf", True)

        # TODO: Enviar email con adjunto PDF
        # await email.send(
        #     to=email,
        #     subject=f"Factura {invoice_id} - Transvega Animal",
        #     template="invoice",
        #     data={"invoice_id": invoice_id},
        #     attachments=[pdf_bytes] if attach_pdf else []
        # )

        return {
            "success": True,
            "invoice_id": invoice_id,
            "sent_to": email,
            "sent_at": datetime.now().isoformat(),
        }

    async def _register_payment(self, data: dict) -> dict:
        """Registrar cobro de factura."""
        invoice_id = data.get("invoice_id")
        amount = data.get("amount")
        _ = data.get("payment_date", date.today().isoformat())
        _ = data.get("payment_method", "transfer")
        _ = data.get("reference")

        if amount <= 0:
            return {"success": False, "error": "Importe debe ser positivo"}

        # Validar que factura existe y está validada
        # invoice = await dolibarr.get_invoice(invoice_id)
        # if invoice["status"] != 1:
        #     return {"success": False, "error": "Solo facturas validadas pueden cobrarse"}

        # Verificar importe
        # if amount > invoice["total_ttc"]:
        #     return {"success": False, "error": "Importe superior al total de la factura"}

        # Registrar cobro en Dolibarr
        # payment = await dolibarr.register_payment({
        #     "invoice_id": invoice_id,
        #     "amount": amount,
        #     "date": payment_date,
        #     "mode": payment_method,
        #     "reference": reference,
        # })

        return {
            "success": True,
            "payment_id": str(uuid4()),
            "invoice_id": invoice_id,
            "amount": amount,
            "message": "Pago registrado correctamente",
        }

    async def _detect_overdue(self, data: dict) -> dict:
        """Detectar facturas impagadas vencidas."""
        _ = data.get("days_overdue", 30)

        # TODO: Consultar facturas validadas sin cobrar
        # overdue = await dolibarr.get_overdue_invoices(days_overdue)

        return {
            "success": True,
            "overdue_count": 0,
            "total_overdue_amount": 0,
            "invoices": [],
        }

    async def _create_rectification(self, data: dict) -> dict:
        """Crear factura rectificativa."""
        _ = data.get("original_invoice_id")
        _ = data.get("reason")
        _ = data.get("new_lines", [])

        # Requiere aprobación humana
        # approval_id = await approval_service.request({
        #     "action": "rectify_invoice",
        #     "resource_type": "invoice",
        #     "resource_id": original_invoice_id,
        #     "reason": reason,
        # })

        return {
            "success": True,
            "message": "Factura rectificativa solicitada, pendiente de aprobación",
            "approval_id": "pending",
        }

    async def _cancel_invoice(self, data: dict) -> dict:
        """Anular factura."""
        _ = data.get("invoice_id")
        _ = data.get("reason")

        # Requiere aprobación
        # approval_id = await approval_service.request({
        #     "action": "cancel_invoice",
        #     "resource_type": "invoice",
        #     "resource_id": invoice_id,
        #     "reason": reason,
        # })

        return {
            "success": True,
            "message": "Anulación solicitada, pendiente de aprobación",
            "approval_id": "pending",
        }
