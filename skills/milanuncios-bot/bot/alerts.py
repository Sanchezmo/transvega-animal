# Milanuncios Bot - Alerts
"""
Telegram notifications for critical events.
"""
import os
from typing import Optional

from bot.config import settings


async def send_alert(message: str, parse_mode: str = "Markdown") -> bool:
    """
    Send alert via Telegram bot.
    Returns True if sent successfully, False otherwise.
    """
    token = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.TELEGRAM_CHAT_ID
    
    if not token or not chat_id:
        return False
    
    try:
        import aiohttp
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=10) as resp:
                return resp.status == 200
    except Exception:
        return False


async def send_critical_alert(title: str, details: str) -> None:
    """Send critical alert that requires immediate attention."""
    message = f"🚨 *{title}*\n\n{details}"
    await send_alert(message)


async def send_daily_summary(stats: dict) -> None:
    """Send daily run summary."""
    message = (
        f"📊 *Milanuncios Bot: Resumen Diario*\n\n"
        f"• Encontrados: {stats.get('found', 0)}\n"
        f"• Renovados: {stats.get('renewed', 0)} ✅\n"
        f"• Fallidos: {stats.get('failed', 0)} ❌\n"
        f"• Saltados: {stats.get('skipped', 0)} ⏭️\n"
        f"• Duración: {stats.get('duration_sec', 0)}s"
    )
    await send_alert(message)


async def send_captcha_alert() -> None:
    """Alert when CAPTCHA is detected."""
    message = (
        "🔴 *Milanuncios Bot: CAPTCHA Detectado*\n\n"
        "El bot ha encontrado un desafío CAPTCHA.\n"
        "Se pausará 15 minutos antes de reintentar.\n"
        "Revisar manualmente si persiste."
    )
    await send_alert(message)


async def send_login_failed_alert(error: str) -> None:
    """Alert when login fails after retries."""
    message = (
        "🔴 *Milanuncios Bot: Login Fallido*\n\n"
        f"Después de 3 reintentos no se pudo iniciar sesión.\n"
        f"```\n{error}\n```\n"
        "Verificar credenciales o 2FA."
    )
    await send_alert(message)