"""Listing Agent
Genera un anuncio estructurado a partir de la ficha del perro.
"""
import structlog
from typing import Dict, List, Any, Optional
from datetime import datetime

logger = structlog.get_logger()


class ListingAgent:
    """
    Agente de generación de anuncios (listings).

    Responsabilidades:
    - Generar un anuncio estructurado para plataformas como Milanuncios.
    - Nunca publicar automáticamente; solo crear borradores (status: draft).
    - Utilizar datos existentes (perro, medios, etc.) sin acceder directamente a Dolibarr DB.
    - El anuncio debe incluir título, descripción, precio, ubicación, raza, imágenes, etc.
    """

    def __init__(self, config: Dict):
        self.config = config
        self.agent_id = "listing"
        self.agent_name = "Listing Agent"
        # Base URL for internal API (same service)
        self.api_base = config.get("INTERNAL_API_URL", "http://localhost:8000")
        self.client = None  # Will be initialized lazily
        self.capabilities = [
            "generate_listing_draft",
        ]
        self.restrictions = [
            "no_direct_db_access",
            "privacy_scope_aware",  # Debe respetar el ámbito de privacidad (LOCAL_ONLY vs ONLINE_ALLOWED)
        ]

    async def _get_client(self):
        if self.client is None:
            import httpx
            self.client = httpx.AsyncClient(base_url=self.api_base, timeout=30.0)
        return self.client

    async def __aenter__(self):
        await self._get_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()

    async def generate_listing_draft(self, dog_id: int) -> Dict[str, Any]:
        """Generar un borrador de anuncio para un perro."""
        logger.info("generating_listing_draft", dog_id=dog_id)
        client = await self._get_client()
        # Fetch dog data
        try:
            resp = await client.get(f"/dogs/{dog_id}")
            if resp.status_code != 200:
                return {"success": False, "error": f"Dog {dog_id} not found"}
            dog = resp.json()
        except Exception as e:
            logger.error("failed_to_get_dog", dog_id=dog_id, error=str(e))
            return {"success": False, "error": str(e)}

        # Fetch media for the dog
        try:
            media_resp = await client.get(f"/dogs/{dog_id}/media")
            if media_resp.status_code == 200:
                media_data = media_resp.json()
                # Assume media_data is a list or has 'data' key
                if isinstance(media_data, dict) and "data" in media_data:
                    media_list = media_data["data"]
                elif isinstance(media_data, list):
                    media_list = media_data
                else:
                    media_list = []
            else:
                media_list = []
        except Exception as e:
            logger.error("failed_to_get_media", dog_id=dog_id, error=str(e))
            media_list = []

        # Select images: only photos with purpose original or social/listing? We'll take all photos.
        images = []
        for m in media_list:
            if m.get("media_type") == "photo":
                # Use file_path; assume it's accessible via URL base
                file_path = m.get("file_path")
                if file_path:
                    # Convert to URL if needed; for now just keep path
                    images.append(file_path)

        # If no images, we cannot create a draft
        if not images:
            return {"success": False, "error": "No images available for listing"}

        # Build listing draft
        title = f"{dog.get('name', 'Sin nombre')} - {await self._get_breed_name(client, dog.get('breed_id'))}"
        description = (
            f"Precioso cachorro de raza {await self._get_breed_name(client, dog.get('breed_id'))}. "
            f"Fecha de nacimiento: {dog.get('birth_date', 'N/A')}. "
            f"Sexo: {dog.get('sex', 'N/A').upper()}. "
            f"Color: {dog.get('color', 'N/A')}. "
            f"Microchip: {dog.get('microchip', 'N/A')}. "
            f"Vacunas: {dog.get('vet_status', 'N/A')}. "
            f"Precio: {dog.get('sale_price', dog.get('purchase_price', 0))} €."
        )
        # Price: prefer sale_price, else purchase_price, else 0
        price = dog.get("sale_price") or dog.get("purchase_price") or 0
        # Location: from dog or config? We'll use a placeholder
        location = dog.get("location") or self.config.get("DEFAULT_LOCATION", "España")

        draft = {
            "success": True,
            "listing": {
                "dog_id": dog_id,
                "platform": "milanuncios",
                "title": title,
                "description": description,
                "price": price,
                "location": location,
                "breed": await self._get_breed_name(client, dog.get('breed_id')),
                "images": images,
                "status": "draft",
                "created_at": datetime.utcnow().isoformat() + "Z",
            }
        }
        return draft

    async def _get_breed_name(self, client, breed_id: Optional[int]) -> Optional[str]:
        if not breed_id:
            return None
        try:
            resp = await client.get(f"/breeds/{breed_id}")
            if resp.status_code == 200:
                return resp.json().get("name")
        except Exception:
            pass
        return None


# Función de ayuda para crear el agente desde configuración
def create_listing_agent(config: Dict) -> ListingAgent:
    return ListingAgent(config)