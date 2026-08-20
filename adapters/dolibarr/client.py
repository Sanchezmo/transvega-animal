"""
Cliente HTTP para comunicación con Dolibarr API.
"""

from typing import Any

import httpx
import structlog

from app.core.config import get_settings
from app.core.exceptions import DolibarrException
from app.utils.tax_id import normalize_tax_id

logger = structlog.get_logger()
settings = get_settings()


class DolibarrClient:
    """Cliente para API REST de Dolibarr."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: int = 30,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "DolibarrClient":
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "DOLAPIKEY": self.api_key,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=self.timeout,
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> None:
        if self._client:
            await self._client.aclose()

    @property
    def client(self) -> httpx.AsyncClient:
        if not self._client:
            raise RuntimeError("DolibarrClient not initialized. Use async context manager.")
        return self._client

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Realizar petición HTTP con manejo de errores."""
        # Handle both Dolibarr API format (/api/index.php/...) and mock format (direct)
        if self.base_url.endswith(":8001"):  # Mock Dolibarr
            url = f"/{endpoint.lstrip('/')}"
        else:
            url = f"/api/index.php/{endpoint.lstrip('/')}"

        try:
            response = await self.client.request(
                method=method,
                url=url,
                params=params,
                json=json,
                data=data,
            )

            # Dolibarr devuelve 200/201 en éxito, 400+ en error
            if response.status_code >= 400:
                try:
                    error_data = response.json()
                except Exception:
                    error_data = {"message": response.text}

                raise DolibarrException(
                    message=error_data.get("error", {}).get("message", f"HTTP {response.status_code}"),
                    endpoint=endpoint,
                    status_code=response.status_code,
                    details=error_data,
                )

            if response.status_code == 204:  # No content
                return {}

            return response.json()

        except httpx.TimeoutException:
            raise DolibarrException(
                message="Timeout conectando con Dolibarr",
                endpoint=endpoint,
                status_code=504,
            )
        except httpx.RequestError as e:
            raise DolibarrException(
                message=f"Error de conexión: {e}",
                endpoint=endpoint,
                status_code=502,
            )

    # =========================================================================
    # HEALTH CHECK
    # =========================================================================

    async def health_check(self) -> bool:
        """Verificar conectividad con Dolibarr."""
        try:
            # Endpoint simple que siempre existe
            await self._request("GET", "thirdparties", params={"limit": 1})
            return True
        except Exception:
            return False

    # =========================================================================
    # TERCEROS
    # =========================================================================

    async def list_thirdparties(
        self,
        limit: int = 100,
        offset: int = 0,
        sortfield: str = "rowid",
        sortorder: str = "ASC",
        sqlfilters: str | None = None,
    ) -> list[dict[str, Any]]:
        params = {
            "limit": limit,
            "offset": offset,
            "sortfield": sortfield,
            "sortorder": sortorder,
        }
        if sqlfilters:
            params["sqlfilters"] = sqlfilters

        result = await self._request("GET", "thirdparties", params=params)
        return result.get("data", []) if isinstance(result, dict) else result

    async def iter_all_thirdparties(
        self,
        page_size: int = 100,
        sqlfilters: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Iterate through ALL thirdparties using pagination.
        Returns complete list - use with caution for large datasets.
        For targeted searches, prefer find_thirdparty_by_tax_id.
        """
        all_parties = []
        offset = 0
        while True:
            parties = await self.list_thirdparties(
                limit=page_size,
                offset=offset,
                sqlfilters=sqlfilters,
            )
            if not parties:
                break
            all_parties.extend(parties)
            if len(parties) < page_size:
                break
            offset += page_size
        return all_parties

    async def find_thirdparty_by_tax_id(
        self,
        tax_id: str,
        page_size: int = 100,
        max_pages: int = 50,
    ) -> dict[str, Any] | None:
        """
        Find a thirdparty by normalized tax_id (CIF/NIF) using pagination.
        Searches through pages until found or max_pages reached.
        """
        if not tax_id:
            return None
        normalized_search = normalize_tax_id(tax_id)

        offset = 0
        pages_checked = 0
        while pages_checked < max_pages:
            parties = await self.list_thirdparties(
                limit=page_size,
                offset=offset,
            )
            if not parties:
                break

            for party in parties:
                party_vat = normalize_tax_id(party.get("vat_number", "") or party.get("vatnumber", ""))
                if party_vat == normalized_search:
                    return party

            if len(parties) < page_size:
                break
            offset += page_size
            pages_checked += 1

        return None

    async def get_thirdparty(self, thirdparty_id: int) -> dict[str, Any]:
        return await self._request("GET", f"thirdparties/{thirdparty_id}")

    async def create_thirdparty(self, data: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] | int = await self._request("POST", "thirdparties", json=data)
        # Handle different response formats:
        # - Mock: {"success": true, "data": {...}, "id": 21}
        # - Real Dolibarr: integer ID (e.g., "6") or full object
        if isinstance(result, dict) and "data" in result:
            return result["data"]
        elif isinstance(result, int):
            # Real Dolibarr returns just the ID on create, fetch the full object
            return await self.get_thirdparty(result)
        return result

    async def update_thirdparty(self, thirdparty_id: int, data: dict[str, Any]) -> dict[str, Any]:
        return await self._request("PUT", f"thirdparties/{thirdparty_id}", json=data)

    async def delete_thirdparty(self, thirdparty_id: int) -> dict[str, Any]:
        return await self._request("DELETE", f"thirdparties/{thirdparty_id}")

    # =========================================================================
    # PRODUCTOS
    # =========================================================================

    async def list_products(
        self,
        limit: int = 100,
        offset: int = 0,
        sortfield: str = "rowid",
        sortorder: str = "ASC",
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit, "offset": offset, "sortfield": sortfield, "sortorder": sortorder}
        result = await self._request("GET", "products", params=params)
        return result.get("data", []) if isinstance(result, dict) else result

    async def get_product(self, product_id: int) -> dict[str, Any]:
        return await self._request("GET", f"products/{product_id}")

    async def create_product(self, data: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "products", json=data)

    async def update_product(self, product_id: int, data: dict[str, Any]) -> dict[str, Any]:
        return await self._request("PUT", f"products/{product_id}", json=data)

    async def delete_product(self, product_id: int) -> dict[str, Any]:
        return await self._request("DELETE", f"products/{product_id}")

    # =========================================================================
    # EXPEDIENTES ANIMALES (Módulo personalizado)
    # =========================================================================

    async def list_expedientes(
        self,
        limit: int = 100,
        offset: int = 0,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if status:
            params["sqlfilters"] = f"commercial_status:='{status}'"
        result = await self._request("GET", "expedientes_animal", params=params)
        return result.get("data", []) if isinstance(result, dict) else result

    async def get_expediente(self, expediente_id: int) -> dict[str, Any]:
        return await self._request("GET", f"expedientes_animal/{expediente_id}")

    async def create_expediente(self, data: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "expedientes_animal", json=data)

    async def update_expediente(self, expediente_id: int, data: dict[str, Any]) -> dict[str, Any]:
        return await self._request("PUT", f"expedientes_animal/{expediente_id}", json=data)

    async def delete_expediente(self, expediente_id: int) -> dict[str, Any]:
        return await self._request("DELETE", f"expedientes_animal/{expediente_id}")

    # =========================================================================
    # FACTURAS
    # =========================================================================

    async def list_invoices(
        self,
        limit: int = 100,
        offset: int = 0,
        status: int | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if status is not None:
            params["status"] = status
        result = await self._request("GET", "invoices", params=params)
        return result.get("data", []) if isinstance(result, dict) else result

    async def get_invoice(self, invoice_id: int) -> dict[str, Any]:
        return await self._request("GET", f"invoices/{invoice_id}")

    async def create_invoice(self, data: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "invoices", json=data)

    async def update_invoice(self, invoice_id: int, data: dict[str, Any]) -> dict[str, Any]:
        return await self._request("PUT", f"invoices/{invoice_id}", json=data)

    async def validate_invoice(self, invoice_id: int) -> dict[str, Any]:
        """Validar factura (pasar de borrador a validada)."""
        return await self._request("POST", f"invoices/{invoice_id}/validate")

    async def cancel_invoice(self, invoice_id: int) -> dict[str, Any]:
        """Anular factura."""
        return await self._request("POST", f"invoices/{invoice_id}/cancel")

    # =========================================================================
    # PEDIDOS
    # =========================================================================

    async def list_orders(
        self,
        limit: int = 100,
        offset: int = 0,
        status: int | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if status is not None:
            params["status"] = status
        result = await self._request("GET", "orders", params=params)
        return result.get("data", []) if isinstance(result, dict) else result

    async def get_order(self, order_id: int) -> dict[str, Any]:
        return await self._request("GET", f"orders/{order_id}")

    async def create_order(self, data: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "orders", json=data)

    async def update_order(self, order_id: int, data: dict[str, Any]) -> dict[str, Any]:
        return await self._request("PUT", f"orders/{order_id}", json=data)

    # =========================================================================
    # PROPUESTAS COMERCIALES (PROPALS)
    # =========================================================================

    async def list_propals(
        self,
        limit: int = 100,
        offset: int = 0,
        status: int | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if status is not None:
            params["status"] = status
        result = await self._request("GET", "propals", params=params)
        return result.get("data", []) if isinstance(result, dict) else result

    async def get_propal(self, propal_id: int) -> dict[str, Any]:
        return await self._request("GET", f"propals/{propal_id}")

    async def create_propal(self, data: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "propals", json=data)

    async def update_propal(self, propal_id: int, data: dict[str, Any]) -> dict[str, Any]:
        return await self._request("PUT", f"propals/{propal_id}", json=data)

    async def convert_propal_to_order(self, propal_id: int) -> dict[str, Any]:
        """Convertir propuesta en pedido."""
        return await self._request("POST", f"propals/{propal_id}/convert_to_order")

    # =========================================================================
    # EXPEDICIONES/ENVIOS
    # =========================================================================

    async def list_shipments(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        result = await self._request("GET", "shipments", params=params)
        return result.get("data", []) if isinstance(result, dict) else result

    async def get_shipment(self, shipment_id: int) -> dict[str, Any]:
        return await self._request("GET", f"shipments/{shipment_id}")

    async def create_shipment(self, data: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "shipments", json=data)

    # =========================================================================
    # CONTACTOS
    # =========================================================================

    async def list_contacts(self, thirdparty_id: int) -> list[dict[str, Any]]:
        result = await self._request("GET", f"thirdparties/{thirdparty_id}/contacts")
        return result.get("data", []) if isinstance(result, dict) else result

    async def create_contact(self, thirdparty_id: int, data: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", f"thirdparties/{thirdparty_id}/contacts", json=data)

    # =========================================================================
    # DOCUMENTOS ADJUNTOS
    # =========================================================================

    async def upload_document(
        self, resource_type: str, resource_id: int, file_data: bytes, filename: str
    ) -> dict[str, Any]:
        """Subir documento adjunto a un recurso usando multipart/form-data."""
        # Handle both Dolibarr API format and mock format
        if self.base_url.endswith(":8001"):  # Mock Dolibarr
            url = f"/{resource_type}/{resource_id}/documents"
        else:
            url = f"/api/index.php/{resource_type}/{resource_id}/documents"

        # Create multipart form data
        files = {"file": (filename, file_data)}

        # Need to remove Content-Type header to let httpx set multipart boundary
        headers = {
            "DOLAPIKEY": self.api_key,
            "Accept": "application/json",
            # Content-Type will be set automatically by httpx for multipart
        }

        try:
            # Create a temporary client with multipart headers
            async with httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=self.timeout,
            ) as client:
                response = await client.post(url, files=files)

            if response.status_code >= 400:
                try:
                    error_data = response.json()
                except Exception:
                    error_data = {"message": response.text}

                raise DolibarrException(
                    message=error_data.get("error", {}).get("message", f"HTTP {response.status_code}"),
                    endpoint=url,
                    status_code=response.status_code,
                    details=error_data,
                )

            if response.status_code == 204:
                return {}

            return response.json()

        except httpx.TimeoutException:
            raise DolibarrException(
                message="Timeout conectando con Dolibarr",
                endpoint=url,
                status_code=504,
            )
        except httpx.RequestError as e:
            raise DolibarrException(
                message=f"Error de conexión: {e}",
                endpoint=url,
                status_code=502,
            )

    async def list_documents(self, resource_type: str, resource_id: int) -> list[dict[str, Any]]:
        result = await self._request("GET", f"{resource_type}/{resource_id}/documents")
        return result.get("data", []) if isinstance(result, dict) else result

    # =========================================================================
    # USUARIOS
    # =========================================================================

    async def list_users(self) -> list[dict[str, Any]]:
        result = await self._request("GET", "users")
        return result.get("data", []) if isinstance(result, dict) else result

    async def get_user(self, user_id: int) -> dict[str, Any]:
        return await self._request("GET", f"users/{user_id}")

    # =========================================================================
    # PROVEEDORES (TERCEROS CON SUPPLIER=1)
    # =========================================================================

    async def list_suppliers(
        self,
        limit: int = 100,
        offset: int = 0,
        sortfield: str = "rowid",
        sortorder: str = "ASC",
        sqlfilters: str | None = None,
) -> list[dict[str, Any]]:
        """List suppliers by fetching thirdparties and filtering in memory.

        Note: Dolibarr's sqlfilters syntax for fournisseur is problematic.
        We fetch all and filter in memory to avoid API syntax issues.
        """
        # Fetch a larger set to filter in memory
        fetch_limit = max(limit * 5, 500)
        params: dict[str, Any] = {
            "limit": fetch_limit,
            "offset": offset,
            "sortfield": sortfield,
            "sortorder": sortorder,
        }
        if sqlfilters:
            params["sqlfilters"] = sqlfilters

        result = await self._request("GET", "thirdparties", params=params)
        all_parties = result.get("data", []) if isinstance(result, dict) else result

        # Filter for suppliers (fournisseur=1 or supplier=1)
        suppliers = [
            p for p in all_parties
            if p.get("fournisseur") == 1 or p.get("supplier") == 1
        ]

        # Apply pagination after filtering
        return suppliers[:limit]

    async def get_supplier(self, supplier_id: int) -> dict[str, Any]:
        return await self._request("GET", f"thirdparties/{supplier_id}")  # type: ignore[no-any-return]

    async def create_supplier(self, data: dict[str, Any]) -> dict[str, Any]:
        """Crear proveedor. Asegura fournisseur=1 y client=0."""
        data["fournisseur"] = 1
        data["client"] = 0
        result: dict[str, Any] | int = await self._request("POST", "thirdparties", json=data)
        if isinstance(result, dict) and "data" in result:
            return result["data"]
        elif isinstance(result, int):
            return await self.get_supplier(result)
        return result

    async def update_supplier(self, supplier_id: int, data: dict[str, Any]) -> dict[str, Any]:
        data["fournisseur"] = 1
        data["client"] = 0
        return await self._request("PUT", f"thirdparties/{supplier_id}", json=data)

    async def delete_supplier(self, supplier_id: int) -> dict[str, Any]:
        return await self._request("DELETE", f"thirdparties/{supplier_id}")

    # =========================================================================
    # FACTURAS PROVEEDOR (SUPPLIER INVOICES)
    # =========================================================================

    async def list_supplier_invoices(
        self,
        limit: int = 100,
        offset: int = 0,
        status: int | None = None,
        thirdparty_id: int | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if status is not None:
            params["status"] = status
        if thirdparty_id is not None:
            params["thirdparty_ids"] = str(thirdparty_id)
        result = await self._request("GET", "supplierinvoices", params=params)
        return result.get("data", []) if isinstance(result, dict) else result

    async def get_supplier_invoice(self, invoice_id: int) -> dict[str, Any]:
        return await self._request("GET", f"supplierinvoices/{invoice_id}")

    async def create_supplier_invoice(self, data: dict[str, Any]) -> dict[str, Any]:
        """Crear factura de proveedor. Requiere socid (ID proveedor)."""
        # Dolibarr usa 'socid' para el proveedor
        if "thirdparty_id" in data and "socid" not in data:
            data["socid"] = data.pop("thirdparty_id")
        result: dict[str, Any] | int = await self._request("POST", "supplierinvoices", json=data)
        if isinstance(result, dict) and "data" in result:
            return result["data"]
        elif isinstance(result, int):
            return await self.get_supplier_invoice(result)
        return result

    async def update_supplier_invoice(self, invoice_id: int, data: dict[str, Any]) -> dict[str, Any]:
        return await self._request("PUT", f"supplierinvoices/{invoice_id}", json=data)  # type: ignore[no-any-return]

    async def validate_supplier_invoice(self, invoice_id: int) -> dict[str, Any]:
        """Validar factura proveedor (pasar de borrador a validada)."""
        return await self._request("POST", f"supplierinvoices/{invoice_id}/validate")  # type: ignore[no-any-return]

    async def cancel_supplier_invoice(self, invoice_id: int) -> dict[str, Any]:
        """Anular factura proveedor."""
        return await self._request("POST", f"supplierinvoices/{invoice_id}/cancel")  # type: ignore[no-any-return]

    async def add_supplier_invoice_line(self, invoice_id: int, line_data: dict[str, Any]) -> dict[str, Any]:
        """Añadir línea a factura proveedor."""
        return await self._request("POST", f"supplierinvoices/{invoice_id}/lines", json=line_data)  # type: ignore[no-any-return]

    async def update_supplier_invoice_line(
        self, invoice_id: int, line_id: int, line_data: dict[str, Any]
    ) -> dict[str, Any]:
        return await self._request("PUT", f"supplierinvoices/{invoice_id}/lines/{line_id}", json=line_data)  # type: ignore[no-any-return]

    async def delete_supplier_invoice_line(self, invoice_id: int, line_id: int) -> dict[str, Any]:
        return await self._request("DELETE", f"supplierinvoices/{invoice_id}/lines/{line_id}")  # type: ignore[no-any-return]

    # =========================================================================
    # PEDIDOS PROVEEDOR (SUPPLIER ORDERS / ÓRDENES DE COMPRA)
    # =========================================================================

    async def list_supplier_orders(
        self,
        limit: int = 100,
        offset: int = 0,
        status: int | None = None,
        thirdparty_id: int | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if status is not None:
            params["status"] = status
        if thirdparty_id is not None:
            params["thirdparty_ids"] = str(thirdparty_id)
        result = await self._request("GET", "supplierorders", params=params)
        return result.get("data", []) if isinstance(result, dict) else result

    async def get_supplier_order(self, order_id: int) -> dict[str, Any]:
        return await self._request("GET", f"supplierorders/{order_id}")

    async def create_supplier_order(self, data: dict[str, Any]) -> dict[str, Any]:
        if "thirdparty_id" in data and "socid" not in data:
            data["socid"] = data.pop("thirdparty_id")
        result = await self._request("POST", "supplierorders", json=data)
        if isinstance(result, dict) and "data" in result:
            return result["data"]
        elif isinstance(result, int):
            return await self.get_supplier_order(result)
        return result

    async def update_supplier_order(self, order_id: int, data: dict[str, Any]) -> dict[str, Any]:
        return await self._request("PUT", f"supplierorders/{order_id}", json=data)

    async def validate_supplier_order(self, order_id: int) -> dict[str, Any]:
        return await self._request("POST", f"supplierorders/{order_id}/validate")

    async def add_supplier_order_line(self, order_id: int, line_data: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", f"supplierorders/{order_id}/lines", json=line_data)

    # =========================================================================
    # PROPUESTAS PROVEEDOR (SUPPLIER PROPOSALS)
    # =========================================================================

    async def list_supplier_proposals(
        self,
        limit: int = 100,
        offset: int = 0,
        status: int | None = None,
        thirdparty_id: int | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if status is not None:
            params["status"] = status
        if thirdparty_id is not None:
            params["thirdparty_ids"] = str(thirdparty_id)
        result = await self._request("GET", "supplierproposals", params=params)
        return result.get("data", []) if isinstance(result, dict) else result

    async def get_supplier_proposal(self, proposal_id: int) -> dict[str, Any]:
        return await self._request("GET", f"supplierproposals/{proposal_id}")

    async def create_supplier_proposal(self, data: dict[str, Any]) -> dict[str, Any]:
        if "thirdparty_id" in data and "socid" not in data:
            data["socid"] = data.pop("thirdparty_id")
        result = await self._request("POST", "supplierproposals", json=data)
        if isinstance(result, dict) and "data" in result:
            return result["data"]
        elif isinstance(result, int):
            return await self.get_supplier_proposal(result)
        return result

    async def update_supplier_proposal(self, proposal_id: int, data: dict[str, Any]) -> dict[str, Any]:
        return await self._request("PUT", f"supplierproposals/{proposal_id}", json=data)

    async def convert_supplier_proposal_to_order(self, proposal_id: int) -> dict[str, Any]:
        return await self._request("POST", f"supplierproposals/{proposal_id}/convert_to_order")

    # =========================================================================
    # RECEPCIONES (PROVEEDOR - RECEIPTS)
    # =========================================================================

    async def list_supplier_receipts(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        result = await self._request("GET", "supplierreceipts", params=params)
        return result.get("data", []) if isinstance(result, dict) else result

    async def get_supplier_receipt(self, receipt_id: int) -> dict[str, Any]:
        return await self._request("GET", f"supplierreceipts/{receipt_id}")

    async def create_supplier_receipt(self, data: dict[str, Any]) -> dict[str, Any]:
        result = await self._request("POST", "supplierreceipts", json=data)
        if isinstance(result, dict) and "data" in result:
            return result["data"]
        elif isinstance(result, int):
            return await self.get_supplier_receipt(result)
        return result
