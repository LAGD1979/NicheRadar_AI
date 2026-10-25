"""Contratos de los proveedores (spec §5.1). El dominio no depende del JSON de ningún proveedor."""

from dataclasses import dataclass


class ProviderError(Exception):
    """Base. Los mensajes nunca contienen URLs ni claves."""

    code = "PROVIDER_ERROR"


class ProviderNotConfigured(ProviderError):
    code = "NOT_CONFIGURED"


class ProviderAuthError(ProviderError):
    """401/403 que no son cuota, o clave inválida. Requiere acción humana (spec §9.3)."""

    code = "AUTH_ERROR"


class QuotaExhausted(ProviderError):
    """403 quotaExceeded o cuota local agotada: pausar hasta el reinicio de cuota (spec §9.3)."""

    code = "PAUSED_QUOTA"


class InvalidRequest(ProviderError):
    """4xx por entrada inválida: error definitivo, sin reintento."""

    code = "INVALID_REQUEST"


class ProviderUnavailable(ProviderError):
    """Timeout, 429 transitorio o 5xx tras agotar reintentos."""

    code = "UNAVAILABLE"


@dataclass(frozen=True)
class SearchHit:
    youtube_video_id: str
    youtube_channel_id: str
    published_at: str
    title: str


@dataclass(frozen=True)
class VideoRecord:
    youtube_video_id: str
    youtube_channel_id: str
    title: str
    published_at: str
    duration_iso: str | None
    default_language: str | None
    default_audio_language: str | None
    view_count: int | None
    live_broadcast: str | None


@dataclass(frozen=True)
class ChannelRecord:
    youtube_channel_id: str
    title: str
    subscriber_count: int | None
    hidden_subscribers: bool
    uploads_playlist_id: str | None
    country: str | None


@dataclass(frozen=True)
class SearchParams:
    query: str
    published_after: str | None
    published_before: str | None
    relevance_language: str | None
    region_code: str | None
    max_results: int = 50
    page_token: str | None = None
