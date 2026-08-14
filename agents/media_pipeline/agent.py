"""
Media Pipeline Agent - Orchestrates the complete media workflow for dogs.
Coordinates: ingestion -> storage -> selection/analysis -> generation -> publishing prep
"""
import os
import hashlib
import structlog
from typing import Dict, List, Any, Optional
from datetime import datetime

from app.services.media_storage import save_uploaded_file, get_media_root, ensure_media_dirs
from app.agents.media_selection.agent import MediaSelectionAgent
from app.agents.media_generation.agent import MediaGenerationAgent, create_media_generation_agent
from app.schemas import DogMediaCreate

logger = structlog.get_logger()


class MediaPipelineAgent:
    """
    Agente de pipeline de media - Orquesta el flujo completo de media para perros.
    
    Flujo:
    1. INGEST: Recibir archivo -> validar -> guardar en storage (original/)
    2. ANALYZE: MediaSelectionAgent analiza (nitidez, exposición, encuadre, visibilidad perro)
    3. SELECT: Recomendar portada, listado, redes sociales, marcar descartables
    4. PROCESS (opcional): Generar versiones procesadas (processed/, social/, listing/)
    5. PUBLISH PREP: Preparar assets para Publishing Agent
    
    Privacy: Media original es LOCAL_ONLY por defecto.
    """

    def __init__(self, config: Dict):
        self.config = config
        self.agent_id = "media_pipeline"
        self.agent_name = "Media Pipeline Agent"
        
        # Sub-agents
        self.selection_agent = MediaSelectionAgent(config)
        self.generation_agent = create_media_generation_agent(config)
        
        self.capabilities = [
            "ingest_media",
            "analyze_media",
            "select_best_media",
            "generate_variants",
            "get_media_for_publishing",
            "cleanup_disposable",
        ]
        self.restrictions = [
            "original_media_local_only",
            "processed_can_be_cloud",
            "privacy_scope_aware",
        ]
        
        # Config
        self.auto_analyze = config.get("MEDIA_PIPELINE_AUTO_ANALYZE", True)
        self.auto_select = config.get("MEDIA_PIPELINE_AUTO_SELECT", True)
        self.auto_generate_variants = config.get("MEDIA_PIPELINE_AUTO_GENERATE_VARIANTS", False)

    async def ingest_media(
        self,
        file_content: bytes,
        filename: str,
        dog_internal_id: str,
        purpose: str = "original",
        uploaded_by: int = 1,
        metadata: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Paso 1: Ingestar media - validar, hashear, guardar en storage.
        Retorna metadata para DogMediaCreate.
        """
        # Validar propósito
        if purpose not in ["original", "processed", "social", "listing"]:
            return {"success": False, "error": f"Invalid purpose: {purpose}"}
        
        # Validar tipo MIME
        ext = os.path.splitext(filename)[1].lower()
        mime_map = {
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".png": "image/png", ".mp4": "video/mp4",
        }
        mime_type = mime_map.get(ext, "application/octet-stream")
        
        if not (mime_type.startswith("image/") or mime_type.startswith("video/")):
            return {"success": False, "error": f"Unsupported file type: {mime_type}"}
        
        # Guardar en storage
        try:
            media_meta = save_uploaded_file(
                file_content=file_content,
                filename=filename,
                dog_internal_id=dog_internal_id,
                purpose=purpose,
                uploaded_by=uploaded_by,
            )
        except Exception as e:
            logger.error("media_ingest_failed", error=str(e), dog_internal_id=dog_internal_id)
            return {"success": False, "error": str(e)}
        
        # Añadir metadata extra
        media_meta.update({
            "dog_internal_id": dog_internal_id,
            "original_filename": filename,
            "ingested_at": datetime.utcnow().isoformat(),
            "metadata": metadata or {},
        })
        
        logger.info("media_ingested", 
                    dog_internal_id=dog_internal_id, 
                    file_hash=media_meta["file_hash"],
                    purpose=purpose)
        
        return {"success": True, "media_metadata": media_meta}

    async def ingest_and_analyze(
        self,
        file_content: bytes,
        filename: str,
        dog_internal_id: str,
        purpose: str = "original",
        uploaded_by: int = 1,
    ) -> Dict[str, Any]:
        """
        Ingestar y analizar en un paso (para flujo Telegram/webhook).
        """
        # Ingest
        ingest_result = await self.ingest_media(
            file_content=file_content,
            filename=filename,
            dog_internal_id=dog_internal_id,
            purpose=purpose,
            uploaded_by=uploaded_by,
        )
        if not ingest_result["success"]:
            return ingest_result
        
        media_meta = ingest_result["media_metadata"]
        file_path = media_meta["file_path"]
        
        # Analizar si es foto
        if media_meta["media_type"] == "photo" and self.auto_analyze:
            analysis = await self.selection_agent.analyze_image(file_path)
            media_meta["analysis"] = analysis
            
            # Auto-seleccionar si hay otros media del perro
            if self.auto_select:
                # Obtener todos los media del perro para selección
                pass  # Se haría consultando la API/DB
        
        return {"success": True, "media_metadata": media_meta}

    async def select_best_for_publishing(
        self,
        dog_internal_id: str,
        media_items: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Paso 3: Seleccionar mejores media para publishing.
        media_items: lista con file_path, purpose, media_type, etc.
        """
        return await self.selection_agent.select_media(dog_internal_id, media_items)

    async def generate_social_variants(
        self,
        dog_internal_id: str,
        cover_image_path: str,
        breed: str,
        dog_name: str,
        privacy_scope: str = "LOCAL_ONLY"
    ) -> Dict[str, Any]:
        """
        Paso 4: Generar variantes para redes sociales usando MediaGenerationAgent.
        - Post cuadrado (Instagram) 1080x1080
        - Story 1080x1920
        - Listing 1200x800
        """
        results = {}
        
        prompts = {
            "social_square": f"Professional photo of {dog_name}, a {breed} dog, clean background, high quality, square format",
            "social_story": f"Vertical photo of {dog_name}, {breed} puppy, lifestyle shot, story format 9:16",
            "listing": f"Clean product photo of {dog_name}, {breed} dog for sale listing, professional lighting, 3:2 ratio",
        }
        
        for variant, prompt in prompts.items():
            output_path = f"/data/dogs/{dog_internal_id}/{variant}/{variant}.jpg"
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            result = await self.generation_agent.generate_image(
                prompt=prompt,
                output_path=output_path,
                privacy_scope=privacy_scope,
            )
            results[variant] = result
            
            if result["success"]:
                # Guardar metadata en storage
                save_uploaded_file(
                    file_content=open(result["output_path"], "rb").read(),
                    filename=f"{variant}.jpg",
                    dog_internal_id=dog_internal_id,
                    purpose="social",
                    uploaded_by=1,
                )
        
        return {"success": True, "variants": results}

    async def prepare_for_publishing(
        self,
        dog_internal_id: str,
        platforms: List[str] = ["milanuncios", "meta"]
    ) -> Dict[str, Any]:
        """
        Paso 5: Preparar assets para Publishing Agent.
        Retorna dict con archivos listos por plataforma.
        """
        media_root = get_media_root() / dog_internal_id
        
        assets = {
            "milanuncios": {},
            "meta": {},
        }
        
        # Milanuncios: necesita portada + hasta 20 fotos
        if "milanuncios" in platforms:
            cover = media_root / "social" / "cover.jpg"
            listing = media_root / "listing"
            
            assets["milanuncios"] = {
                "cover": str(cover) if cover.exists() else None,
                "photos": [str(f) for f in listing.glob("*.jpg")] if listing.exists() else [],
                "max_photos": 20,
            }
        
        # Meta (Instagram/Facebook): post + story
        if "meta" in platforms:
            assets["meta"] = {
                "post_image": str(media_root / "social" / "social_square.jpg") if (media_root / "social" / "social_square.jpg").exists() else None,
                "story_image": str(media_root / "social" / "social_story.jpg") if (media_root / "social" / "social_story.jpg").exists() else None,
            }
        
        return {"success": True, "assets": assets, "dog_internal_id": dog_internal_id}

    async def get_dog_media_summary(self, dog_internal_id: str) -> Dict[str, Any]:
        """
        Obtener resumen de todo el media de un perro para dashboard.
        """
        media_root = get_media_root() / dog_internal_id
        
        summary = {
            "dog_internal_id": dog_internal_id,
            "by_purpose": {},
            "total_files": 0,
            "total_size_bytes": 0,
        }
        
        for purpose in ["original", "processed", "social", "listing"]:
            purpose_dir = media_root / purpose
            if purpose_dir.exists():
                files = list(purpose_dir.glob("*"))
                summary["by_purpose"][purpose] = {
                    "count": len(files),
                    "files": [f.name for f in files],
                    "size_bytes": sum(f.stat().st_size for f in files if f.is_file()),
                }
                summary["total_files"] += len(files)
                summary["total_size_bytes"] += summary["by_purpose"][purpose]["size_bytes"]
        
        return {"success": True, "summary": summary}

    async def close(self):
        await self.generation_agent.close()


def create_media_pipeline_agent(config: Dict) -> MediaPipelineAgent:
    """Factory function."""
    return MediaPipelineAgent(config)