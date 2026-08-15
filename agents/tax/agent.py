"""
Agente Fiscal - Preparación de impuestos.
"""

from datetime import date, datetime
from uuid import uuid4

import structlog

logger = structlog.get_logger()


class TaxAgent:
    """
    Agente Fiscal - Preparación de impuestos.

    Responsabilidades:
    - Preparar información trimestral
    - Calcular borradores
    - Comparar con la información de la gestoría
    - Detectar diferencias
    - Revisar facturas omitidas
    - Detectar IVA potencialmente no deducible
    - Preparar informes
    - Controlar vencimientos
    - Registrar incidencias

    No puede:
    - Presentar impuestos
    - Firmar documentos
    - Acceder directamente al certificado digital
    - Modificar declaraciones presentadas
    - Enviar información a Hacienda sin aprobación humana
    """

    def __init__(self, config: dict):
        self.config = config
        self.agent_id = "tax"
        self.agent_name = "Tax Agent"
        self.capabilities = [
            "prepare_quarterly_vat",
            "prepare_annual_vat",
            "prepare_income_tax",
            "calculate_vat_draft",
            "compare_with_gestoria",
            "detect_missing_invoices",
            "detect_non_deductible_vat",
            "prepare_reports",
            "track_deadlines",
            "register_incidents",
        ]
        self.restrictions = [
            "cannot_file_taxes",
            "cannot_sign_documents",
            "cannot_access_certificate",
            "cannot_modify_filed_returns",
            "cannot_send_to_aeat",
        ]

    async def start(self):
        logger.info("starting_tax_agent")

    async def stop(self):
        pass

    async def process_task(self, task: dict) -> dict:
        handlers = {
            "prepare_quarterly_vat": self._prepare_quarterly_vat,
            "prepare_annual_vat": self._prepare_annual_vat,
            "prepare_income_tax": self._prepare_income_tax,
            "calculate_vat_draft": self._calculate_vat_draft,
            "compare_with_gestoria": self._compare_with_gestoria,
            "detect_missing_invoices": self._detect_missing_invoices,
            "detect_non_deductible_vat": self._detect_non_deductible_vat,
            "prepare_reports": self._prepare_reports,
            "track_deadlines": self._track_deadlines,
            "register_incident": self._register_incident,
        }

        handler = handlers.get(task.get("task_type"))
        if not handler:
            return {"success": False, "error": f"Unknown task type: {task.get('task_type')}"}

        try:
            return await handler(task.get("input_data", {}))
        except Exception as e:
            logger.error("task_failed", task_type=task.get("task_type"), error=str(e))
            return {"success": False, "error": str(e)}

    async def _prepare_quarterly_vat(self, data: dict) -> dict:
        """Preparar borrador IVA trimestral (modelo 303)."""
        quarter = data.get("quarter")  # Q1, Q2, Q3, Q4
        year = data.get("year", date.today().year)

        # TODO: Consultar facturas emitidas y recibidas del trimestre
        # Calcular:
        # Casilla 1: IVA repercutido (facturas emitidas)
        # Casilla 2: IVA soportado deducible (facturas recibidas deducibles)
        # Casilla 3: IVA soportado no deducible
        # Casilla 4: IVA repercutido operaciones exentas
        # Casilla 5: IVA repercutido operaciones no sujetas
        # Casilla 6: IVA repercutido operaciones intracomunitarias
        # Casilla 7: IVA soportado operaciones intracomunitarias
        # Casilla 8: IVA repercutido operaciones importación
        # Casilla 9: IVA soportado operaciones importación
        # Casilla 10: Regularizaciones
        # Casilla 11: Diferencia (1+4+5+6+8 - 2-3-7-9-10)
        # Casilla 12: A ingresar / A devolver

        # Simulación
        vat_emitido = 15000.00
        vat_deducible = 8000.00
        vat_no_deducible = 500.00
        regularizaciones = 0.0

        resultado = round(vat_emitido - vat_deducible - vat_no_deducible + regularizaciones, 2)

        draft = {
            "model": "303",
            "period": f"{year}Q{quarter}",
            "year": year,
            "quarter": quarter,
            "boxes": {
                "01": round(vat_emitido, 2),
                "02": round(vat_deducible, 2),
                "03": round(vat_no_deducible, 2),
                "04": 0.0,
                "05": 0.0,
                "06": 0.0,
                "07": 0.0,
                "08": 0.0,
                "09": 0.0,
                "10": round(regularizaciones, 2),
                "11": round(resultado, 2),
                "12": "A ingresar" if resultado > 0 else "A devolver" if resultado < 0 else "Sin actividad",
            },
            "status": "draft",
            "calculated_at": datetime.now().isoformat(),
            "notes": "Borrador automático - Requiere revisión y aprobación",
        }

        return {
            "success": True,
            "draft": draft,
            "requires_review": True,
            "message": f"Borrador modelo 303 {year}Q{quarter} preparado",
        }

    async def _prepare_annual_vat(self, data: dict) -> dict:
        """Preparar borrador IVA anual (modelo 390)."""
        year = data.get("year", date.today().year)

        # Resumen anual de IVA
        # Agregar 4 trimestres
        annual = {
            "model": "390",
            "year": year,
            "summary": {
                "total_vat_emitido": 60000.00,
                "total_vat_deducible": 32000.00,
                "total_vat_no_deducible": 2000.00,
                "total_regularizaciones": 0.0,
                "total_ingresado": 28000.00,
            },
            "quarterly_breakdown": [
                {"quarter": "Q1", "emitido": 15000, "deducible": 8000, "no_deducible": 500},
                {"quarter": "Q2", "emitido": 15000, "deducible": 8000, "no_deducible": 500},
                {"quarter": "Q3", "emitido": 15000, "deducible": 8000, "no_deducible": 500},
                {"quarter": "Q4", "emitido": 15000, "deducible": 8000, "no_deducible": 500},
            ],
            "status": "draft",
            "calculated_at": datetime.now().isoformat(),
        }

        return {
            "success": True,
            "draft": annual,
            "message": f"Borrador modelo 390 {year} preparado",
        }

    async def _prepare_income_tax(self, data: dict) -> dict:
        """Preparar borrador IRPF/IS (modelo 130/131/202/200)."""
        year = data.get("year", date.today().year)
        tax_type = data.get("tax_type", "IS")  # IS, IRPF

        if tax_type == "IS":
            # Impuesto Sociedades (modelo 200)
            draft = {
                "model": "200",
                "year": year,
                "tax_base": 150000.00,
                "tax_rate": 25.0,
                "gross_tax": 37500.00,
                "deductions": 0.0,
                "net_tax": 37500.00,
                "withholdings": 35000.00,
                "payments_on_account": 30000.00,
                "to_pay": 7500.00,
            }
        else:
            # IRPF (modelo 130/131)
            draft = {
                "model": "130",
                "year": year,
                "net_income": 50000.00,
                "deductions": 5000.00,
                "taxable_base": 45000.00,
                "tax": 9000.00,
                "withholdings": 8000.00,
                "to_pay": 1000.00,
            }

        return {
            "success": True,
            "draft": draft,
            "message": f"Borrador {draft['model']} {year} preparado",
        }

    async def _calculate_vat_draft(self, data: dict) -> dict:
        """Calcular borrador IVA para período específico."""
        # TODO: Calcular IVA para rango de fechas
        _ = data.get("date_from")
        _ = data.get("date_to")
        return {
            "success": True,
            "vat_emitido": 0.0,
            "vat_deducible": 0.0,
            "vat_no_deducible": 0.0,
            "result": 0.0,
        }

    async def _compare_with_gestoria(self, data: dict) -> dict:
        """Comparar cálculos con información de la gestoría."""
        period = data.get("period")  # Q1, Q2, Q3, Q4, YEAR
        gestoria_data = data.get("gestoria_data", {})

        # Nuestros cálculos
        our_calculations = data.get("our_calculations", {})

        differences = []
        for key in ["vat_emitido", "vat_deducible", "vat_no_deducible", "result"]:
            our_val = our_calculations.get(key, 0)
            gestoria_val = gestoria_data.get(key, 0)
            diff = round(abs(our_val - gestoria_val), 2)

            if diff > 0.01:
                differences.append(
                    {
                        "concept": key,
                        "our_value": our_val,
                        "gestoria_value": gestoria_val,
                        "difference": diff,
                        "percentage": round((diff / max(abs(gestoria_val), 1)) * 100, 2),
                    }
                )

        return {
            "success": True,
            "period": period,
            "differences": differences,
            "total_differences": sum(d["difference"] for d in differences),
            "matches": len(differences) == 0,
            "requires_review": len(differences) > 0,
        }

    async def _detect_missing_invoices(self, data: dict) -> dict:
        """Detectar facturas omitidas en declaraciones."""
        _ = data.get("period")

        # Comparar facturas en Dolibarr vs declaradas
        missing_emitidas = []  # Facturas emitidas no declaradas
        missing_recibidas = []  # Facturas recibidas no declaradas

        # TODO: Comparar
        # 1. Facturas emitidas en Dolibarr vs declaradas en 303
        # 2. Facturas recibidas en Dolibarr vs declaradas en 303

        return {
            "success": True,
            "missing_emitidas": missing_emitidas,
            "missing_recibidas": missing_recibidas,
            "total_missing": len(missing_emitidas) + len(missing_recibidas),
        }

    async def _detect_non_deductible_vat(self, data: dict) -> dict:
        """Detectar IVA potencialmente no deducible."""
        _ = data.get("period")

        # Facturas recibidas con IVA potencialmente no deducible:
        # - Gastos de representación (>1% ingresos netos)
        # - Gastos de atenciones a clientes/proveedores
        # - Vehículos turismo (salvo excepciones)
        # - Gastos de restauración/hotel (salvo viajes)
        # - Regalos a clientes (>200€/año)
        # - Servicios de telefonía móvil (parcial)
        # - Gastos de vestuario (salvo uniformes)

        suspicious = []

        # TODO: Analizar facturas recibidas
        # suspicious = [
        #     {
        #         "invoice_id": 1,
        #         "concept": "Comida cliente",
        #         "amount": 150,
        #         "vat": 31.5,
        #         "reason": "Atenciones a clientes - límite 1%",
        #     },
        # ]

        return {
            "success": True,
            "suspicious_invoices": suspicious,
            "total_suspicious_vat": sum(s.get("vat", 0) for s in suspicious),
            "recommendations": [
                "Revisar gastos de representación (límite 1% ingresos netos)",
                "Verificar vehículos turismo (solo deducible si uso exclusivo actividad)",
                "Separar gastos de viaje de restauración/hotel",
            ],
        }

    async def _prepare_reports(self, data: dict) -> dict:
        """Preparar informes fiscales."""
        report_type = data.get("report_type", "quarterly_vat")
        period = data.get("period")

        reports = {
            "quarterly_vat": "Informe IVA trimestral (modelo 303)",
            "annual_vat": "Informe IVA anual (modelo 390)",
            "income_tax": "Informe IRPF/IS",
            "withholdings": "Informe retenciones (modelo 190/111)",
            "intracomunitary": "Operaciones intracomunitarias (modelo 349)",
            "cash_basis": "Régimen especial criterio de caja",
        }

        return {
            "success": True,
            "report_type": report_type,
            "period": period,
            "report": f"Informe {reports.get(report_type, 'personalizado')} para {period}",
            "generated_at": datetime.now().isoformat(),
        }

    async def _track_deadlines(self, data: dict) -> dict:
        """Controlar vencimientos fiscales."""
        # Calendario fiscal 2024
        deadlines = {
            "303_Q1": "2024-04-20",
            "303_Q2": "2024-07-20",
            "303_Q3": "2024-10-20",
            "303_Q4": "2025-01-20",
            "390": "2025-01-31",
            "130_Q1": "2024-04-20",
            "130_Q2": "2024-07-20",
            "130_Q3": "2024-10-20",
            "130_Q4": "2025-01-20",
            "111_Q1": "2024-04-20",
            "111_Q2": "2024-07-20",
            "111_Q3": "2024-10-20",
            "111_Q4": "2025-01-20",
            "190": "2025-01-31",
            "349_Q1": "2024-04-20",
            "349_Q2": "2024-07-20",
            "349_Q3": "2024-10-20",
            "349_Q4": "2025-01-20",
            "200": "2025-07-25",
        }

        upcoming = []
        today = date.today()
        for model, deadline_str in deadlines.items():
            deadline = datetime.strptime(deadline_str, "%Y-%m-%d").date()
            days_left = (deadline - today).days
            if 0 <= days_left <= 30:
                upcoming.append(
                    {
                        "model": model,
                        "deadline": deadline_str,
                        "days_left": days_left,
                        "urgency": "critical" if days_left <= 5 else "warning" if days_left <= 15 else "normal",
                    }
                )

        return {
            "success": True,
            "upcoming_deadlines": sorted(upcoming, key=lambda x: x["days_left"]),
            "total_pending": len(upcoming),
        }

    async def _register_incident(self, data: dict) -> dict:
        """Registrar incidencia fiscal."""
        incident = {
            "id": str(uuid4()),
            "date": datetime.now().isoformat(),
            "type": data.get("type", "general"),
            "description": data.get("description", ""),
            "period": data.get("period"),
            "model": data.get("model"),
            "severity": data.get("severity", "medium"),
            "status": "open",
            "assigned_to": data.get("assigned_to"),
            "resolution": None,
            "resolved_at": None,
        }

        # TODO: Guardar en BD
        return {
            "success": True,
            "incident": incident,
            "message": "Incidencia registrada",
        }
