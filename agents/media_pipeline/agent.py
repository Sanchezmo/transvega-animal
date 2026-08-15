"""
Media Pipeline Agent - Orchestrates the complete media workflow for dogs.
Coordinates: ingestion -> storage -> selection/analysis -> generation -> publishing prep
"""

import os
from datetime import datetime
from typing import Any

import structlog

from agents.media_generation.agent import create_media_generation_agent
from agents.media_selection.agent import MediaSelectionAgent
from app.services.media_storage import (
    MediaAsset,
    get_assets_for_publishing,
    list_dog_assets,
    save_uploaded_file,
)

logger = structlog.get_logger()


class MediaPipelineAgent:
    """
    Agente de pipeline de media - Orquesta el flujo completo de media para perros.

    Flujo:
    1. INGEST: Recibir archivo -> validar -> guardar en storage (originals/)
    2. ANALYZE: MediaSelectionAgent analiza (nitidez, exposición, encuadre, visibilidad perro)
    3. SELECT: Recomendar portada, listado, redes sociales, marcar descartables
    4. PROCESS (opcional): Generar versiones procesadas (processed/, social/, listing/)
    5. PUBLISH PREP: Preparar assets para Publishing Agent

    Privacy: Media original es LOCAL_ONLY por defecto.

    Estructura de directorios unificada:
    /data/dogs/{dog_internal_id}/
        originals/
        listing/
            cover.jpg
            image_01.jpg
            image_02.jpg
            ...
        social/
            square.jpg
            story.jpg
            facebook.jpg
        processed/
    """

    def __init__(self, config: dict):
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

    async def start(self):
        """Initialize sub-agents."""
        await self.generation_agent.start()
        logger.info("media_pipeline_agent_started")

    async def stop(self):
        """Close sub-agents."""
        await self.generation_agent.stop()
        logger.info("media_pipeline_agent_stopped")

    async def ingest_media(
        self,
        file_content: bytes,
        filename: str,
        dog_internal_id: str,
        variant: str = "original",
        uploaded_by: int = 1,
        metadata: dict | None = None,
    ) -> dict[str, Any]:
        """
        Paso 1: Ingestar media - validar, hashear, guardar en storage.
        Retorna MediaAsset.
        """
        # Validar variante
        valid_variants = [
            "original",
            "cover",
            "listing_01",
            "listing_02",
            "listing_03",
            "listing_04",
            "listing_05",
            "listing_06",
            "listing_07",
            "listing_08",
            "listing_09",
            "listing_10",
            "social_square",
            "social_story",
            "social_facebook",
            "processed",
        ]
        if variant not in valid_variants:
            return {"success": False, "error": f"Invalid variant: {variant}. Valid: {valid_variants}"}

        # Validar tipo MIME
        ext = os.path.splitext(filename)[1].lower()
        mime_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".mp4": "video/mp4",
        }
        mime_type = mime_map.get(ext, "application/octet-stream")

        if not (mime_type.startswith("image/") or mime_type.startswith("video/")):
            return {"success": False, "error": f"Unsupported file type: {mime_type}"}

        # Guardar en storage
        try:
            asset = save_uploaded_file(
                file_content=file_content,
                filename=filename,
                dog_internal_id=dog_internal_id,
                variant=variant,
                uploaded_by=uploaded_by,
            )
        except Exception as e:
            logger.error("media_ingest_failed", error=str(e), dog_internal_id=dog_internal_id)
            return {"success": False, "error": str(e)}

        # Añadir metadata extra
        asset_dict = asset.to_dict()
        asset_dict.update(
            {
                "dog_internal_id": dog_internal_id,
                "original_filename": filename,
                "ingested_at": datetime.utcnow().isoformat(),
                "metadata": metadata or {},
            }
        )

        logger.info("media_ingested", dog_internal_id=dog_internal_id, asset_id=asset.id, variant=variant)

        return {"success": True, "media_asset": asset_dict}

    async def ingest_and_analyze(
        self,
        file_content: bytes,
        filename: str,
        dog_internal_id: str,
        variant: str = "original",
        uploaded_by: int = 1,
    ) -> dict[str, Any]:
        """
        Ingestar y analizar en un paso (para flujo Telegram/webhook).
        """
        # Ingest
        ingest_result = await self.ingest_media(
            file_content=file_content,
            filename=filename,
            dog_internal_id=dog_internal_id,
            variant=variant,
            uploaded_by=uploaded_by,
        )
        if not ingest_result["success"]:
            return ingest_result

        asset_dict = ingest_result["media_asset"]
        file_path = asset_dict["path"]

        # Analizar si es foto
        if asset_dict["type"] == "photo" and self.auto_analyze:
            analysis = await self.selection_agent.analyze_image(file_path)
            asset_dict["analysis"] = analysis

            # Auto-seleccionar si hay otros media del perro
            if self.auto_select:
                # Obtener todos los media del perro para selección
                pass  # Se haría consultando la API/DB

        return {"success": True, "media_asset": asset_dict}

    async def select_best_for_publishing(
        self, dog_internal_id: str, media_assets: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """
        Paso 3: Seleccionar mejores media para publishing.
        media_items: lista con file_path, variant, type, etc.
        """
        return await self.selection_agent.select_media(dog_internal_id, media_assets)

    async def generate_social_variants(
        self, dog_internal_id: str, cover_image_path: str, breed: str, dog_name: str, privacy_scope: str = "LOCAL_ONLY"
    ) -> dict[str, Any]:
        """
        Paso 4: Generar variantes para redes sociales usando MediaGenerationAgent.
        - Post cuadrado (Instagram) 1080x1080 -> social/square.jpg
        - Story 1080x1920 -> social/story.jpg
        - Listing 1200x800 -> listing/cover.jpg (also used as listing image)
        """
        results = {}

        prompts = {
            "social_square": (
                f"Professional photo of {dog_name}, a {breed} dog, clean background, high quality, square format"
            ),
            "social_story": (f"Vertical photo of {dog_name}, {breed} puppy, lifestyle shot, story format 9:16"),
            "listing_cover": (
                f"Clean product photo of {dog_name}, {breed} dog for sale listing, professional lighting, 3:2 ratio"
            ),
        }

        for variant, prompt in prompts.items():
            # Determine output path based on variant
            if variant.startswith("social_"):
                output_path = f"/data/dogs/{dog_internal_id}/social/{variant.replace('social_', '')}.jpg"
            elif variant == "listing_cover":
                output_path = f"/data/dogs/{dog_internal_id}/listing/cover.jpg"
            else:
                output_path = f"/data/dogs/{dog_internal_id}/listing/{variant}.jpg"

            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            result = await self.generation_agent.generate_image(
                prompt=prompt,
                output_path=output_path,
                privacy_scope=privacy_scope,
            )
            results[variant] = result

            if result["success"]:
                # The file is already saved by the generation agent to the correct path
                # We just need to register it in storage with the correct variant
                # Note: save_uploaded_file will overwrite with the same filename
                with open(result["output_path"], "rb") as f:
                    file_content = f.read()
                save_uploaded_file(
                    file_content=file_content,
                    filename=os.path.basename(result["output_path"]),
                    dog_internal_id=dog_internal_id,
                    variant=variant,
                    uploaded_by=1,
                )

        return {"success": True, "variants": results}

    async def prepare_for_publishing(self, dog_internal_id: str, platforms: list[str] | None = None) -> dict[str, Any]:
        """
        Paso 5: Preparar assets para Publishing Agent.
        Retorna dict con archivos listos por plataforma usando la estructura unificada.
        """
        if platforms is None:
            platforms = ["milanuncios", "meta"]

        assets = {}

        for platform in platforms:
            platform_assets = get_assets_for_publishing(dog_internal_id, platform)
            assets[platform] = platform_assets

        return {"success": True, "assets": assets, "dog_internal_id": dog_internal_id}

    async def get_dog_media_summary(self, dog_internal_id: str) -> dict[str, Any]:
        """
        Obtener resumen de todo el media de un perro para dashboard.
        """
        assets = list_dog_assets(dog_internal_id)

        summary = {
            "dog_internal_id": dog_internal_id,
            "by_variant": {},
            "total_files": 0,
            "total_size_bytes": 0,
        }

        for asset in assets:
            variant = asset.variant
            if variant not in summary["by_variant"]:
                summary["by_variant"][variant] = {
                    "count": 0,
                    "files": [],
                    "size_bytes": 0,
                }

            summary["by_variant"][variant]["count"] += 1
            summary["by_variant"][variant]["files"].append(
                {
                    "id": asset.id,
                    "path": asset.path,
                    "type": asset.type,
                    "mime_type": asset.mime_type,
                    "width": asset.width,
                    "height": asset.height,
                }
            )

            # Calculate file size
            try:
                file_size = os.path.getsize(asset.path)
                summary["by_variant"][variant]["size_bytes"] += file_size
                summary["total_size_bytes"] += file_size
            except Exception:
                pass  # nosec B110 - Intentional: ignore files that can't be sized

            summary["total_files"] += 1

        return {"success": True, "summary": summary}

    async def get_assets_by_variant(self, dog_internal_id: str, variant: str) -> list[MediaAsset]:
        """Get all assets for a specific variant."""
        assets = list_dog_assets(dog_internal_id)
        return [a for a in assets if a.variant == variant]

    async def close(self):
        await self.generation_agent.close()


def create_media_pipeline_agent(config: dict) -> MediaPipelineAgent:
    """Factory function."""
    return MediaPipelineAgent(config)
