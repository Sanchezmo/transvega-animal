"""
Dependency para inyectar cliente Dolibarr.
"""

from collections.abc import AsyncGenerator

from app.adapters.dolibarr.client import DolibarrClient
from app.core.config import get_settings

settings = get_settings()


async def get_dolibarr_client() -> AsyncGenerator[DolibarrClient, None]:
    """
    Dependency que provee un cliente Dolibarr configurado.
    Usa async context manager para manejo correcto de conexiones.
    """
    client = DolibarrClient(
        base_url=settings.DOLIBARR_API_URL,
        api_key=settings.DOLIBARR_API_KEY,
        timeout=settings.DOLIBARR_TIMEOUT,
    )
    async with client as c:
        yield c
