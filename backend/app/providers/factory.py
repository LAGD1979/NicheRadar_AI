from app.core.config import Settings
from app.providers.base import ProviderNotConfigured
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
