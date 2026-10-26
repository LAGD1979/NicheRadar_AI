from app.core.config import Settings
from app.providers.base import ProviderNotConfigured
from app.providers.vidiq_mcp import VidIQClient
from app.providers.youtube_official import YouTubeOfficialClient


def build_youtube_source(settings: Settings) -> YouTubeOfficialClient:
    """Cliente real. Sin clave no se crea nada: no hay llamadas ni datos de respaldo."""
    api_key = settings.youtube_api_key.get_secret_value()
    if not api_key:
        raise ProviderNotConfigured("YOUTUBE_API_KEY no está definida.")
    return YouTubeOfficialClient(
        api_key=api_key,
        base_url=settings.youtube_api_base_url,
        timeout=settings.youtube_timeout_seconds,
        max_retries=settings.youtube_max_retries,
    )


def build_vidiq_source(settings: Settings) -> VidIQClient:
    """Cliente real de vidIQ. Sin clave no se crea nada."""
    api_key = settings.vidiq_api_key.get_secret_value()
    if not api_key:
        raise ProviderNotConfigured("VIDIQ_API_KEY no está definida.")
    return VidIQClient(
        api_key=api_key,
        url=settings.vidiq_mcp_url,
        timeout=settings.vidiq_timeout_seconds,
        max_retries=settings.vidiq_max_retries,
    )
