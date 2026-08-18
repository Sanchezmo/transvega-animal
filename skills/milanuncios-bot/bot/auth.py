# Milanuncios Bot - Authentication
"""
Login and session management for Milanuncios.
"""

import asyncio
import os

from bot.alerts import send_alert, send_login_failed_alert
from bot.browser import HumanBehavior
from bot.config import settings
from bot.metrics import record_login_attempt, record_login_duration
from playwright.async_api import BrowserContext, Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError


async def login(page: Page) -> bool:
    """
    Perform login to Milanuncios.
    Returns True if successful, False otherwise.
    """
    import time

    start = time.perf_counter()

    try:
        await page.goto(settings.LOGIN_URL, wait_until="networkidle", timeout=30000)
        await HumanBehavior.wait_for_page_load(page)

        # Fill email
        email_input = page.locator(settings.LOGIN_EMAIL_SELECTOR).first
        if await email_input.count() == 0:
            raise Exception("Email input not found")

        await email_input.fill("")
        await HumanBehavior.type_like_human(email_input, settings.MILANUNCIOS_EMAIL)
        await HumanBehavior.random_delay(0.3, 0.6)

        # Fill password
        pass_input = page.locator(settings.LOGIN_PASSWORD_SELECTOR).first
        if await pass_input.count() == 0:
            raise Exception("Password input not found")

        await pass_input.fill("")
        await HumanBehavior.type_like_human(pass_input, settings.MILANUNCIOS_PASSWORD)
        await HumanBehavior.random_delay(0.3, 0.6)

        # Submit
        submit_btn = page.locator(settings.LOGIN_SUBMIT_SELECTOR).first
        if await submit_btn.count() == 0:
            raise Exception("Submit button not found")

        await HumanBehavior.click_like_human(page, submit_btn)
        await HumanBehavior.wait_for_page_load(page, timeout=30000)

        # Check if login succeeded
        success = await _verify_login_success(page)

        duration = time.perf_counter() - start
        record_login_duration(duration)

        if success:
            record_login_attempt("success")
            return True
        else:
            record_login_attempt("failed")
            return False

    except PlaywrightTimeoutError:
        duration = time.perf_counter() - start
        record_login_duration(duration)
        record_login_attempt("timeout")
        return False
    except Exception as e:
        duration = time.perf_counter() - start
        record_login_duration(duration)
        record_login_attempt("error")
        await send_alert(f"❌ Error en login: {e}")
        return False


async def _verify_login_success(page: Page) -> bool:
    """Verify login was successful by checking for logged-in indicators."""
    # Check for user menu, profile link, or absence of login form
    indicators = [
        "[data-qa='user-menu']",
        ".user-menu",
        "a[href*='mis-anuncios']",
        "text=Mi cuenta",
        "text=Cerrar sesión",
    ]

    for selector in indicators:
        try:
            if await page.locator(selector).first.is_visible(timeout=5000):
                return True
        except:
            continue

    # Check if we're still on login page
    try:
        login_form = page.locator(settings.LOGIN_EMAIL_SELECTOR).first
        if await login_form.is_visible(timeout=3000):
            return False
    except:
        pass

    return True


async def save_storage_state(context: BrowserContext) -> None:
    """Save browser storage state (cookies, localStorage) for session reuse."""
    try:
        await context.storage_state(path=settings.STORAGE_STATE_PATH)
    except Exception as e:
        await send_alert(f"⚠️ No se pudo guardar storage_state: {e}")


async def load_storage_state(context: BrowserContext) -> bool:
    """Load previously saved storage state. Returns True if loaded successfully."""
    if not os.path.exists(settings.STORAGE_STATE_PATH):
        return False

    try:
        # Storage state is loaded when creating context, not after
        # This is just a check
        return True
    except Exception:
        return False


async def needs_login(page: Page) -> bool:
    """Check if current page requires login."""
    try:
        login_form = page.locator(settings.LOGIN_EMAIL_SELECTOR).first
        return await login_form.is_visible(timeout=3000)
    except:
        return False


async def ensure_logged_in(page: Page, max_retries: int = 3) -> bool:
    """
    Ensure we're logged in. Attempt login if needed.
    Returns True if logged in successfully.
    """
    # Check if already logged in
    if not await needs_login(page):
        return True

    for attempt in range(max_retries):
        await send_alert(f"🔐 Intentando login (intento {attempt + 1}/{max_retries})")

        success = await login(page)
        if success:
            return True

        await asyncio.sleep(5 * (attempt + 1))  # Exponential backoff

    # All retries failed
    await send_login_failed_alert(max_retries)
    return False


async def handle_2fa(page: Page) -> bool:
    """
    Handle 2FA if presented.
    Returns True if handled, False if manual intervention needed.
    """
    # Check for 2FA indicators
    twofa_indicators = [
        "text=/código.*autenticación|authenticator|2fa|two.?factor/i",
        "input[name='code'], input[name='otp'], input[name='2fa']",
    ]

    for selector in twofa_indicators:
        try:
            if await page.locator(selector).first.is_visible(timeout=3000):
                await send_alert("🔐 2FA detectado - intervención manual requerida")
                # Wait for manual input (up to 5 minutes)
                for _ in range(300):
                    if not await needs_login(page):
                        return True
                    await asyncio.sleep(1)
                return False
        except:
            continue

    return True  # No 2FA detected
