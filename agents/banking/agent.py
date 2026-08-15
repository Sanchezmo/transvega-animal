"""
Agente Bancario - Conciliación y tesorería.
"""

from datetime import date, timedelta
from decimal import Decimal

import structlog

logger = structlog.get_logger()


class BankingAgent:
    """
    Agente Bancario - Conciliación bancaria y tesorería.

    Responsabilidades:
    - Importar movimientos bancarios
    - Proponer conciliaciones
    - Conciliar coincidencias exactas autorizadas
    - Detectar pagos parciales
    - Detectar devoluciones
    - Detectar comisiones
    - Detectar cobros sin factura
    - Detectar pagos duplicados
    - Generar previsión de tesorería

    No debe iniciar transferencias bancarias.
    """

    def __init__(self, config: dict):
        self.config = config
        self.agent_id = "banking"
        self.agent_name = "Banking Agent"
        self.capabilities = [
            "import_bank_statements",
            "propose_reconciliations",
            "auto_reconcile_exact_matches",
            "detect_partial_payments",
            "detect_returns",
            "detect_fees",
            "detect_unmatched_receipts",
            "detect_duplicate_payments",
            "forecast_cashflow",
        ]
        self.restrictions = [
            "cannot_initiate_transfers",
            "cannot_modify_bank_data",
            "auto_reconcile_only_exact_matches",
        ]

    async def start(self):
        logger.info("starting_banking_agent")

    async def stop(self):
        pass

    async def process_task(self, task: dict) -> dict:
        handlers = {
            "import_bank_statements": self._import_bank_statements,
            "propose_reconciliations": self._propose_reconciliations,
            "auto_reconcile": self._auto_reconcile,
            "detect_partial_payments": self._detect_partial_payments,
            "detect_returns": self._detect_returns,
            "detect_fees": self._detect_fees,
            "detect_unmatched_receipts": self._detect_unmatched_receipts,
            "detect_duplicate_payments": self._detect_duplicate_payments,
            "forecast_cashflow": self._forecast_cashflow,
        }

        handler = handlers.get(task.get("task_type"))
        if not handler:
            return {"success": False, "error": f"Unknown task type: {task.get('task_type')}"}

        try:
            return await handler(task.get("input_data", {}))
        except Exception as e:
            logger.error("task_failed", task_type=task.get("task_type"), error=str(e))
            return {"success": False, "error": str(e)}

    async def _import_bank_statements(self, data: dict) -> dict:
        """Importar extractos bancarios (CSV/OFX/CAMT053)."""
        _ = data.get("file_data")
        account_id = data.get("account_id")
        format_type = data.get("format", "csv")

        # TODO: Parsear según formato
        # CSV: columnas fecha, concepto, importe, saldo, referencia
        # OFX: parse XML
        # CAMT053: ISO 20022

        transactions = []

        # Simulación
        return {
            "success": True,
            "imported": len(transactions),
            "account_id": account_id,
            "format": format_type,
            "transactions": transactions,
            "duplicates_skipped": 0,
        }

    async def _propose_reconciliations(self, data: dict) -> dict:
        """Proponer conciliaciones para movimientos sin conciliar."""
        _ = data.get("account_id")
        _ = data.get("date_from")
        _ = data.get("date_to")

        # TODO: Obtener movimientos bancarios sin conciliar
        # Obtener facturas pendientes de cobro/pago
        # Hacer matching:
        # 1. Coincidencia exacta (importe + fecha + concepto)
        # 2. Coincidencia por importe +- 2 días
        # 3. Coincidencia por referencia
        # 4. Pago parcial (importe menor a factura)

        proposals = []

        # Simulación
        return {
            "success": True,
            "proposals": proposals,
            "auto_reconcilable": len([p for p in proposals if p.get("confidence", 0) >= 0.95]),
            "requires_review": len([p for p in proposals if p.get("confidence", 0) < 0.95]),
        }

    async def _auto_reconcile(self, data: dict) -> dict:
        """Conciliar automáticamente coincidencias exactas autorizadas."""
        proposals = data.get("proposals", [])
        min_confidence = data.get("min_confidence", 0.95)

        reconciled = []
        failed = []

        for proposal in proposals:
            if proposal.get("confidence", 0) >= min_confidence:
                # TODO: Conciliar en Dolibarr/BD
                reconciled.append(
                    {
                        "bank_movement_id": proposal["bank_movement_id"],
                        "document_id": proposal["document_id"],
                        "document_type": proposal["document_type"],
                    }
                )
            else:
                failed.append(
                    {
                        "proposal": proposal,
                        "reason": "Confidence below threshold",
                    }
                )

        return {
            "success": True,
            "reconciled": len(reconciled),
            "failed": len(failed),
            "details": {"reconciled": reconciled, "failed": failed},
        }

    async def _detect_partial_payments(self, data: dict) -> dict:
        """Detectar pagos parciales (importe menor a factura)."""
        _ = data.get("account_id")

        # TODO: Buscar movimientos bancarios donde importe < factura asociada
        # pero concepto similar

        partial_payments = []

        return {
            "success": True,
            "partial_payments": partial_payments,
            "count": len(partial_payments),
        }

    async def _detect_returns(self, data: dict) -> dict:
        """Detectar devoluciones (movimientos negativos o conceptos de devolución)."""
        _ = data.get("account_id")

        # Buscar movimientos negativos o conceptos con "devolución", "return"
        returns = []

        return {
            "success": True,
            "returns": returns,
            "count": len(returns),
        }

    async def _detect_fees(self, data: dict) -> dict:
        """Detectar comisiones bancarias."""
        _ = data.get("account_id")

        # Buscar conceptos: "comisión", "comision", "fee", "mantenimiento"
        fees = []

        return {
            "success": True,
            "fees": fees,
            "total_fees": sum(f.get("amount", 0) for f in fees),
        }

    async def _detect_unmatched_receipts(self, data: dict) -> dict:
        """Detectar cobros sin factura asociada."""
        _ = data.get("account_id")

        # Movimientos positivos sin factura de venta asociada
        unmatched = []

        return {
            "success": True,
            "unmatched_receipts": unmatched,
            "count": len(unmatched),
        }

    async def _detect_duplicate_payments(self, data: dict) -> dict:
        """Detectar pagos duplicados (mismo importe, mismo proveedor, fechas cercanas)."""
        _ = data.get("account_id")

        # Buscar pagos con mismo importe, mismo proveedor, fechas +/- 3 días
        duplicates = []

        return {
            "success": True,
            "duplicates": duplicates,
            "count": len(duplicates),
        }

    async def _forecast_cashflow(self, data: dict) -> dict:
        """Generar previsión de tesorería a 30/60/90 días."""
        _ = data.get("account_id")
        days = data.get("days", 90)

        # TODO:
        # 1. Saldo actual
        # 2. Cobros previstos (facturas pendientes + histórico)
        # 3. Pagos previstos (facturas proveedor + nóminas + impuestos + préstamos)
        # 4. Flujos recurrentes (nóminas, alquiler, leasing, seguros)
        # 4. Estacionalidad

        forecast = {
            "current_balance": 0,
            "forecast": [],
            "alerts": [],
        }

        # Simulación
        current = Decimal("50000")
        for day in range(1, days + 1):
            forecast_date = date.today() + timedelta(days=day)
            # Simular flujos
            daily_change = Decimal("0")
            current += daily_change

            if day % 30 == 0:
                forecast["forecast"].append(
                    {
                        "date": forecast_date.isoformat(),
                        "projected_balance": float(current),
                    }
                )

            if current < 10000:
                forecast["alerts"].append(
                    {
                        "date": forecast_date.isoformat(),
                        "type": "low_balance",
                        "message": f"Saldo proyectado bajo: {current}€",
                        "severity": "warning" if current > 0 else "critical",
                    }
                )

        return {
            "success": True,
            "forecast": forecast,
        }
