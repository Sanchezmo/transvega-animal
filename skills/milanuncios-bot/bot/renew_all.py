# Milanuncios Bot - Main Orchestrator
"""
Main entry point and scheduler for the Milanuncios renewal bot.
"""
import asyncio
import signal
import sys
from contextlib import asynccontextmanager
from datetime import time as dt_time

from playwright.async_api import async_playwright

from bot.config import settings
from bot.browser import BrowserManager
from bot.auth import ensure_logged_in, save_storage_state
from bot.renewal import renew_all_ads
from bot.metrics import start_metrics_server
from bot.alerts import send_alert


class MilanunciosBot:
    """Main bot orchestrator."""
    
    def __init__(self):
        self.browser_manager = None
        self.running = False
        self._shutdown_event = asyncio.Event()
    
    async def initialize(self) -> None:
        """Initialize browser and metrics."""
        # Start Prometheus metrics server
        start_metrics_server(settings.METRICS_PORT)
        
        # Initialize browser
        self.browser_manager = BrowserManager(
            headless=settings.HEADLESS,
            storage_state_path=settings.STORAGE_STATE_PATH,
        )
        await self.browser_manager.start()
        
        # Set up signal handlers
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        asyncio.create_task(self.shutdown())
    
    async def run_once(self) -> dict:
        """Run one complete renewal cycle."""
        page = await self.browser_manager.get_page()
        
        try:
            # Ensure we're logged in
            logged_in = await ensure_logged_in(page)
            if not logged_in:
                return {"status": "login_failed", "renewed": 0}
            
            # Save storage state after successful login
            await save_storage_state(self.browser_manager.context)
            
            # Run renewal cycle
            stats = await renew_all_ads(page)
            stats["status"] = "completed"
            return stats
            
        except Exception as e:
            await send_alert(f"💥 Error crítico en run_once: {e}")
            return {"status": "error", "error": str(e)}
        finally:
            await self.browser_manager.close_page(page)
    
    async def run_scheduled(self) -> None:
        """Run bot on schedule (daily at configured time)."""
        self.running = True
        
        # Calculate initial delay until next run
        next_run = self._get_next_run_time()
        delay = (next_run - datetime.now()).total_seconds()
        
        if delay > 0:
            await send_alert(f"⏰ Bot programado para ejecutarse en {delay/3600:.1f}h")
            await asyncio.sleep(delay)
        
        while self.running and not self._shutdown_event.is_set():
            try:
                await self.run_once()
            except Exception as e:
                await send_alert(f"💥 Error en ciclo programado: {e}")
            
            # Wait until next scheduled run
            next_run = self._get_next_run_time()
            delay = (next_run - datetime.now()).total_seconds()
            if delay > 0:
                await asyncio.sleep(min(delay, 3600))  # Check hourly max
    
    def _get_next_run_time(self) -> datetime:
        """Calculate next scheduled run time."""
        from datetime import datetime, timedelta
        now = datetime.now()
        run_time = dt_time(hour=settings.SCHEDULE_HOUR, minute=settings.SCHEDULE_MINUTE)
        next_run = datetime.combine(now.date(), run_time)
        if next_run <= now:
            next_run += timedelta(days=1)
        return next_run
    
    async def shutdown(self) -> None:
        """Graceful shutdown."""
        self.running = False
        self._shutdown_event.set()
        
        if self.browser_manager:
            await self.browser_manager.stop()
        
        await send_alert("🛑 Milanuncios Bot detenido")


async def main() -> int:
    """Main entry point."""
    bot = MilanunciosBot()
    
    try:
        await bot.initialize()
        
        if len(sys.argv) > 1 and sys.argv[1] == "--once":
            # Single run mode (for testing/CI)
            result = await bot.run_once()
            print(f"Result: {result}")
            await bot.shutdown()
            return 0 if result.get("status") in ("completed", "partial") else 1
        else:
            # Scheduled mode
            await bot.run_scheduled()
            return 0
            
    except KeyboardInterrupt:
        await bot.shutdown()
        return 0
    except Exception as e:
        await send_alert(f"💥 Error fatal: {e}")
        await bot.shutdown()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)