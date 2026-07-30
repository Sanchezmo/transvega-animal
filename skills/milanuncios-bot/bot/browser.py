# Milanuncios Bot - Browser Manager
"""
Playwright browser lifecycle with stealth configuration.
"""
import asyncio
import random
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from bot.config import settings
from bot.metrics import (
    record_browser_start,
    record_browser_error,
)


# User agents for rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]

# Viewport sizes for rotation
VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1536, "height": 864},
]


class BrowserManager:
    """Manages Playwright browser lifecycle with stealth settings."""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    async def start(self) -> None:
        """Launch browser with stealth configuration."""
        start_time = time.time()
        
        self._playwright = await async_playwright().start()
        
        # Launch with anti-detection settings
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-site-isolation-trials",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-extensions",
                "--disable-popup-blocking",
            ],
        )
        
        record_browser_start(time.time() - start_time)

    async def new_context(self) -> BrowserContext:
        """Create a new stealth context."""
        if not self._browser:
            await self.start()

        # Random fingerprint
        user_agent = random.choice(USER_AGENTS)
        viewport = random.choice(VIEWPORTS)

        self._context = await self._browser.new_context(
            user_agent=user_agent,
            viewport=viewport,
            locale="es-ES",
            timezone_id="Europe/Madrid",
            extra_http_headers={
                "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Cache-Control": "max-age=0",
            },
            ignore_https_errors=True,
            java_script_enabled=True,
            bypass_csp=True,
            color_scheme="light",
            reduced_motion="no-preference",
            forced_colors="none",
        )

        # Add stealth scripts
        await self._context.add_init_script("""
            // Overwrite navigator properties to hide automation
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            
            // Overwrite chrome property
            window.chrome = {
                runtime: {},
                loadTimes: function() {},
                csi: function() {},
                app: {}
            };
            
            // Overwrite permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
            
            // Hide automation flags
            delete navigator.__proto__.webdriver;
            
            // Mock plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5].map(() => ({
                    name: 'PDF Viewer',
                    filename: 'internal-pdf-viewer',
                    description: 'Portable Document Format'
                }))
            });
            
            // Mock languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['es-ES', 'es', 'en-US', 'en']
            });
            
            // Mock hardware concurrency
            Object.defineProperty(navigator, 'hardwareConcurrency', {
                get: () => 8
            });
            
            // Mock device memory
            Object.defineProperty(navigator, 'deviceMemory', {
                get: () => 8
            });
        """)

        return self._context

    async def new_page(self) -> Page:
        """Create a new page with human-like behavior."""
        if not self._context:
            await self.new_context()

        page = await self._context.new_page()
        
        # Add random mouse movement
        await page.mouse.move(
            random.randint(100, 500),
            random.randint(100, 500)
        )
        
        # Random initial scroll
        await page.evaluate(f"window.scrollTo(0, {random.randint(0, 300)})")
        
        return page

    async def close(self) -> None:
        """Clean up resources."""
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[Page, None]:
        """Context manager for a complete browser session."""
        try:
            page = await self.new_page()
            yield page
        finally:
            await self.close()


class HumanBehavior:
    """Simulates human-like interactions."""

    @staticmethod
    async def random_delay(min_sec: float = 0.5, max_sec: float = 2.0) -> None:
        """Random delay between actions."""
        await asyncio.sleep(random.uniform(min_sec, max_sec))

    @staticmethod
    async def type_like_human(page: Page, selector: str, text: str) -> None:
        """Type text with human-like speed variations."""
        await page.click(selector)
        await HumanBehavior.random_delay(0.1, 0.3)
        
        for char in text:
            await page.keyboard.type(char)
            await asyncio.sleep(random.uniform(0.05, 0.15))

    @staticmethod
    async def click_like_human(page: Page, selector: str) -> None:
        """Click with human-like mouse movement."""
        element = await page.wait_for_selector(selector, state="visible")
        box = await element.bounding_box()
        if box:
            # Move to random point within element
            target_x = box["x"] + box["width"] * random.uniform(0.3, 0.7)
            target_y = box["y"] + box["height"] * random.uniform(0.3, 0.7)
            
            await page.mouse.move(target_x, target_y, steps=random.randint(10, 20))
            await HumanBehavior.random_delay(0.1, 0.3)
            await page.mouse.click(target_x, target_y)
        else:
            await page.click(selector)

    @staticmethod
    async def scroll_random(page: Page) -> None:
        """Random scroll to simulate reading."""
        scroll_amount = random.randint(100, 500)
        await page.evaluate(f"window.scrollBy(0, {scroll_amount})")
        await HumanBehavior.random_delay(0.5, 1.5)

    @staticmethod
    async def wait_for_page_load(page: Page, timeout: int = 30000) -> None:
        """Wait for page to fully load with network idle."""
        await page.wait_for_load_state("networkidle", timeout=timeout)
        await HumanBehavior.random_delay(0.5, 1.0)

    @staticmethod
    async def handle_captcha(page: Page) -> bool:
        """
        Detect and handle CAPTCHA.
        Returns True if CAPTCHA was solved, False otherwise.
        """
        # Check for reCAPTCHA
        recaptcha = await page.query_selector("iframe[src*='recaptcha']")
        if recaptcha:
            return False  # Need external solver
        
        # Check for hCaptcha
        hcaptcha = await page.query_selector("iframe[src*='hcaptcha']")
        if hcaptcha:
            return False
        
        # Check for text-based CAPTCHA
        captcha_text = await page.query_selector("text=/captcha|CAPTCHA|verificacion/i")
        if captcha_text:
            return False
        
        return True  # No CAPTCHA detected