"""Cliente de vidIQ por MCP (Streamable HTTP, JSON-RPC). Solo lectura (D-57).

- Autenticación: `Authorization: Bearer <clave>`. La clave nunca aparece en errores ni logs.
- Cada consulta de investigación cuesta créditos del plan del usuario; el control de gasto
  vive en `services/vidiq_service.py`, no aquí.
- Se leen los datos estructurados de `_meta.widgetData`; no se interpreta el texto en markdown.
- Solo se conservan los campos que el sistema usa (sin etiquetas, temas ni miniaturas).
"""

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.providers.base import (
    InvalidRequest,
    ProviderAuthError,
    ProviderNotConfigured,
    ProviderUnavailable,
    QuotaExhausted,
)

PROTOCOL_VERSION = "2025-03-26"
CLIENT_NAME = "nicheradar"
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
WINDOWS = ("thisWeek", "thisMonth", "threeMonths", "sixMonths", "oneYear")


@dataclass(frozen=True)
class OutlierParams:
    """Filtros de `vidiq_outliers`. Los campos en None no se envían."""

    language: str = "en"
    content_type: str = "long"
    published_within: str | None = None
    trend_categories: tuple[str, ...] = ()
    keyword: str | None = None
    max_subscribers: int | None = None
    min_views: int | None = None
    limit: int = 20

    def to_arguments(self) -> dict[str, Any]:
        args: dict[str, Any] = {
            "language": self.language,
            "contentType": self.content_type,
            "limit": self.limit,
        }
        if self.published_within:
            args["publishedWithin"] = self.published_within
        if self.trend_categories:
            args["trendCategories"] = list(self.trend_categories)
        if self.keyword:
            args["keyword"] = self.keyword
        if self.max_subscribers is not None:
            args["maxSubscribers"] = self.max_subscribers
        if self.min_views is not None:
            args["minViews"] = self.min_views
        return args


class _RawVideo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    videoId: str = Field(min_length=6, max_length=20)  # noqa: N815 - nombre del proveedor
    videoTitle: str = Field(min_length=1)  # noqa: N815
    videoPublishedAt: int  # noqa: N815 - epoch en segundos
    videoDuration: int | None = Field(default=None, ge=0)  # noqa: N815
    channelId: str = Field(min_length=6, max_length=40)  # noqa: N815
    channelTitle: str = Field(min_length=1)  # noqa: N815
    channelCountry: str | None = None  # noqa: N815
    subscriberCount: int | None = Field(default=None, ge=0)  # noqa: N815
    viewCount: int | None = Field(default=None, ge=0)  # noqa: N815
    breakoutScore: float | None = None  # noqa: N815
    vph: float | None = None
    engagementRate: float | None = None  # noqa: N815
    videoType: str | None = None  # noqa: N815
    trendCategories: list[str] | None = None  # noqa: N815
    hasAiLabel: bool | None = None  # noqa: N815


@dataclass(frozen=True)
class OutlierVideo:
    youtube_video_id: str
    title: str
    published_at: str
    duration_seconds: int | None
    youtube_channel_id: str
    channel_title: str
    channel_country: str | None
    subscriber_count: int | None
    view_count: int | None
    breakout_score: float | None
    views_per_hour: float | None
    engagement_rate: float | None
    video_type: str | None
    trend_categories: tuple[str, ...] = field(default_factory=tuple)
    ai_labeled: bool | None = None


def _to_outlier(raw: _RawVideo) -> OutlierVideo:
    published = datetime.fromtimestamp(raw.videoPublishedAt, tz=UTC).isoformat()
    return OutlierVideo(
        youtube_video_id=raw.videoId,
        title=raw.videoTitle,
        published_at=published,
        duration_seconds=raw.videoDuration,
        youtube_channel_id=raw.channelId,
        channel_title=raw.channelTitle,
        channel_country=raw.channelCountry,
        subscriber_count=raw.subscriberCount,
        view_count=raw.viewCount,
        breakout_score=raw.breakoutScore,
        views_per_hour=raw.vph,
        engagement_rate=raw.engagementRate,
        video_type=raw.videoType,
        trend_categories=tuple(raw.trendCategories or ()),
        ai_labeled=raw.hasAiLabel,
    )


def _sse_or_json(text: str) -> dict[str, Any]:
    """El servidor responde `text/event-stream` con un evento `data:`; acepta también JSON."""
    body = text.strip()
    if body.startswith("{"):
        return _as_dict(json.loads(body))
    for line in body.splitlines():
        if line.startswith("data:"):
            return _as_dict(json.loads(line[5:].strip()))
    raise InvalidRequest("Respuesta de vidIQ sin datos.")


def _as_dict(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InvalidRequest("Respuesta de vidIQ con formato inesperado.")
    return value


def _error_text(error: Any) -> str:
    if isinstance(error, dict):
        return str(error.get("message", ""))
    return str(error)


class VidIQClient:
    def __init__(
        self,
        *,
        api_key: str,
        url: str,
        timeout: float = 30.0,
        max_retries: int = 3,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_key:
            raise ProviderNotConfigured("VIDIQ_API_KEY no está definida.")
        self._api_key = api_key
        self._url = url
        self._max_retries = max_retries
        self._sleep = sleep
        self._next_id = 0
        self._http = httpx.Client(timeout=timeout, transport=transport)

    def close(self) -> None:
        self._http.close()

    def _post(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self._next_id += 1
        body = {"jsonrpc": "2.0", "id": self._next_id, "method": method, "params": params}
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        for attempt in range(self._max_retries):
            last = attempt == self._max_retries - 1
            try:
                response = self._http.post(self._url, headers=headers, json=body)
            except httpx.TransportError as exc:
                if last:
                    raise ProviderUnavailable("vidIQ: sin respuesta.") from exc
                self._sleep(min(2**attempt, 8))
                continue
            if response.status_code in (401, 403):
                raise ProviderAuthError("vidIQ rechazó la clave (revoque y genere otra).")
            if response.status_code in RETRYABLE_STATUS:
                if last:
                    raise ProviderUnavailable(f"vidIQ: HTTP {response.status_code}.")
                self._sleep(min(2**attempt, 8))
                continue
            if response.status_code >= 400:
                raise InvalidRequest(f"vidIQ: HTTP {response.status_code}.")
            return _sse_or_json(response.text)
        raise ProviderUnavailable("vidIQ: reintentos agotados.")

    def _call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        message = self._post("tools/call", {"name": name, "arguments": arguments})
        if "error" in message:
            raise self._tool_error(_error_text(message["error"]))
        result = _as_dict(message.get("result"))
        if result.get("isError"):
            texts = " ".join(str(c.get("text", "")) for c in result.get("content", []))
            raise self._tool_error(texts)
        return result

    @staticmethod
    def _tool_error(detail: str) -> Exception:
        lowered = detail.lower()
        if "credit" in lowered or "insufficient" in lowered or "limit" in lowered:
            return QuotaExhausted("vidIQ: créditos del plan agotados.")
        return InvalidRequest("vidIQ rechazó la consulta.")

    def outliers(self, params: OutlierParams) -> tuple[list[OutlierVideo], int]:
        """Videos válidos y cuántos registros se descartaron por no cumplir el contrato."""
        result = self._call_tool("vidiq_outliers", params.to_arguments())
        widget = (result.get("_meta") or {}).get("widgetData")
        if not isinstance(widget, dict) or "videos" not in widget:
            text = " ".join(str(c.get("text", "")) for c in result.get("content", []))
            if text.lstrip().lower().startswith(("no ", "found 0")):
                return [], 0
            raise InvalidRequest("Respuesta de vidIQ con formato inesperado.")
        videos: list[OutlierVideo] = []
        skipped = 0
        for item in widget["videos"]:
            try:
                videos.append(_to_outlier(_RawVideo.model_validate(item)))
            except ValidationError:
                skipped += 1  # un registro inválido no invalida el resto
        return videos, skipped

    def balance(self) -> int | None:
        """Créditos restantes. No consume créditos."""
        result = self._call_tool("vidiq_balance", {})
        structured = result.get("structuredContent")
        if isinstance(structured, dict) and isinstance(structured.get("totalCredits"), int):
            return int(structured["totalCredits"])
        return None
