"""
Cliente HTTP para comunicación con Dolibarr API.
"""
import httpx
from typing import Optional, List, Dict, Any
from datetime import datetime
import structlog

from app.core.config import get_settings
from app.core.exceptions import DolibarrException

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
        self._client: Optional[httpx.AsyncClient] = None
    
    async def __aenter__(self):
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
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
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
        params: Optional[Dict] = None,
        json: Optional[Dict] = None,
        data: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Realizar petición HTTP con manejo de errores."""
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
                except:
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
        sqlfilters: Optional[str] = None,
    ) -> List[Dict]:
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
    
    async def get_thirdparty(self, thirdparty_id: int) -> Dict:
        return await self._request("GET", f"thirdparties/{thirdparty_id}")
    
    async def create_thirdparty(self, data: Dict) -> Dict:
        return await self._request("POST", "thirdparties", json=data)
    
    async def update_thirdparty(self, thirdparty_id: int, data: Dict) -> Dict:
        return await self._request("PUT", f"thirdparties/{thirdparty_id}", json=data)
    
    async def delete_thirdparty(self, thirdparty_id: int) -> Dict:
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
    ) -> List[Dict]:
        params = {"limit": limit, "offset": offset, "sortfield": sortfield, "sortorder": sortorder}
        result = await self._request("GET", "products", params=params)
        return result.get("data", []) if isinstance(result, dict) else result
    
    async def get_product(self, product_id: int) -> Dict:
        return await self._request("GET", f"products/{product_id}")
    
    async def create_product(self, data: Dict) -> Dict:
        return await self._request("POST", "products", json=data)
    
    async def update_product(self, product_id: int, data: Dict) -> Dict:
        return await self._request("PUT", f"products/{product_id}", json=data)
    
    async def delete_product(self, product_id: int) -> Dict:
        return await self._request("DELETE", f"products/{product_id}")
    
    # =========================================================================
    # EXPEDIENTES ANIMALES (Módulo personalizado)
    # =========================================================================
    
    async def list_expedientes(
        self,
        limit: int = 100,
        offset: int = 0,
        status: Optional[str] = None,
    ) -> List[Dict]:
        params = {"limit": limit, "offset": offset}
        if status:
            params["sqlfilters"] = f"commercial_status:='{status}'"
        result = await self._request("GET", "expedientes_animal", params=params)
        return result.get("data", []) if isinstance(result, dict) else result
    
    async def get_expediente(self, expediente_id: int) -> Dict:
        return await self._request("GET", f"expedientes_animal/{expediente_id}")
    
    async def create_expediente(self, data: Dict) -> Dict:
        return await self._request("POST", "expedientes_animal", json=data)
    
    async def update_expediente(self, expediente_id: int, data: Dict) -> Dict:
        return await self._request("PUT", f"expedientes_animal/{expediente_id}", json=data)
    
    async def delete_expediente(self, expediente_id: int) -> Dict:
        return await self._request("DELETE", f"expedientes_animal/{expediente_id}")
    
    # =========================================================================
    # FACTURAS
    # =========================================================================
    
    async def list_invoices(
        self,
        limit: int = 100,
        offset: int = 0,
        status: Optional[int] = None,
    ) -> List[Dict]:
        params = {"limit": limit, "offset": offset}
        if status is not None:
            params["status"] = status
        result = await self._request("GET", "invoices", params=params)
        return result.get("data", []) if isinstance(result, dict) else result
    
    async def get_invoice(self, invoice_id: int) -> Dict:
        return await self._request("GET", f"invoices/{invoice_id}")
    
    async def create_invoice(self, data: Dict) -> Dict:
        return await self._request("POST", "invoices", json=data)
    
    async def update_invoice(self, invoice_id: int, data: Dict) -> Dict:
        return await self._request("PUT", f"invoices/{invoice_id}", json=data)
    
    async def validate_invoice(self, invoice_id: int) -> Dict:
        """Validar factura (pasar de borrador a validada)."""
        return await self._request("POST", f"invoices/{invoice_id}/validate")
    
    async def cancel_invoice(self, invoice_id: int) -> Dict:
        """Anular factura."""
        return await self._request("POST", f"invoices/{invoice_id}/cancel")
    
    # =========================================================================
    # PEDIDOS
    # =========================================================================
    
    async def list_orders(
        self,
        limit: int = 100,
        offset: int = 0,
        status: Optional[int] = None,
    ) -> List[Dict]:
        params = {"limit": limit, "offset": offset}
        if status is not None:
            params["status"] = status
        result = await self._request("GET", "orders", params=params)
        return result.get("data", []) if isinstance(result, dict) else result
    
    async def get_order(self, order_id: int) -> Dict:
        return await self._request("GET", f"orders/{order_id}")
    
    async def create_order(self, data: Dict) -> Dict:
        return await self._request("POST", "orders", json=data)
    
    async def update_order(self, order_id: int, data: Dict) -> Dict:
        return await self._request("PUT", f"orders/{order_id}", json=data)
    
    # =========================================================================
    # PROPUESTAS COMERCIALES (PROPALS)
    # =========================================================================
    
    async def list_propals(
        self,
        limit: int = 100,
        offset: int = 0,
        status: Optional[int] = None,
    ) -> List[Dict]:
        params = {"limit": limit, "offset": offset}
        if status is not None:
            params["status"] = status
        result = await self._request("GET", "propals", params=params)
        return result.get("data", []) if isinstance(result, dict) else result
    
    async def get_propal(self, propal_id: int) -> Dict:
        return await self._request("GET", f"propals/{propal_id}")
    
    async def create_propal(self, data: Dict) -> Dict:
        return await self._request("POST", "propals", json=data)
    
    async def update_propal(self, propal_id: int, data: Dict) -> Dict:
        return await self._request("PUT", f"propals/{propal_id}", json=data)
    
    async def convert_propal_to_order(self, propal_id: int) -> Dict:
        """Convertir propuesta en pedido."""
        return await self._request("POST", f"propals/{propal_id}/convert_to_order")
    
    # =========================================================================
    # EXPEDICIONES/ENVIOS
    # =========================================================================
    
    async def list_shipments(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict]:
        params = {"limit": limit, "offset": offset}
        result = await self._request("GET", "shipments", params=params)
        return result.get("data", []) if isinstance(result, dict) else result
    
    async def get_shipment(self, shipment_id: int) -> Dict:
        return await self._request("GET", f"shipments/{shipment_id}")
    
    async def create_shipment(self, data: Dict) -> Dict:
        return await self._request("POST", "shipments", json=data)
    
    # =========================================================================
    # CONTACTOS
    # =========================================================================
    
    async def list_contacts(self, thirdparty_id: int) -> List[Dict]:
        result = await self._request("GET", f"thirdparties/{thirdparty_id}/contacts")
        return result.get("data", []) if isinstance(result, dict) else result
    
    async def create_contact(self, thirdparty_id: int, data: Dict) -> Dict:
        return await self._request("POST", f"thirdparties/{thirdparty_id}/contacts", json=data)
    
    # =========================================================================
    # DOCUMENTOS ADJUNTOS
    # =========================================================================
    
    async def upload_document(self, resource_type: str, resource_id: int, file_data: bytes, filename: str) -> Dict:
        """Subir documento adjunto a un recurso."""
        files = {"file": (filename, file_data)}
        return await self._request(
            "POST",
            f"{resource_type}/{resource_id}/documents",
            data={"file": (filename, file_data)},
        )
    
    async def list_documents(self, resource_type: str, resource_id: int) -> List[Dict]:
        result = await self._request("GET", f"{resource_type}/{resource_id}/documents")
        return result.get("data", []) if isinstance(result, dict) else result
    
    # =========================================================================
    # USUARIOS
    # =========================================================================
    
    async def list_users(self) -> List[Dict]:
        result = await self._request("GET", "users")
        return result.get("data", []) if isinstance(result, dict) else result
    
    async def get_user(self, user_id: int) -> Dict:
        return await self._request("GET", f"users/{user_id}")