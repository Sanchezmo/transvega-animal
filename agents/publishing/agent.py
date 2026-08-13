"""Publishing Agent
Handles assisted and automatic publishing of listings to platforms like Milanuncios, Facebook, Instagram, TikTok.
"""
import structlog
import json
import os
from typing import Dict, Any, Optional, List
from datetime import datetime

try:
    from playwright.async_api import async_playwright, Page, Browser
    PLAYWRIGHT_AVAILABLE = True
except Exception:  # pragma: no cover
    PLAYWRIGHT_AVAILABLE = False

logger = structlog.get_logger()


class PublishingAgent:
    """
    Agente de publicación.

    Responsabilidades:
    - Publicación asistida: generar instrucciones para que un humano publique.
    - Publicación automática: publicar directamente en la plataforma (después de validar y con aprobación).
    - Renovación, modificación y retirada de anuncios.
    - Integración con plataformas mediante sus APIs (o técnicas de automatización aprobadas).

    Este agente depende de los borradores generados por el Listing Agent y de la aprobación humana.
    Soporta múltiples plataformas: milanuncios (vía Playwright en explorador), facebook, instagram, tiktok.
    """

    def __init__(self, config: Dict):
        self.config = config
        self.agent_id = "publishing"
        self.agent_name = "Publishing Agent"
        # We'll initialize platform-specific clients as needed.
        self.capabilities = [
            "assist_publish",
            "auto_publish",
            "renew_listing",
            "update_listing",
            "remove_listing",
        ]
        self.restrictions = [
            "no_direct_db_access",
            "privacy_scope_aware",  # Only publish content that is ONLINE_ALLOWED
            "approval_required",  # No publicar sin aprobación humana
        ]

    async def _get_platform_config(self, platform: str) -> Dict:
        """Obtener configuración específica de la plataforma."""
        platform_configs = self.config.get("PLATFORMS", {})
        return platform_configs.get(platform, {})

    # --------------------------------------------------------------------- #
    # Assisted publishing (instructions)
    # --------------------------------------------------------------------- #
    async def assist_publish(self, listing_id: int, platform: str) -> Dict[str, Any]:
        """Proveer instrucciones para publicación asistida."""
        logger.info("assisting_publish", listing_id=listing_id, platform=platform)
        platform_cfg = await self._get_platform_config(platform)
        instructions = []

        if platform == "milanuncios":
            instructions = [
                "Inicie sesión en Milanuncios mediante el navegador.",
                "Navegue a 'Mis anuncios' → 'Publicar anuncio'.",
                "Seleccione la categoría adecuada (Animales → Perros).",
                "Complete el formulario con los datos proporcionados a continuación.",
                "Suba las imágenes en el orden indicado (primero la portada).",
                "Revise y publique el anuncio.",
                "Nota: Se utilizará Playwright para automatizar estos pasos en el futuro."
            ]
        elif platform in ["facebook", "instagram"]:
            instructions = [
                f"Inicie sesión en {platform.capitalize()}.",
                "Cree una nueva publicación.",
                "Añada el texto del anuncio y las imágenes.",
                "Use los hashtags sugeridos si se proporcionan.",
                "Publique en su página o perfil correspondiente."
            ]
        elif platform == "tiktok":
            instructions = [
                "Inicie sesión en TikTok.",
                "Prepare un video corto (15-60 segundos) con las imágenes proporcionadas.",
                "Añada una descripción atractiva y hashtags relevantes.",
                "Publique el video."
            ]
        else:
            instructions = [f"Instrucciones genéricas para {platform}."]

        return {
            "success": True,
            "message": f"Instrucciones para publicar en {platform} generadas.",
            "instructions": instructions,
            "platform_specific_config": platform_cfg
        }

    # --------------------------------------------------------------------- #
    # Automatic publishing (Milanuncios via Playwright)
    # --------------------------------------------------------------------- #
    async def auto_publish(self, listing_id: int, platform: str) -> Dict[str, Any]:
        """Publicar automáticamente en la plataforma."""
        logger.info("auto_publishing", listing_id=listing_id, platform=platform)
        if platform == "milanuncios":
            if not PLAYWRIGHT_AVAILABLE:
                return {
                    "success": False,
                    "error": "playwright_not_installed",
                    "platform": platform,
                    "detail": "Playwright is not installed. Install with `pip install playwright` and run `playwright install`."
                }
            return await self._milanuncios_auto_publish(listing_id)
        elif platform in ["facebook", "instagram"]:
            return {
                "success": False,
                "error": "publishing_provider_not_implemented",
                "platform": platform,
                "detail": "Graph API integration not yet implemented"
            }
        elif platform == "tiktok":
            return {
                "success": False,
                "error": "publishing_provider_not_implemented",
                "platform": platform,
                "detail": "TikTok API integration not yet implemented"
            }
        else:
            return {
                "success": False,
                "error": "unsupported_platform",
                "platform": platform
            }

    async def _milanuncios_auto_publish(self, listing_id: int) -> Dict[str, Any]:
        """Use Playwright to publish a listing on Milanuncios."""
        try:
            # Fetch listing draft from internal API (we assume a GET endpoint)
            async with self._get_http_client() as client:
                resp = await client.get(f"/listings/{listing_id}")
                if resp.status_code != 200:
                    return {"success": False, "error": f"Listing {listing_id} not found", "platform": "milanuncios"}
                listing_data = resp.json()
                # The API may wrap data
                if isinstance(listing_data, dict) and "data" in listing_data:
                    listing = listing_data["data"]
                else:
                    listing = listing_data

            # Extract needed fields
            title = listing.get("title", "")
            description = listing.get("description", "")
            price = listing.get("price", 0)
            location = listing.get("location", "")
            breed = listing.get("breed", "")
            images: List[str] = listing.get("images", [])

            # Get credentials from config
            milanuncios_cfg = await self._get_platform_config("milanuncios")
            username = milanuncios_cfg.get("username")
            password = milanuncios_cfg.get("password")
            if not username or not password:
                return {"success": False, "error": "missing_milanuncios_credentials", "platform": "milanuncios"}

            # Launch Playwright
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=False)  # set True for production
                context = await browser.new_context()
                page = await context.new_page()

                # Login
                await page.goto("https://www.milanuncios.com/", timeout=30000)
                await page.click("text=Entrar")  # adjust selector as needed
                await page.fill("input[name='email']", username)
                await page.fill("input[name='password']", password)
                await page.click("button:has-text('Entrar')")
                await page.wait_for_timeout(3000)  # wait for login

                # Navigate to publish
                await page.goto("https://www.milanuncios.com/anuncios/publicar.htm", timeout=30000)
                await page.wait_for_timeout(2000)

                # Select category: Animales > Perros
                await page.click("text=Animales")
                await page.wait_for_timeout(1000)
                await page.click("text=Perros")
                await page.wait_for_timeout(1000)

                # Fill title
                await page.fill("input[name='subject']", title)
                # Fill description
                await page.fill("textarea[name='body']", description)
                # Fill price
                await page.fill("input[name='price']", str(price))
                # Fill location
                await page.fill("input[name='location']", location)
                # Optional: breed maybe in a custom field; we ignore for now

                # Upload images
                if images:
                    # Assume images are accessible via a URL or local path; we need to upload files.
                    # For simplicity, we expect images to be accessible via a URL that the browser can fetch.
                    # We'll use the file input and set files via JS if needed.
                    file_input = await page.query_selector("input[type='file']")
                    if file_input:
                        # Prepare a list of local file paths (need to be accessible to the browser)
                        # We'll copy images to a temp directory accessible to Playwright.
                        import tempfile, shutil
                        with tempfile.TemporaryDirectory() as tmpdir:
                            local_paths = []
                            for img_url in images:
                                # If img_url is a local path already, use it; else download.
                                if img_url.startswith("http"):
                                    # download
                                    import httpx
                                    img_resp = await httpx.get(img_url, timeout=10.0)
                                    if img_resp.status_code != 200:
                                        continue
                                    ext = os.path.splitext(img_url)[1] or ".jpg"
                                    local_path = os.path.join(tmpdir, f"img{len(local_paths)}{ext}")
                                    with open(local_path, "wb") as f:
                                        f.write(img_resp.content)
                                    local_paths.append(local_path)
                                else:
                                    local_paths.append(img_url)
                            if local_paths:
                                await file_input.set_input_files(*local_paths)
                    else:
                        logger.warning("File input not found for image upload")

                # Submit
                await page.click("button:has-text('Publicar')")
                await page.wait_for_timeout(5000)  # wait for submission

                # Check for success
                success_indicator = await page.query_selector("text=Anuncio publicado")
                if success_indicator:
                    await browser.close()
                    return {
                        "success": True,
                        "message": "Anuncio publicado correctamente en Milanuncios.",
                        "platform": "milanuncios",
                        "listing_id": listing_id
                    }
                else:
                    await browser.close()
                    return {
                        "success": False,
                        "error": "publication_failed",
                        "platform": "milanuncios",
                        "detail": "No se encontró indicador de éxito tras publicar."
                    }
        except Exception as e:  # pragma: no cover
            logger.error("milanuncios_auto_publish_failed", error=str(e))
            return {
                "success": False,
                "error": "exception_during_publish",
                "platform": "milanuncios",
                "detail": str(e)
            }

    # --------------------------------------------------------------------- #
    # Renewal, Update, Removal (placeholders for Milanuncios)
    # --------------------------------------------------------------------- #
    async def renew_listing(self, listing_id: int, platform: str) -> Dict[str, Any]:
        """Renovar un anuncio existente."""
        logger.info("renewing_listing", listing_id=listing_id, platform=platform)
        if platform == "milanuncios":
            # For now, we implement renewal as re-publishing the same listing
            return await self.auto_publish(listing_id, platform)
        return {
            "success": False,
            "error": "publishing_provider_not_implemented",
            "platform": platform
        }

    async def update_listing(self, listing_id: int, platform: str, changes: Dict) -> Dict[str, Any]:
        """Actualizar un anuncio existente."""
        logger.info("updating_listing", listing_id=listing_id, platform=platform, changes=changes)
        if platform == "milanuncios":
            # For simplicity, we treat update as delete + create (not implemented)
            return {
                "success": False,
                "error": "update_not_implemented",
                "platform": "milanuncios",
                "detail": "Update functionality not yet implemented for Milanuncios via Playwright."
            }
        return {
            "success": False,
            "error": "publishing_provider_not_implemented",
            "platform": platform
        }

    async def remove_listing(self, listing_id: int, platform: str) -> Dict[str, Any]:
        """Retirar un anuncio."""
        logger.info("removing_listing", listing_id=listing_id, platform=platform)
        if platform == "milanuncios":
            # Placeholder: we could navigate to my ads and delete, but not implemented
            return {
                "success": False,
                "error": "remove_not_implemented",
                "platform": "milanuncios",
                "detail": "Remove functionality not yet implemented for Milanuncios via Playwright."
            }
        return {
            "success": False,
            "error": "publishing_provider_not_implemented",
            "platform": platform
        }

    # --------------------------------------------------------------------- #
    # Helper: HTTP client
    # --------------------------------------------------------------------- #
    async def _get_http_client(self):
        import httpx
        return httpx.AsyncClient(base_url=self.config.get("INTERNAL_API_URL", "http://localhost:8000"), timeout=30.0)


# Función de ayuda para crear el agente desde configuración
def create_publishing_agent(config: Dict) -> PublishingAgent:
    return PublishingAgent(config)