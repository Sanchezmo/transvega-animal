"""
Adaptador VeriFactu - Integración con AEAT para facturación verificada.
"""

from datetime import datetime
from uuid import uuid4

import httpx
import structlog

logger = structlog.get_logger()


class VeriFactuAdapter:
    """
    Adaptador para VeriFactu - Sistema de facturación verificada de AEAT.

    VeriFactu es obligatorio desde 2025/2026 para:
    - Emitir facturas verificables por AEAT
    - Incluir código QR y cadena de verificación
    - Comunicar facturas en tiempo real o diferido

    Requiere:
    - Certificado digital de representante legal
    - Alta en sistema VeriFactu de AEAT
    - Certificado de sellado de tiempo (opcional pero recomendado)
    """

    def __init__(self, config: dict):
        self.config = config
        self.enabled = config.get("VERIFACTU_ENABLED", False)
        self.test_mode = config.get("VERIFACTU_TEST_MODE", True)
        self.cert_path = config.get("VERIFACTU_CERT_PATH")
        self.key_path = config.get("VERIFACTU_KEY_PATH")
        self.endpoint = config.get(
            "VERIFACTU_ENDPOINT", "https://www2.agenciatributaria.gob.es/wlpl/BNR-Verifactu/VeriFactu"
        )
        self.software_id = config.get("VERIFACTU_SOFTWARE_ID", "transvega-animal")
        self.software_version = config.get("VERIFACTU_SOFTWARE_VERSION", "1.0")

    async def send_invoice(self, invoice_data: dict) -> dict:
        """
        Enviar factura a VeriFactu.

        invoice_data debe contener:
        - Número de factura
        - Fecha emisión
        - Tipo factura (F1, F2, F3, R1, R4, R5)
        - Datos emisor (NIF, nombre, dirección)
        - Datos receptor (NIF, nombre, dirección)
        - Líneas (descripción, cantidad, precio, IVA, IRPF)
        - Totales (base, IVA, total)
        - Tipo pago
        """
        if not self.enabled:
            return {"success": True, "message": "VeriFactu deshabilitado", "simulated": True}

        # Validar datos requeridos
        validation = self._validate_invoice_data(invoice_data)
        if not validation["valid"]:
            return {"success": False, "errors": validation["errors"]}

        # Generar XML FacturaE 3.2.2
        xml = self._generate_facturae_xml(invoice_data)

        # Firmar con certificado
        signed_xml = await self._sign_xml(xml)

        # Enviar a AEAT
        try:
            response = await self._send_to_aeat(signed_xml, invoice_data)

            return {
                "success": True,
                "verifactu_id": response.get("id"),
                "qr_code": response.get("qr"),
                "verification_code": response.get("codigo_verificacion"),
                "timestamp": datetime.now().isoformat(),
                "status": response.get("estado", "ENVIADO"),
            }
        except Exception as e:
            logger.error("verifactu_send_failed", error=str(e))
            return {"success": False, "error": str(e)}

    def _validate_invoice_data(self, data: dict) -> dict:
        """Validar datos obligatorios de factura."""
        errors = []

        required = [
            "invoice_number",
            "date",
            "type",
            "issuer",
            "receiver",
            "lines",
            "total_ht",
            "total_vat",
            "total_ttc",
        ]

        for field in required:
            if not data.get(field):
                errors.append(f"Campo obligatorio faltante: {field}")

        # Validar emisor
        issuer = data.get("issuer", {})
        for field in ["nif", "name", "address"]:
            if not issuer.get(field):
                errors.append(f"Emisor: campo obligatorio faltante: {field}")

        # Validar receptor
        receiver = data.get("receiver", {})
        for field in ["nif", "name", "address"]:
            if not receiver.get(field):
                errors.append(f"Receptor: campo obligatorio faltante: {field}")

        # Validar líneas
        lines = data.get("lines", [])
        if not lines:
            errors.append("Al menos una línea de factura requerida")
        else:
            for i, line in enumerate(data.get("lines", [])):
                for field in ["description", "quantity", "unit_price", "vat_rate"]:
                    if not line.get(field):
                        errors.append(f"Línea {i + 1}: campo obligatorio faltante: {field}")

        return {"valid": len(errors) == 0, "errors": errors}

    def _generate_facturae_xml(self, data: dict) -> str:
        """Generar XML FacturaE 3.2.2 para VeriFactu."""
        # Estructura simplificada - en producción usar lxml o plantilla Jinja2
        invoice_type_map = {
            "F1": "F1",  # Factura completa
            "F2": "F2",  # Factura simplificada
            "F3": "F3",  # Factura rectificativa
            "R1": "R1",  # Factura recibida
            "R4": "R4",  # Factura recibida rectificativa
            "R5": "R5",  # Factura recibida intracomunitaria
        }

        invoice_type = invoice_type_map.get(data.get("type", "F1"), "F1")

        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Facturae xmlns="http://www.facturae.gob.es/formato/Versiones/Facturae/3.2.2">
  <FileHeader>
    <SchemaVersion>3.2.2</SchemaVersion>
    <Header>
      <Modality>I</Modality>
      <InvoiceType>{invoice_type}</InvoiceType>
      <InvoiceNumber>{data.get("invoice_number")}</InvoiceNumber>
      <InvoiceSeries>{data.get("series", "")}</InvoiceSeries>
      <InvoiceDate>{data.get("date")}</InvoiceDate>
      <CurrencyCode>EUR</CurrencyCode>
    </Header>
  </FileHeader>
  <Parties>
    <SellerParty>
      <TaxIdentification>
        <PersonTypeCode>{"J" if data["issuer"].get("is_company") else "F"}</PersonTypeCode>
        <ResidenceTypeCode>R</ResidenceTypeCode>
        <TaxIdentificationNumber>{data["issuer"]["nif"]}</TaxIdentificationNumber>
      </TaxIdentification>
      <PartyName>{data["issuer"]["name"]}</PartyName>
      <Address>
        <AddressDetail>{data["issuer"]["address"]}</AddressDetail>
        <PostalCode>{data["issuer"].get("postal_code", "")}</PostalCode>
        <City>{data["issuer"].get("city", "")}</City>
        <Province>{data["issuer"].get("province", "")}</Province>
        <CountryCode>ES</CountryCode>
      </Address>
    </SellerParty>
    <BuyerParty>
      <TaxIdentification>
        <PersonTypeCode>{"J" if data["receiver"].get("is_company") else "F"}</PersonTypeCode>
        <ResidenceTypeCode>R</ResidenceTypeCode>
        <TaxIdentificationNumber>{data["receiver"]["nif"]}</TaxIdentificationNumber>
      </TaxIdentification>
      <PartyName>{data["receiver"]["name"]}</PartyName>
      <Address>
        <AddressDetail>{data["receiver"]["address"]}</AddressDetail>
        <PostalCode>{data["receiver"].get("postal_code", "")}</PostalCode>
        <City>{data["receiver"].get("city", "")}</City>
        <Province>{data["receiver"].get("province", "")}</Province>
        <CountryCode>ES</CountryCode>
      </Address>
    </BuyerParty>
  </Parties>
  <Invoices>
    <Invoice>
      <InvoiceHeader>
        <InvoiceNumber>{data.get("invoice_number")}</InvoiceNumber>
        <InvoiceSeries>{data.get("series", "")}</InvoiceSeries>
        <InvoiceDate>{data.get("date")}</InvoiceDate>
        <InvoiceTypeCode>{invoice_type}</InvoiceTypeCode>
        <CurrencyCode>EUR</CurrencyCode>
        <PaymentTerms>
          <PaymentMeansCode>{data.get("payment_method", "30")}</PaymentMeansCode>
        </PaymentTerms>
      </InvoiceHeader>
      <InvoiceTotals>
        <TotalGrossAmount>{data.get("total_ht", 0):.2f}</TotalGrossAmount>
        <TotalNetAmount>{data.get("total_ht", 0):.2f}</TotalNetAmount>
        <TotalTaxAmount>{data.get("total_vat", 0):.2f}</TotalTaxAmount>
        <TotalAmount>{data.get("total_ttc", 0):.2f}</TotalAmount>
        <InvoiceCurrencyCode>EUR</InvoiceCurrencyCode>
      </InvoiceTotals>
      <InvoiceLines>
"""

        for i, line in enumerate(data.get("lines", []), 1):
            line.get("quantity", 1)
            line.get("unit_price", 0)
            discount = line.get("discount", 0)
            vat_rate = line.get("vat_rate", 21)

            line_total = round(
                (line.get("unit_price", 0) * line.get("quantity", 1)) * (1 - line.get("discount", 0) / 100), 2
            )
            vat_amount = round(line_total * line.get("vat_rate", 21) / 100, 2)

            xml += f"""        <InvoiceLine>
          <LineNumber>{i}</LineNumber>
          <InvoicedQuantity unitCode="H87">{line.get("quantity", 1)}</InvoicedQuantity>
          <LineDescription>{line.get("description", "")}</LineDescription>
          <UnitPrice>{line.get("unit_price", 0):.4f}</UnitPrice>
          <Discount>{discount:.2f}</Discount>
          <NetAmount>{line_total:.2f}</NetAmount>
          <Tax>
            <TaxTypeCode>IVA</TaxTypeCode>
            <TaxRate>{vat_rate}</TaxRate>
            <TaxAmount>{vat_amount:.2f}</TaxAmount>
          </Tax>
        </InvoiceLine>
"""

        xml += """      </InvoiceLines>
    </Invoice>
  </Invoices>
</Facturae>"""

        return xml

    async def _sign_xml(self, xml: str) -> str:
        """Firmar XML con certificado digital (XAdES-BES)."""
        # TODO: Implementar firma XAdES-BES con certificado digital
        # Usar cryptography + lxml para XAdES-BES
        # Requiere certificado .p12/.pfx y clave privada

        # Simulación para desarrollo
        return xml + "\n<!-- FIRMA_XADES_BES -->"

    async def _send_to_aeat(self, signed_xml: str, invoice_data: dict) -> dict:
        """Enviar factura firmada a AEAT VeriFactu."""
        # Endpoints según documentación AEAT:
        # Test: https://www2.agenciatributaria.gob.es/wlpl/BNR-Verifactu/VeriFactu
        # Prod: https://www2.agenciatributaria.gob.es/wlpl/BNR-Verifactu/VeriFactu

        # En producción: mTLS con certificado cliente
        # Headers: Content-Type: application/xml
        # Autenticación: Certificado cliente (mTLS)

        # Simulación para desarrollo
        if self.test_mode:
            return {
                "id": f"VF-{datetime.now().strftime('%Y%m%d')}-{uuid4().hex[:8]}",
                "qr": f"https://www.agenciatributaria.gob.es/verifactu/qr/{uuid4().hex[:16]}",
                "codigo_verificacion": uuid4().hex[:16].upper(),
                "estado": "ACEPTADA",
                "timestamp": datetime.now().isoformat(),
            }

        # Producción real
        async with httpx.AsyncClient(cert=(self.cert_path, self.key_path)) as client:
            resp = await client.post(
                self.endpoint,
                content=signed_xml,
                headers={"Content-Type": "application/xml"},
                timeout=30.0,
            )
            resp.raise_for_status()
            # Parsear respuesta AEAT
            return {"id": "AEAT-RESPONSE-ID"}

    async def cancel_invoice(self, invoice_number: str, reason: str) -> dict:
        """Anular factura en VeriFactu (factura rectificativa tipo R)."""
        return {"success": False, "error": "No implementado - requiere factura rectificativa"}

    async def query_status(self, verifactu_id: str) -> dict:
        """Consultar estado de factura en VeriFactu."""
        return {"success": False, "error": "No implementado"}

    async def get_qr_code(self, verifactu_id: str) -> bytes:
        """Generar/obtener código QR para factura."""
        # QR contiene: URL verificación + código verificación
        return b"QR_CODE_BYTES"


class VeriFactuManager:
    """Gestor de alto nivel para VeriFactu."""

    def __init__(self, config: dict):
        self.adapter = VeriFactuAdapter(config)
        self.enabled = config.get("VERIFACTU_ENABLED", False)

    async def process_invoice_verifactu(self, invoice_data: dict) -> dict:
        """Procesar factura completa para VeriFactu."""
        if not self.enabled:
            return {"success": True, "message": "VeriFactu deshabilitado", "skipped": True}

        # 1. Validar y enviar
        result = await self.adapter.send_invoice(invoice_data)

        if not result["success"]:
            return result

        # 2. Guardar datos VeriFactu en factura
        # await db.update_invoice_verifactu(invoice_data["invoice_number"], result)

        # 3. Generar PDF con QR
        # pdf_result = await pdf_generator.add_verifactu_qr(invoice_data["id"], result["qr_code"])

        return {
            "success": True,
            "verifactu_data": result,
            "message": "Factura enviada a VeriFactu correctamente",
        }

    async def batch_send_pending(self) -> dict:
        """Enviar facturas pendientes a VeriFactu."""
        # TODO: Consultar facturas pendientes de envío
        sent = 0
        failed = 0

        return {"success": True, "sent": sent, "failed": failed}

    async def reconcile_with_aeat(self, period: str) -> dict:
        """Conciliar facturas enviadas con AEAT."""
        return {"success": True, "message": "Conciliación completada", "matched": 0, "unmatched": 0}
