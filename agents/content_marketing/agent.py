"""Content Marketing Agent
Genera propuestas de contenido basándose en animales disponibles y datos existentes.
"""
import structlog
from typing import Dict, List, Any, Optional
from datetime import datetime

from app.core.internal_api_client import InternalAPIClient, create_internal_api_client, InternalAPIError

logger = structlog.get_logger()


class ContentMarketingAgent:
    """
    Agente de marketing de contenido.

    Responsabilidades:
    - Generar propuestas de contenido individuales (centradas en un perro).
    - Generar contenido por raza.
    - Generar contenido por camada.
    - Generar contenido informativo genérico.
    - Utilizar datos existentes (perros, medios, salud, etc.) sin acceder directamente a Dolibarr DB.

    El agente puede usar modelos externos para contenido informativo genérico si no contiene información confidencial.
    """

    def __init__(self, config: Dict):
        self.config = config
        self.agent_id = "content_marketing"
        self.agent_name = "Content Marketing Agent"
        # Base URL for internal API (same service, includes /api/v1)
        self.api_base = config.get("INTERNAL_API_URL", "http://localhost:8000/api/v1")
        self.api_key = config.get("AGENT_API_KEY_MARKETING", "")
        self.api_client: Optional[InternalAPIClient] = None
        self.capabilities = [
            "generate_individual_content",
            "generate_breed_content",
            "generate_litter_content",
            "generate_generic_content",
        ]
        self.restrictions = [
            "no_direct_db_access",
            "privacy_scope_aware",  # Debe respetar el ámbito de privacidad (LOCAL_ONLY vs ONLINE_ALLOWED)
        ]

    async def start(self):
        """Initialize the internal API client."""
        if self.api_client is None:
            self.api_client = await create_internal_api_client(
                agent_name="marketing",
                base_url=self.api_base,
                api_key=self.api_key or None,
            )
            await self.api_client.start()
        logger.info("content_marketing_agent_started")

    async def stop(self):
        """Close the internal API client."""
        if self.api_client:
            await self.api_client.close()
            self.api_client = None

    async def generate_individual_content(self, dog_id: int) -> Dict[str, Any]:
        """Generar contenido centrado en un perro específico."""
        logger.info("generating_individual_content", dog_id=dog_id)
        
        if self.api_client is None:
            return {"success": False, "error": "ContentMarketingAgent not started. Call start() first."}
        
        # Fetch dog data
        dog = await self._get_dog(dog_id)
        if not dog:
            return {"success": False, "error": f"Dog {dog_id} not found"}
        # Fetch media for the dog
        media = await self._get_media_for_dog(dog_id)
        # Simple content generation
        name = dog.get("name", "Sin nombre")
        breed_id = dog.get("breed_id")
        breed_name = await self._get_breed_name(breed_id) if breed_id else "raza desconocida"
        sex = dog.get("sex", "")
        color = dog.get("color", "")
        title = f"{name} - {breed_name} {sex}"
        copy = (
            f"Presentamos a {name}, un hermoso cachorro de raza {breed_name} "
            f"de color {color}. Este cachorro está listo para encontrar su hogar ideal. "
            f"Para más información, contáctenos."
        )
        # Select media: use cover from media selection if available, else first photo
        suggested_media = []
        if media:
            # Assume media list includes 'file_path' and we can extract filename
            for m in media[:3]:  # up to 3
                if m.get("media_type") == "photo":
                    suggested_media.append(m.get("file_path"))
        return {
            "success": True,
            "content_type": "individual",
            "dog_id": dog_id,
            "title": title,
            "copy": copy,
            "suggested_media": suggested_media,
            "format": "post",
            "created_at": datetime.utcnow().isoformat() + "Z",
        }

    async def generate_breed_content(self, breed_id: int) -> Dict[str, Any]:
        """Generar contenido que agrupe varios perros de la misma raza."""
        logger.info("generating_breed_content", breed_id=breed_id)
        breed_name = await self._get_breed_name(breed_id) or f"raza {breed_id}"
        # Fetch dogs of this breed (limit to a few)
        dogs = await self._get_dogs_by_breed(breed_id, limit=5)
        if not dogs:
            return {"success": False, "error": f"No dogs found for breed {breed_id}"}
        names = [d.get("name", "Sin nombre") for d in dogs]
        title = f"{breed_name} - Conoce a nuestros cachorros"
        copy = (
            f"Descubre la maravillosa raza {breed_name}. "
            f"Actualmente tenemos disponibles: {', '.join(names)}. "
            f"Cada uno de ellos viene con pedigree, vacunas al día y mucho amor para dar."
        )
        # Suggest media: collect photos from first few dogs
        suggested_media = []
        for dog in dogs[:2]:
            media = await self._get_media_for_dog(dog.get("id"))
            for m in media:
                if m.get("media_type") == "photo" and len(suggested_media) < 3:
                    suggested_media.append(m.get("file_path"))
        return {
            "success": True,
            "content_type": "breed",
            "breed_id": breed_id,
            "title": title,
            "copy": copy,
            "suggested_media": suggested_media,
            "format": "post",
            "created_at": datetime.utcnow().isoformat() + "Z",
        }

    async def generate_litter_content(self, litter_id: int) -> Dict[str, Any]:
        """Generar contenido sobre hermanos de la misma camada."""
        logger.info("generating_litter_content", litter_id=litter_id)
        # Fetch litter info
        litter = await self._get_litter(litter_id)
        if not litter:
            return {"success": False, "error": f"Litter {litter_id} not found"}
        # Fetch dogs in this litter
        dogs = await self._get_dogs_by_litter(litter_id, limit=10)
        if not dogs:
            return {"success": False, "error": f"No dogs found for litter {litter_id}"}
        # Simple info
        breed_name = await self._get_breed_name(litter.get("breed_id")) if litter.get("breed_id") else "raza desconocida"
        title = f"Camada {litter.get('code', litter_id)} - Hermanos de {breed_name}"
        copy = (
            f"Presentamos la camada {litter.get('code', litter_id)} de raza {breed_name}. "
            f"Estos {len(dogs)} hermanos comparten rasgos de salud, temperamento y belleza. "
            f"Cada uno está listo para unirse a una familia amorosa."
        )
        # Suggest media: one photo per dog (up to 4)
        suggested_media = []
        for dog in dogs[:4]:
            media = await self._get_media_for_dog(dog.get("id"))
            for m in media:
                if m.get("media_type") == "photo" and len(suggested_media) < 4:
                    suggested_media.append(m.get("file_path"))
                    break
        return {
            "success": True,
            "content_type": "litter",
            "litter_id": litter_id,
            "title": title,
            "copy": copy,
            "suggested_media": suggested_media,
            "format": "post",
            "created_at": datetime.utcnow().isoformat() + "Z",
        }

    async def generate_generic_content(self, topic: str) -> Dict[str, Any]:
        """Generar contenido informativo genérico (cuidados, transporte, bienestar, etc.)."""
        # Este tipo de contenido puede usar modelos externos si no contiene información confidencial.
        logger.info("generating_generic_content", topic=topic)
        # For now, we just return a simple placeholder. In the future, we could call an external LLM.
        title = f"{topic.capitalize()} - Guía esencial"
        copy = (
            f"Información útil sobre {topic}. "
            f"En esta guía encontrarás consejos prácticos para asegurar el bienestar de tu cachorro. "
            f"Recuerda siempre consultar con un veterinario profesional."
        )
        return {
            "success": True,
            "content_type": "generic",
            "topic": topic,
            "title": title,
            "copy": copy,
            "format": "article",
            "created_at": datetime.utcnow().isoformat() + "Z",
        }

    # Helper methods to call internal API
    async def _get_dog(self, dog_id: int) -> Optional[Dict]:
        try:
            return await self.api_client.get(f"/dogs/{dog_id}")
        except InternalAPIError as e:
            logger.error("failed_to_get_dog", dog_id=dog_id, error=e.message)
        except Exception as e:
            logger.error("failed_to_get_dog", dog_id=dog_id, error=str(e))
        return None

    async def _get_media_for_dog(self, dog_id: int) -> List[Dict]:
        try:
            resp = await self.api_client.get(f"/dogs/{dog_id}/media")
            data = resp
            # Assuming the API returns a list under 'data' key or direct list
            if isinstance(data, dict) and "data" in data:
                return data["data"]
            if isinstance(data, list):
                return data
        except InternalAPIError as e:
            logger.error("failed_to_get_media", dog_id=dog_id, error=e.message)
        except Exception as e:
            logger.error("failed_to_get_media", dog_id=dog_id, error=str(e))
        return []

    async def _get_breed_name(self, breed_id: int) -> Optional[str]:
        try:
            breed = await self.api_client.get(f"/breeds/{breed_id}")
            return breed.get("name")
        except InternalAPIError as e:
            logger.error("failed_to_get_breed", breed_id=breed_id, error=e.message)
        except Exception as e:
            logger.error("failed_to_get_breed", breed_id=breed_id, error=str(e))
        return None

    async def _get_dogs_by_breed(self, breed_id: int, limit: int = 5) -> List[Dict]:
        try:
            resp = await self.api_client.get("/dogs/", params={"breed_id": breed_id, "limit": limit})
            data = resp
            if isinstance(data, dict) and "data" in data:
                return data["data"]
            if isinstance(data, list):
                return data
        except InternalAPIError as e:
            logger.error("failed_to_get_dogs_by_breed", breed_id=breed_id, error=e.message)
        except Exception as e:
            logger.error("failed_to_get_dogs_by_breed", breed_id=breed_id, error=str(e))
        return []

    async def _get_litter(self, litter_id: int) -> Optional[Dict]:
        try:
            return await self.api_client.get(f"/litters/{litter_id}")
        except InternalAPIError as e:
            logger.error("failed_to_get_litter", litter_id=litter_id, error=e.message)
        except Exception as e:
            logger.error("failed_to_get_litter", litter_id=litter_id, error=str(e))
        return None

    async def _get_dogs_by_litter(self, litter_id: int, limit: int = 10) -> List[Dict]:
        try:
            resp = await self.api_client.get("/dogs/", params={"litter_id": litter_id, "limit": limit})
            data = resp
            if isinstance(data, dict) and "data" in data:
                return data["data"]
            if isinstance(data, list):
                return data
        except InternalAPIError as e:
            logger.error("failed_to_get_dogs_by_litter", litter_id=litter_id, error=e.message)
        except Exception as e:
            logger.error("failed_to_get_dogs_by_litter", litter_id=litter_id, error=str(e))
        return []


# Función de ayuda para crear el agente desde configuración
def create_content_marketing_agent(config: Dict) -> ContentMarketingAgent:
    return ContentMarketingAgent(config)