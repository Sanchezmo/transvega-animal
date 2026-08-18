# Milanuncios Bot - Ad Renewal Logic
"""
Core logic for finding and renewing ads on Milanuncios.
"""

import asyncio
import random
from dataclasses import dataclass
from datetime import datetime

from bot.alerts import send_alert
from bot.browser import HumanBehavior
from bot.config import settings
from bot.metrics import (
    record_ad_failed,
    record_ad_found,
    record_ad_renewed,
    record_ad_skipped,
    record_renewal_duration,
    record_run_complete,
    record_run_duration,
    set_active_ads,
    set_current_renewing,
)
from playwright.async_api import Locator, Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError


@dataclass
class AdInfo:
    """Information about an ad found on Milanuncios."""

    id: str
    title: str
    url: str
    status: str  # 'active', 'expired', 'pending', 'draft'
    expires_at: datetime | None = None
    can_renew: bool = False
    renew_button: Locator | None = None


async def find_renewable_ads(page: Page) -> list[AdInfo]:
    """
    Navigate to mis-anuncios and find all ads that can be renewed.
    Returns list of AdInfo objects.
    """
    ads = []

    try:
        await page.goto(settings.LOGIN_URL, wait_until="networkidle", timeout=30000)
        await HumanBehavior.wait_for_page_load(page)

        # Wait for ads list to load
        await page.wait_for_selector(settings.ADS_LIST_SELECTOR, timeout=15000)

        # Scroll to load all ads
        await HumanBehavior.scroll_random(page)
        await HumanBehavior.random_delay(0.5, 1.0)

        ad_elements = await page.locator(settings.ADS_LIST_SELECTOR).all()
        record_ad_found(len(ad_elements))

        for element in ad_elements[: settings.MAX_ADS_PER_RUN]:
            ad_info = await _parse_ad_element(page, element)
            if ad_info and ad_info.can_renew:
                ads.append(ad_info)

    except PlaywrightTimeoutError:
        # No ads found or page structure changed
        pass
    except Exception as e:
        await send_alert(f"⚠️ Error buscando anuncios: {e}")

    return ads


async def _parse_ad_element(page: Page, element: Locator) -> AdInfo | None:
    """Parse individual ad element to extract info and check if renewable."""
    try:
        # Extract ad ID
        ad_id = await element.get_attribute("data-ad-id") or ""
        if not ad_id:
            link = element.locator("a[href*='/anuncio/']").first
            href = await link.get_attribute("href")
            if href:
                ad_id = href.split("/")[-1].split("-")[0]

        # Extract title
        title_elem = element.locator("h2, h3, .ad-title, [data-qa='ad-title']").first
        title = await title_elem.inner_text() if await title_elem.count() > 0 else "Sin título"
        title = title.strip()[:100]

        # Extract URL
        link_elem = element.locator("a[href*='/anuncio/']").first
        url = await link_elem.get_attribute("href") if await link_elem.count() > 0 else ""
        if url and not url.startswith("http"):
            url = f"https://www.milanuncios.com{url}"

        # Check status and renew button
        status = "unknown"
        can_renew = False
        renew_button = None

        # Look for renew button
        renew_btn = element.locator(settings.RENEW_BUTTON_SELECTOR).first
        if await renew_btn.count() > 0:
            if await renew_btn.is_visible():
                can_renew = True
                renew_button = renew_btn
                status = "expired"

        # Check status badges
        status_elem = element.locator(".status, .badge, [data-status]").first
        if await status_elem.count() > 0:
            status_text = await status_elem.inner_text()
            status_text = status_text.lower()
            if "activo" in status_text:
                status = "active"
                can_renew = False
            elif "expir" in status_text or "caduc" in status_text:
                status = "expired"
                can_renew = True
            elif "borrador" in status_text:
                status = "draft"
                can_renew = False

        return AdInfo(
            id=ad_id,
            title=title,
            url=url,
            status=status,
            can_renew=can_renew,
            renew_button=renew_button,
        )

    except Exception:
        return None


async def renew_ad(page: Page, ad: AdInfo) -> bool:
    """
    Attempt to renew a single ad.
    Returns True if successful, False otherwise.
    """
    import time

    start = time.perf_counter()

    try:
        # If we have a direct renew button on the list, use it
        if ad.renew_button:
            await _click_renew_button(page, ad.renew_button)
        else:
            # Navigate to ad detail page and find renew there
            await page.goto(ad.url, wait_until="networkidle", timeout=30000)
            await HumanBehavior.wait_for_page_load(page)

            renew_btn = page.locator(settings.RENEW_BUTTON_SELECTOR).first
            if await renew_btn.count() == 0 or not await renew_btn.is_visible():
                record_ad_skipped()
                return False
            await _click_renew_button(page, renew_btn)

        # Confirm renewal if dialog appears
        await _confirm_renewal(page)

        # Wait and verify
        await asyncio.sleep(2)
        success = await _verify_renewal_success(page, ad)

        duration = time.perf_counter() - start
        record_renewal_duration(duration)

        if success:
            record_ad_renewed()
        else:
            record_ad_failed("verification_failed")

        return success

    except Exception as e:
        duration = time.perf_counter() - start
        record_renewal_duration(duration)
        record_ad_failed("exception")
        await send_alert(f"❌ Error renovando *{ad.title}*: `{e}`")
        return False


async def _click_renew_button(page: Page, button: Locator) -> None:
    """Click renew button with human-like behavior."""
    await button.scroll_into_view_if_needed()
    await HumanBehavior.random_delay(0.3, 0.8)
    await HumanBehavior.click_like_human(page, button)


async def _confirm_renewal(page: Page) -> None:
    """Handle confirmation dialog if it appears."""
    try:
        confirm_btn = page.locator(settings.CONFIRM_RENEW_SELECTOR).first
        if await confirm_btn.count() > 0 and await confirm_btn.is_visible(timeout=3000):
            await _click_renew_button(page, confirm_btn)
            await asyncio.sleep(1)
    except Exception:
        pass  # No confirmation needed


async def _verify_renewal_success(page: Page, ad: AdInfo) -> bool:
    """Verify the renewal actually succeeded."""
    # Check for success indicators
    success_indicators = [
        "text=Renovado",
        "text=Anuncio renovado",
        ".success",
        ".toast-success",
        "[data-qa='renewal-success']",
    ]

    for selector in success_indicators:
        try:
            if await page.locator(selector).first.is_visible(timeout=3000):
                return True
        except Exception:
            continue

    # Alternative: check if renew button disappeared or changed to "editar"
    try:
        renew_btn = page.locator(settings.RENEW_BUTTON_SELECTOR).first
        if await renew_btn.count() > 0:
            if not await renew_btn.is_visible():
                return True
            text = await renew_btn.inner_text()
            if "editar" in text.lower() or "renovado" in text.lower():
                return True
    except Exception:
        pass

    return False


async def random_delay() -> None:
    """Random delay between operations to appear human."""
    delay = random.uniform(settings.RENEWAL_DELAY_MIN, settings.RENEWAL_DELAY_MAX)
    await asyncio.sleep(delay)


async def renew_all_ads(page: Page) -> dict[str, int]:
    """
    Main renewal flow: find all renewable ads and renew them.
    Returns stats dict.
    """
    import time

    run_start = time.perf_counter()

    stats = {"found": 0, "renewed": 0, "failed": 0, "skipped": 0, "duration_sec": 0}

    ads = await find_renewable_ads(page)
    stats["found"] = len(ads)
    set_active_ads(len(ads))

    if not ads:
        await send_alert("ℹ️ *Milanuncios Bot*: No hay anuncios para renovar")
        stats["duration_sec"] = int(time.perf_counter() - run_start)
        record_run_complete("success")
        record_run_duration(stats["duration_sec"])
        return stats

    await send_alert(f"🔄 *Milanuncios Bot*: Encontrados {len(ads)} anuncios para renovar")

    for i, ad in enumerate(ads):
        set_current_renewing(i + 1)
        await send_alert(f"▶️ Renovando ({i + 1}/{len(ads)}): *{ad.title}*")

        success = await renew_ad(page, ad)

        if success:
            stats["renewed"] += 1
            await send_alert(f"✅ Renovado: *{ad.title}*")
        else:
            stats["failed"] += 1
            await send_alert(f"⚠️ Falló: *{ad.title}*")

        # Random delay between ads (except last)
        if i < len(ads) - 1:
            await random_delay()

    set_current_renewing(0)

    # Final summary
    stats["duration_sec"] = int(time.perf_counter() - run_start)
    await send_alert(
        f"🏁 *Milanuncios Bot: Resumen*\n"
        f"• Encontrados: {stats['found']}\n"
        f"• Renovados: {stats['renewed']} ✅\n"
        f"• Fallidos: {stats['failed']} ❌\n"
        f"• Saltados: {stats['skipped']} ⏭️\n"
        f"• Duración: {stats['duration_sec']}s"
    )

    # Determine run status
    if stats["failed"] == 0:
        run_status = "success"
    elif stats["renewed"] > 0:
        run_status = "partial"
    else:
        run_status = "failed"

    record_run_complete(run_status)
    record_run_duration(stats["duration_sec"])

    return stats
