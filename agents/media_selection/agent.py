"""Media Selection Agent
Analiza fotografías y vídeos para proporcionar métricas y recomendaciones de uso.
"""

import hashlib
import os
from typing import Any

import structlog
from PIL import Image, ImageFile, ImageStat

# Allow loading of truncated images
ImageFile.LOAD_TRUNCATED_IMAGES = True

logger = structlog.get_logger()


class MediaSelectionAgent:
    """
    Agente de selección de media.

    Responsabilidades:
    - Analizar imágenes para métricas de nitidez, exposición, encuadre, visibilidad del perro.
    - Detectar posibles duplicados.
    - Recomendar qué media usar como portada, para listados, para redes sociales.
    - Marcar media descartable si no cumple umbrales mínimos.

    El análisis se realiza con un modelo local cuando está disponible;
    si no, se usan heurísticas básicas y se devuelve un estado de proveedor no disponible.
    """

    def __init__(self, config: dict):
        self.config = config
        self.agent_id = "media_selection"
        self.agent_name = "Media Selection Agent"
        # Proveedor local (stub). En el futuro se inyectará una implementación real.
        self.provider = self._get_local_provider(config)
        self.capabilities = [
            "analyze_image",
            "select_media",
            "detect_duplicates",
        ]
        self.restrictions = [
            "provider_optional",  # El agente funciona incluso si el proveedor no está disponible
        ]
        # Umbrales para considerar media como descartable
        self.thresholds = config.get(
            "MEDIA_SELECTION_THRESHOLDS",
            {
                "sharpness": 0.3,
                "exposure": 0.3,
                "dog_visibility": 0.3,
            },
        )

    def _get_local_provider(self, config: dict):
        """Obtener el proveedor local de análisis de medios."""
        provider_type = config.get("MEDIA_ANALYSIS_PROVIDER", "stub")
        if provider_type == "stub":
            return StubAnalysisProvider()
        # En el futuro se podrían cargar proveedores reales (por ejemplo, que llamen a un modelo en DGX Spark)
        # Por ahora, solo stub.
        logger.warning("Unknown media analysis provider, using stub", provider=provider_type)
        return StubAnalysisProvider()

    async def analyze_image(self, image_path: str) -> dict[str, Any]:
        """Analizar una imagen y devolver métricas."""
        if not os.path.exists(image_path):
            return {"success": False, "error": f"Image not found: {image_path}"}

        try:
            # Delegar al proveedor (puede ser stub o real)
            result = await self.provider.analyze_image(image_path)
            return {"success": True, "analysis": result}
        except Exception as e:
            logger.error("image_analysis_failed", image_path=image_path, error=str(e))
            return {"success": False, "error": str(e)}

    async def select_media(self, dog_internal_id: str, media_items: list[dict]) -> dict[str, Any]:
        """
        Dada una lista de media (cada ítem con al menos 'file_path', 'purpose', etc.),
        devolver selecciones y puntuaciones.

        Espera que cada ítem tenga:
        - file_path: ruta absoluta al archivo original
        - purpose: original, processed, social, listing (o None)
        - media_type: photo o video

        Devuelve:
        {
            "cover": "img_xxx.jpg",
            "listing": ["img_xxx.jpg", "img_yyy.jpg"],
            "social": ["img_xxx.jpg", "img_zzz.jpg"],
            "scores": { "img_xxx.jpg": { "sharpness": 0.8, ... } }
        }
        """
        if not media_items:
            return {"success": False, "error": "No media items provided"}

        # Analizar cada medio (solo fotos por ahora)
        analyzed = []
        for item in media_items:
            if item.get("media_type") != "photo":
                # Por ahora ignoramos videos para selección; se pueden añadir después
                continue
            file_path = item.get("file_path")
            if not file_path or not os.path.exists(file_path):
                continue
            analysis = await self.analyze_image(file_path)
            if not analysis.get("success"):
                # Si falla el análisis, asignamos scores bajos
                scores = {"sharpness": 0.0, "exposure": 0.0, "framing": 0.0, "dog_visibility": 0.0}
            else:
                scores = analysis["analysis"]
            analyzed.append(
                {
                    "file_path": file_path,
                    "filename": os.path.basename(file_path),
                    "scores": scores,
                    "purpose": item.get("purpose"),
                    "media_type": "photo",
                }
            )

        if not analyzed:
            return {"success": False, "error": "No photos to analyze"}

        # Simple selection logic: higher sharpness + dog_visibility better
        def score_item(it):
            s = it["scores"]
            return (
                s.get("sharpness", 0) * 0.4
                + s.get("dog_visibility", 0) * 0.4
                + s.get("exposure", 0) * 0.1
                + s.get("framing", 0) * 0.1
            )

        sorted_items = sorted(analyzed, key=score_item, reverse=True)

        # Choose top 1 for cover
        cover = sorted_items[0]["filename"] if sorted_items else None
        # Choose top 3 for listing (avoid duplicate)
        listing = [it["filename"] for it in sorted_items[:3]]
        # Choose top 2 for social (could be same as listing)
        social = [it["filename"] for it in sorted_items[:2]]

        # Build scores dict for output
        scores_dict = {it["filename"]: it["scores"] for it in analyzed}

        # Determine disposable media based on thresholds
        disposable = []
        for it in analyzed:
            s = it["scores"]
            if (
                s.get("sharpness", 0) < self.thresholds.get("sharpness", 0)
                or s.get("exposure", 0) < self.thresholds.get("exposure", 0)
                or s.get("dog_visibility", 0) < self.thresholds.get("dog_visibility", 0)
            ):
                disposable.append(it["filename"])

        return {
            "success": True,
            "cover": cover,
            "listing": listing,
            "social": social,
            "scores": scores_dict,
            "disposable": disposable,
            "message": "Media selection completed",
        }

    async def detect_duplicates(self, media_items: list[dict]) -> dict[str, Any]:
        """Detectar posibles duplicados basado en hash de archivo."""
        hashes = {}
        duplicates = []
        for item in media_items:
            file_path = item.get("file_path")
            if not file_path or not os.path.exists(file_path):
                continue
            try:
                with open(file_path, "rb") as f:
                    file_hash = hashlib.sha256(f.read()).hexdigest()
            except Exception as e:
                logger.error("hash_failed", file_path=file_path, error=str(e))
                continue
            if file_hash in hashes:
                duplicates.append({"file1": hashes[file_hash], "file2": file_path, "hash": file_hash})
            else:
                hashes[file_hash] = file_path

        return {"success": True, "duplicates": duplicates, "count": len(duplicates)}


class StubAnalysisProvider:
    """
    Proveedor stub que devuelve métricas falsas basadas en propiedades simples de la imagen.
    En un futuro se reemplazará por un proveedor que llame a un modelo local (DGX Spark).
    """

    async def analyze_image(self, image_path: str) -> dict[str, float]:
        """Devuelve métricas simuladas."""
        try:
            with Image.open(image_path) as img:
                img = img.convert("L")  # grayscale
                stat = ImageStat.Stat(img)
                # Sharpeness approximation: variance of pixel values
                sharpness = stat.stddev[0] / 255.0  # normalize 0-1
                # Exposure: mean brightness
                exposure = stat.mean[0] / 255.0
                # Framing: placeholder (assume centered)
                framing = 0.8
                # Dog visibility: placeholder (assume dog present)
                dog_visibility = 0.7
                # Add some deterministic variation based on filename to make differences
                filename_hash = hashlib.sha256(os.path.basename(image_path).encode()).hexdigest()
                seed = int(filename_hash[:8], 16) / 0xFFFFFFFF
                sharpness = max(0.0, min(1.0, sharpness + (seed - 0.5) * 0.2))
                exposure = max(0.0, min(1.0, exposure + (seed - 0.5) * 0.2))
                return {
                    "sharpness": round(sharpness, 3),
                    "exposure": round(exposure, 3),
                    "framing": round(framing, 3),
                    "dog_visibility": round(dog_visibility, 3),
                }
        except Exception as e:
            # If cannot open image, return low scores
            logger.warning("Stub analysis failed, returning low scores", image_path=image_path, error=str(e))
            return {
                "sharpness": 0.0,
                "exposure": 0.0,
                "framing": 0.0,
                "dog_visibility": 0.0,
            }


# Proveedor de generación local (placeholder para futuro)
class LocalImageProvider:
    """Proveedor local de generación/analisis de imagen (para conectar a DGX Spark)."""

    async def analyze_image(self, image_path: str) -> dict[str, float]:
        raise NotImplementedError("LocalImageProvider not implemented")


class LocalVideoProvider:
    """Proveedor local de vídeo."""

    async def analyze_video(self, video_path: str) -> dict[str, float]:
        raise NotImplementedError("LocalVideoProvider not implemented")


class LocalTTSProvider:
    """Proveedor local de texto a voz."""

    async def synthesize_speech(self, text: str, output_path: str) -> bool:
        raise NotImplementedError("LocalTTSProvider not implemented")


# Función de fábrica para obtener el proveedor de generación (según config)
def get_generation_provider(provider_type: str = "stub"):
    if provider_type == "local_image":
        return LocalImageProvider()
    elif provider_type == "local_video":
        return LocalVideoProvider()
    elif provider_type == "local_tts":
        return LocalTTSProvider()
    else:
        return StubAnalysisProvider()
