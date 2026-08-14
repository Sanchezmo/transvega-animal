"""Publishing Agent
Handles assisted and automatic publishing of listings to platforms like Milanuncios, Facebook, Instagram, TikTok.
"""
import os
import structlog
import tempfile
from typing import Dict, Any, Optional, List
from datetime import datetime

try:
    from playwright.async_api import async_playwright, Page, Browser, Playwright
    PLAYWRIGHT_AVAILABLE = True
except Exception:  # pragma: no cover
    PLAYWRIGHT_AVAILABLE = False

from app.core.internal_api_client import InternalAPIClient, create_internal_api_client, InternalAPIError

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
        self.api_base = config.get("INTERNAL_API_URL", "http://localhost:8000/api/v1")
        self.api_key = config.get("AGENT_API_KEY_PUBLISHING", "")
        self.api_client: Optional[InternalAPIClient] = None
        
        # Playwright config
        self.playwright_headless = config.get("PLAYWRIGHT_HEADLESS", "true").lower() == "true"
        
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

    async def start(self):
        """Initialize the internal API client."""
        if self.api_client is None:
            self.api_client = await create_internal_api_client(
                agent_name="publishing",
                base_url=self.api_base,
                api_key=self.api_key or None,
            )
            await self.api_client.start()
        logger.info("publishing_agent_started", headless=self.playwright_headless)

    async def stop(self):
        """Close the internal API client."""
        if self.api_client:
            await self.api_client.close()
            self.api_client = None

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
        if self.api_client is None:
            return {"success": False, "error": "PublishingAgent not started. Call start() first."}

        try:
            # Fetch publication from internal API (canonical endpoint: /api/v1/publicaciones/{id})
            try:
                publication = await self.api_client.get(f"/publicaciones/{listing_id}")
            except InternalAPIError as e:
                if e.status_code == 404:
                    return {"success": False, "error": f"Publication {listing_id} not found", "platform": "milanuncios"}
                logger.error("api_error_fetching_publication", listing_id=listing_id, error=e.message)
                return {"success": False, "error": f"API error: {e.message}", "platform": "milanuncios"}

            # Extract needed fields
            title = publication.get("title", "")
            description = publication.get("description", "")
            price = publication.get("price", 0)
            location = publication.get("location", "")
            breed = publication.get("breed", "")
            images: List[str] = publication.get("photos", []) or publication.get("images", [])

            # Get credentials from config
            milanuncios_cfg = await self._get_platform_config("milanuncios")
            username = milanuncios_cfg.get("username")
            password = milanuncios_cfg.get("password")
            if not username or not password:
                return {"success": False, "error": "missing_milanuncios_credentials", "platform": "milanuncios"}

            # Launch Playwright
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=self.playwright_headless)
                context = await browser.new_context()
                page = await context.new_page()

                # Login
                await page.goto("https://www.milanuncios.com/", timeout=30000)
                
                # Check for CAPTCHA
                if await self._check_captcha(page):
                    await browser.close()
                    return {
                        "success": False,
                        "error": "requires_human_action",
                        "platform": "milanuncios",
                        "detail": "CAPTCHA detected during login. Manual intervention required.",
                        "requires_human_action": True
                    }
                
                await page.click("text=Entrar")  # adjust selector as needed
                await page.fill("input[name='email']", username)
                await page.fill("input[name='password']", password)
                await page.click("button:has-text('Entrar')")
                await page.wait_for_timeout(3000)  # wait for login

                # Check if login succeeded (session valid)
                if await self._check_session_expired(page):
                    await browser.close()
                    return {
                        "success": False,
                        "error": "requires_human_action",
                        "platform": "milanuncios",
                        "detail": "Login failed - session expired or invalid credentials. Manual intervention required.",
                        "requires_human_action": True
                    }

                # Navigate to publish
                await page.goto("https://www.milanuncios.com/anuncios/publicar.htm", timeout=30000)
                await page.wait_for_timeout(2000)

                # Check for CAPTCHA on publish page
                if await self._check_captcha(page):
                    await browser.close()
                    return {
                        "success": False,
                        "error": "requires_human_action",
                        "platform": "milanuncios",
                        "detail": "CAPTCHA detected on publish page. Manual intervention required.",
                        "requires_human_action": True
                    }

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

                # Upload images
                if images:
                    file_input = await page.query_selector("input[type='file']")
                    if file_input:
                        with tempfile.TemporaryDirectory() as tmpdir:
                            local_paths = []
                            for img_url in images:
                                if img_url.startswith("http"):
                                    # download using internal API client
                                    try:
                                        # For external URLs, we still need httpx
                                        import httpx
                                        async with httpx.AsyncClient(timeout=10.0) as img_client:
                                            img_resp = await img_client.get(img_url)
                                        if img_resp.status_code != 200:
                                            logger.warning("failed_to_download_image", url=img_url)
                                            continue
                                        ext = os.path.splitext(img_url)[1] or ".jpg"
                                        local_path = os.path.join(tmpdir, f"img{len(local_paths)}{ext}")
                                        with open(local_path, "wb") as f:
                                            f.write(img_resp.content)
                                        local_paths.append(local_path)
                                    except Exception as e:
                                        logger.warning("failed_to_download_image", url=img_url, error=str(e))
                                        continue
                                else:
                                    # Local path
                                    local_paths.append(img_url)
                            if local_paths:
                                await file_input.set_input_files(*local_paths)
                    else:
                        logger.warning("File input not found for image upload")

                # Submit
                await page.click("button:has-text('Publicar')")
                await page.wait_for_timeout(5000)  # wait for submission

                # Check for CAPTCHA after submission
                if await self._check_captcha(page):
                    await browser.close()
                    return {
                        "success": False,
                        "error": "requires_human_action",
                        "platform": "milanuncios",
                        "detail": "CAPTCHA detected after submission. Manual intervention required.",
                        "requires_human_action": True
                    }

                # Check for success
                success_indicator = await page.query_selector("text=Anuncio publicado")
                if success_indicator:
                    # Try to extract external_id and external_url
                    external_id = await self._extract_external_id(page)
                    external_url = await self._extract_external_url(page)
                    
                    await browser.close()
                    return {
                        "success": True,
                        "message": "Anuncio publicado correctamente en Milanuncios.",
                        "platform": "milanuncios",
                        "listing_id": listing_id,
                        "external_id": external_id,
                        "external_url": external_url,
                    }
                else:
                    # Check if session expired after submission
                    if await self._check_session_expired(page):
                        await browser.close()
                        return {
                            "success": False,
                            "error": "requires_human_action",
                            "platform": "milanuncios",
                            "detail": "Session expired during publication. Manual intervention required.",
                            "requires_human_action": True
                        }
                    
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

    async def _check_captcha(self, page: "Page") -> bool:
        """Check if CAPTCHA is present on the page."""
        try:
            # Common CAPTCHA indicators
            captcha_selectors = [
                "iframe[src*='recaptcha']",
                "iframe[src*='hcaptcha']",
                ".g-recaptcha",
                ".h-captcha",
                "text=Comprobar que eres humano",
                "text=Verify you are human",
                "#captcha",
                ".captcha-container",
            ]
            for selector in captcha_selectors:
                element = await page.query_selector(selector)
                if element:
                    logger.warning("captcha_detected", selector=selector)
                    return True
        except Exception:
            pass
        return False

    async def _check_session_expired(self, page: "Page") -> bool:
        """Check if session has expired (login required)."""
        try:
            expired_selectors = [
                "text=Iniciar sesión",
                "text=Entrar",
                "input[name='email']",
                "input[name='password']",
                "text=Tu sesión ha expirado",
                "text=Session expired",
            ]
            for selector in expired_selectors:
                element = await page.query_selector(selector)
                if element:
                    logger.warning("session_expired_detected", selector=selector)
                    return True
        except Exception:
            pass
        return False

    async def _extract_external_id(self, page: "Page") -> Optional[str]:
        """Extract external ID from the published ad page."""
        try:
            # Try to find the ad ID in URL or page content
            url = page.url
            # Milanuncios URLs typically contain the ad ID
            import re
            match = re.search(r'/anuncio/(\d+)', url)
            if match:
                return match.group(1)
        except Exception:
            pass
        return None

    async def _extract_external_url(self, page: "Page") -> Optional[str]:
        """Extract the external URL of the published ad."""
        try:
            return page.url
        except Exception:
            return None

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


# Función de ayuda para crear el agente desde configuración
def create_publishing_agent(config: Dict) -> PublishingAgent:
    return PublishingAgent(config)