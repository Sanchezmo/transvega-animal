"""
Agente Contable - Asientos y contabilidad.
"""
import asyncio
from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List, Optional, Any
from uuid import uuid4
import structlog

logger = structlog.get_logger()


class AccountingAgent:
    """
    Agente Contable - Asientos y contabilidad.
    
    Responsabilidades:
    - Proponer asientos derivados de operaciones aprobadas
    - Preparar diarios
    - Revisar descuadres
    - Preparar balance
    - Preparar pérdidas y ganancias
    - Preparar sumas y saldos
    - Detectar saldos anómalos
    - Preparar conciliación contable
    
    No debe disponer de una herramienta genérica para crear cualquier asiento.
    Solo debe utilizar operaciones controladas como:
    - contabilizar_factura_cliente
    - contabilizar_factura_proveedor
    - registrar_cobro
    - registrar_pago
    - registrar_comision
    - proponer_reclasificacion
    - proponer_amortizacion
    """
    
    def __init__(self, config: Dict):
        self.config = config
        self.agent_id = "accounting"
        self.agent_name = "Accounting Agent"
        self.capabilities = [
            "contabilizar_factura_cliente",
            "contabilizar_factura_proveedor",
            "registrar_cobro",
            "registrar_pago",
            "registrar_comision",
            "proponer_reclasificacion",
            "proponer_amortizacion",
            "preparar_diario",
            "revisar_descuadres",
            "preparar_balance",
            "preparar_pyg",
            "preparar_sumas_saldos",
            "detectar_saldos_anomalos",
            "preparar_conciliacion_contable",
        ]
        self.restrictions = [
            "no_generic_entry_creation",
            "only_controlled_operations",
            "requires_approval_for_manual_entries",
        ]
    
    async def start(self):
        logger.info("starting_accounting_agent")
    
    async def stop(self):
        pass
    
    async def process_task(self, task: Dict) -> Dict:
        task_type = task.get("task_type")
        
        handlers = {
            "contabilizar_factura_cliente": self._contabilizar_factura_cliente,
            "contabilizar_factura_proveedor": self._contabilizar_factura_proveedor,
            "registrar_cobro": self._registrar_cobro,
            "registrar_pago": self._registrar_pago,
            "registrar_comision": self._registrar_comision,
            "proponer_reclasificacion": self._proponer_reclasificacion,
            "proponer_amortizacion": self._proponer_amortizacion,
            "preparar_diario": self._preparar_diario,
            "revisar_descuadres": self._revisar_descuadres,
            "preparar_balance": self._preparar_balance,
            "preparar_pyg": self._preparar_pyg,
            "preparar_sumas_saldos": self._preparar_sumas_saldos,
            "detectar_saldos_anomalos": self._detectar_saldos_anomalos,
            "preparar_conciliacion_contable": self._preparar_conciliacion_contable,
        }
        
        handler = handlers.get(task.get("task_type"))
        if not handler:
            return {"success": False, "error": f"Unknown task type: {task.get('task_type')}"}
        
        try:
            return await handler(task.get("input_data", {}))
        except Exception as e:
            logger.error("task_failed", task_type=task.get("task_type"), error=str(e))
            return {"success": False, "error": str(e)}
    
    # =========================================================================
    # OPERACIONES CONTROLADAS
    # =========================================================================
    
    async def _contabilizar_factura_cliente(self, data: Dict) -> Dict:
        """
        Contabilizar factura de cliente (venta).
        
        Asiento típico:
        Debe: 430000 - Clientes (total_ttc)
        Haber: 700000 - Ventas (total_ht)
        Haber: 477000 - IVA repercutido (total_tva)
        """
        invoice_data = data.get("invoice", {})
        lines = invoice_data.get("lines", [])
        
        # Calcular totales
        total_ht = sum(l.get("unit_price", 0) * l.get("qty", 1) * (1 - l.get("discount", 0)/100) for l in lines)
        total_tva = sum(l.get("unit_price", 0) * l.get("qty", 1) * (1 - l.get("discount", 0)/100) * l.get("vat_rate", 21)/100 for l in lines)
        total_ttc = total_ht + total_tva
        
        # Cliente
        client_id = invoice_data.get("client_id")
        
        entry = {
            "date": invoice_data.get("date", date.today().isoformat()),
            "reference": invoice_data.get("ref", ""),
            "description": f"Factura venta {invoice_data.get('ref', '')}",
            "lines": [
                {"account": "430000", "debit": round(total_ttc, 2), "credit": 0, "description": f"Cliente {client_id}"},
                {"account": "700000", "debit": 0, "credit": round(total_ht, 2), "description": "Ventas"},
                {"account": "477000", "debit": 0, "credit": round(total_tva, 2), "description": "IVA repercutido"},
            ],
        }
        
        # Validar cuadrado
        total_debit = sum(l["debit"] for l in entry["lines"])
        total_credit = sum(l["credit"] for l in entry["lines"])
        
        if abs(total_debit - total_credit) > 0.02:
            return {"success": False, "error": "Asiento no cuadra"}
        
        # TODO: Enviar a Dolibarr/contabilidad
        return {
            "success": True,
            "entry": entry,
            "message": "Asiento factura cliente preparado",
        }
    
    async def _contabilizar_factura_proveedor(self, data: Dict) -> Dict:
        """
        Contabilizar factura de proveedor (compra/gasto).
        
        Asiento típico:
        Debe: 600000/6XXXXX - Gasto/Compra (total_ht)
        Debe: 472000 - IVA soportado (total_tva)
        Haber: 400000 - Proveedores (total_ttc)
        """
        invoice_data = data.get("invoice", {})
        lines = invoice_data.get("lines", [])
        
        total_ht = sum(l.get("unit_price", 0) * l.get("qty", 1) * (1 - l.get("discount", 0)/100) for l in lines)
        total_tva = sum(l.get("unit_price", 0) * l.get("qty", 1) * (1 - l.get("discount", 0)/100) * l.get("vat_rate", 21)/100 for l in lines)
        total_ttc = total_ht + total_tva
        
        # Determinar cuenta de gasto según líneas
        expense_account = "600000"  # Por defecto compras
        # TODO: Determinar según categoría de líneas
        
        entry = {
            "date": date.today().isoformat(),
            "reference": invoice_data.get("ref", ""),
            "lines": [
                {"account": "600000", "debit": round(total_ht, 2), "credit": 0, "description": "Compra/servicio"},
                {"account": "472000", "debit": round(total_tva, 2), "credit": 0, "description": "IVA soportado"},
                {"account": "400000", "debit": 0, "credit": round(total_ttc, 2), "description": f"Proveedor {invoice_data.get('vendor_id')}"},
            ],
        }
        
        return {"success": True, "entry": entry, "message": "Asiento factura proveedor preparado"}
    
    async def _registrar_cobro(self, data: Dict) -> Dict:
        """Registrar cobro de cliente."""
        invoice_id = data.get("invoice_id")
        amount = data.get("amount")
        date_str = data.get("date", date.today().isoformat())
        method = data.get("method", "transfer")
        reference = data.get("reference", "")
        
        # Cobro factura cliente
        # Debe: 572000 - Bancos
        # Haber: 430000 - Clientes
        
        entry = {
            "date": date_str,
            "reference": reference,
            "lines": [
                {"account": "572000", "debit": round(amount, 2), "credit": 0, "description": f"Cobro factura {invoice_id}"},
                {"account": "430000", "debit": 0, "credit": round(amount, 2), "description": f"Cliente factura {invoice_id}"},
            ],
        }
        
        return {"success": True, "entry": entry, "message": "Cobro registrado"}
    
    async def _registrar_pago(self, data: Dict) -> Dict:
        """Registrar pago a proveedor."""
        invoice_id = data.get("invoice_id")
        amount = data.get("amount")
        date_str = data.get("date", date.today().isoformat())
        method = data.get("method", "transfer")
        reference = data.get("reference", "")
        
        # Pago factura proveedor
        # Debe: 400000 - Proveedores
        # Haber: 572000 - Bancos
        
        entry = {
            "date": date_str,
            "reference": reference,
            "lines": [
                {"account": "400000", "debit": round(amount, 2), "credit": 0, "description": f"Pago factura {invoice_id}"},
                {"account": "572000", "debit": 0, "credit": round(amount, 2), "description": f"Pago factura {invoice_id}"},
            ],
        }
        
        return {"success": True, "entry": entry, "message": "Pago registrado"}
    
    async def _registrar_comision(self, data: Dict) -> Dict:
        """Registrar comisión bancaria."""
        amount = data.get("amount")
        date_str = data.get("date", date.today().isoformat())
        description = data.get("description", "Comisión bancaria")
        
        # Debe: 626000 - Servicios bancarios
        # Haber: 572000 - Bancos
        
        entry = {
            "date": date_str,
            "lines": [
                {"account": "626000", "debit": round(amount, 2), "credit": 0, "description": description},
                {"account": "572000", "debit": 0, "credit": round(amount, 2), "description": "Comisión bancaria"},
            ],
        }
        
        return {"success": True, "entry": entry, "message": "Comisión registrada"}
    
    async def _proponer_reclasificacion(self, data: Dict) -> Dict:
        """Proponer reclasificación de cuentas."""
        from_account = data.get("from_account")
        to_account = data.get("to_account")
        amount = data.get("amount")
        reason = data.get("reason", "")
        
        entry = {
            "date": date.today().isoformat(),
            "reference": f"RECLASIFICACION: {reason}",
            "lines": [
                {"account": from_account, "debit": amount, "credit": 0, "description": f"Reclasificación a {to_account}"},
                {"account": to_account, "debit": 0, "credit": amount, "description": f"Reclasificación desde {from_account}"},
            ],
        }
        
        return {
            "success": True,
            "entry": entry,
            "message": "Reclasificación propuesta, requiere aprobación",
            "requires_approval": True,
        }
    
    async def _proponer_amortizacion(self, data: Dict) -> Dict:
        """Proponer amortización de inmovilizado."""
        asset_id = data.get("asset_id")
        asset_value = data.get("asset_value")
        useful_life_years = data.get("useful_life_years", 5)
        method = data.get("method", "linear")  # linear, decreasing
        
        annual_amortization = round(asset_value / useful_life_years, 2)
        monthly_amortization = round(annual_amortization / 12, 2)
        
        # Cuentas típicas
        # 681000 - Amortización inmovilizado
        # 280000 - Acum. amortización inmovilizado
        
        entry = {
            "date": date.today().isoformat(),
            "reference": f"AMORTIZACIÓN: Activo {asset_id}",
            "lines": [
                {"account": "681000", "debit": monthly_amortization, "credit": 0, "description": f"Amortización mensual activo {asset_id}"},
                {"account": "280000", "debit": 0, "credit": monthly_amortization, "description": f"Acum. amortización activo {asset_id}"},
            ],
        }
        
        return {
            "success": True,
            "entry": entry,
            "annual_amortization": annual_amortization,
            "monthly_amortization": monthly_amortization,
            "message": "Amortización propuesta, requiere aprobación",
            "requires_approval": True,
        }
    
    # =========================================================================
    # REPORTES Y ANÁLISIS
    # =========================================================================
    
    async def _preparar_diario(self, data: Dict) -> Dict:
        """Preparar libro diario."""
        date_from = data.get("date_from")
        date_to = data.get("date_to")
        
        # TODO: Consultar asientos en rango
        return {
            "success": True,
            "diario": [],
            "totals": {"debit": 0, "credit": 0},
            "period": {"from": date_from, "to": date_to},
        }
    
    async def _revisar_descuadres(self, data: Dict) -> Dict:
        """Revisar descuadres contables."""
        date_from = data.get("date_from")
        date_to = data.get("date_to")
        
        # Verificar:
        # 1. Asientos que no cuadran
        # 2. Cuentas con saldos anómalos
        # 3. Diferencias banco-contabilidad
        # 4. IVA repercutido vs soportado
        
        return {
            "success": True,
            "descuadres": [],
            "summary": {"total": 0, "by_type": {}},
        }
    
    async def _preparar_balance(self, data: Dict) -> Dict:
        """Preparar balance de situación."""
        as_of_date = data.get("date", date.today().isoformat())
        
        # TODO: Consultar saldos de cuentas
        return {
            "success": True,
            "balance": {
                "activo": {"total": 0, "detalle": {}},
                "pasivo": {"total": 0, "detalle": {}},
                "patrimonio_neto": {"total": 0, "detalle": {}},
            },
            "fecha": as_of_date,
        }
    
    async def _preparar_pyg(self, data: Dict) -> Dict:
        """Preparar cuenta de pérdidas y ganancias."""
        date_from = data.get("date_from")
        date_to = data.get("date_to")
        
        # TODO: Consultar cuentas 6 y 7
        return {
            "success": True,
            "pyg": {
                "ingresos": {"total": 0, "detalle": {}},
                "gastos": {"total": 0, "detalle": {}},
                "resultado": 0,
            },
            "period": {"from": date_from, "to": date_to},
        }
    
    async def _preparar_sumas_saldos(self, data: Dict) -> Dict:
        """Preparar sumas y saldos."""
        date_from = data.get("date_from")
        date_to = data.get("date_to")
        
        # TODO: Consultar saldos de todas las cuentas
        return {
            "success": True,
            "sumas_saldos": [],
            "totals": {"debit": 0, "credit": 0},
        }
    
    async def _detectar_saldos_anomalos(self, data: Dict) -> Dict:
        """Detectar saldos anómalos."""
        threshold = data.get("threshold", 10000)
        
        # TODO: Analizar saldos
        anomalias = []
        
        return {
            "success": True,
            "anomalias": anomalias,
            "count": len(anomalias),
        }
    
    async def _preparar_conciliacion_contable(self, data: Dict) -> Dict:
        """Preparar conciliación bancaria contable."""
        account_id = data.get("account_id")
        date_from = data.get("date_from")
        date_to = data.get("date_to")
        
        # TODO: Conciliar extractos vs contabilidad
        return {
            "success": True,
            "conciliacion": {
                "saldo_banco": 0,
                "saldo_contabilidad": 0,
                "diferencia": 0,
                "pendientes_cobro": [],
                "pendientes_pago": [],
            },
        }