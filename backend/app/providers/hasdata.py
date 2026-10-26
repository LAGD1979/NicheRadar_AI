"""HasData: Google Trends por API REST (D-63). Solo lectura.

- `GET /scrape/google-trends/search` con la clave en `x-api-key`. Cada consulta cuesta 10 créditos
  de HasData y solo se cobra si tiene éxito.
- HasData obtiene los datos de Google Trends por scraping en su lado: el uso de esta fuente es una
  decisión de cumplimiento del responsable y queda registrado en `policy_approvals` (capacidad
  `google_trends`).
- Los valores son un **índice relativo de 0 a 100**, no volúmenes de búsqueda. Una consulta sin
  datos suficientes se devuelve como desconocida (`None`), nunca como cero.
- `timeseries` acepta hasta 5 términos separados por coma en una sola llamada (probado en vivo: 10
  créditos). El índice de cada término queda **relativo al más fuerte del grupo**, de modo que los
  términos de una misma llamada son comparables entre sí y los de llamadas distintas no.
- Se envía `tz=0` siempre para que las semanas se alineen en UTC, no en la hora del Pacífico.
- La clave nunca aparece en errores ni logs.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from app.providers.base import (
    InvalidRequest,
    ProviderAuthError,
    ProviderNotConfigured,
    ProviderUnavailable,
    QuotaExhausted,
)

SEARCH_PATH = "/scrape/google-trends/search"
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
DATE_PRESETS = ("today 3-m", "today 12-m", "today 5-y", "all")
GPROPS = ("", "youtube", "news", "images", "froogle")
MAX_TERMS = 5
TZ_MINUTES = "0"


@dataclass(frozen=True)
class TrendPoint:
    """Un punto semanal del índice relativo. `value=None` si Google no tuvo datos."""

    timestamp: datetime
    value: int | None
    partial: bool


@dataclass(frozen=True)
class RelatedQuery:
    query: str
    kind: str  # "top" | "rising"
    value: int | None


def _int_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


class HasDataClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.hasdata.com",
        timeout: float = 45.0,
        max_retries: int = 3,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_key:
            raise ProviderNotConfigured("HASDATA_API_KEY no está definida.")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._max_retries = max_retries
        self._sleep = sleep
        self._http = httpx.Client(timeout=timeout, transport=transport)

    def close(self) -> None:
        self._http.close()

    def _get(self, params: dict[str, str]) -> dict[str, Any]:
        headers = {"x-api-key": self._api_key, "Content-Type": "application/json"}
        url = f"{self._base_url}{SEARCH_PATH}"
        for attempt in range(self._max_retries):
            last = attempt == self._max_retries - 1
            try:
                response = self._http.get(url, params=params, headers=headers)
            except httpx.TransportError as exc:
                if last:
                    raise ProviderUnavailable("HasData: sin respuesta.") from exc
                self._sleep(min(2**attempt, 8))
                continue
            if response.status_code in (401, 403):
                raise ProviderAuthError("HasData rechazó la clave (revise o genere otra).")
            if response.status_code == 402:
                raise QuotaExhausted("HasData: créditos del plan agotados.")
            if response.status_code in RETRYABLE_STATUS:
                if last:
                    raise ProviderUnavailable(f"HasData: HTTP {response.status_code}.")
                self._sleep(min(2**attempt, 8))
                continue
            if response.status_code >= 400:
                raise InvalidRequest(f"HasData: HTTP {response.status_code}.")
            try:
                body = response.json()
            except ValueError as exc:
                raise InvalidRequest("HasData: respuesta que no es JSON.") from exc
            if not isinstance(body, dict):
                raise InvalidRequest("HasData: respuesta con formato inesperado.")
            status = (body.get("requestMetadata") or {}).get("status")
            if status not in (None, "ok"):
                raise InvalidRequest("HasData: la consulta no se completó.")
            return body
        raise ProviderUnavailable("HasData: reintentos agotados.")

    @staticmethod
    def _params(query: str, geo: str, date: str, gprop: str, data_type: str) -> dict[str, str]:
        if not query.strip():
            raise InvalidRequest("HasData: la consulta no puede estar vacía.")
        if "," in query and data_type != "timeseries":
            raise InvalidRequest("HasData: este tipo de consulta admite un solo término.")
        if date not in DATE_PRESETS:
            raise InvalidRequest("HasData: rango de fechas no permitido.")
        if gprop not in GPROPS:
            raise InvalidRequest("HasData: propiedad de Google no permitida.")
        params = {"q": query.strip(), "date": date, "dataType": data_type, "tz": TZ_MINUTES}
        if geo:
            params["geo"] = geo
        if gprop:
            params["gprop"] = gprop
        return params

    def interest_over_time(
        self, query: str, *, geo: str = "", date: str = "today 12-m", gprop: str = "youtube"
    ) -> list[TrendPoint]:
        """Índice relativo semanal de una sola consulta (10 créditos de HasData)."""
        return self.compare_interest([query], geo=geo, date=date, gprop=gprop)[query.strip()]

    def compare_interest(
        self,
        queries: list[str],
        *,
        geo: str = "",
        date: str = "today 12-m",
        gprop: str = "youtube",
    ) -> dict[str, list[TrendPoint]]:
        """Serie semanal de hasta 5 términos en **una** llamada (10 créditos).

        El índice de cada término es relativo al más fuerte del grupo. Devuelve una serie por
        término pedido; un término sin datos trae `value=None` en todas sus semanas.
        """
        terms = [q.strip() for q in queries if q.strip()]
        if not 1 <= len(terms) <= MAX_TERMS:
            raise InvalidRequest(f"HasData: entre 1 y {MAX_TERMS} términos por llamada.")
        if any("," in t for t in terms):
            raise InvalidRequest("HasData: un término no puede contener comas.")
        if len({t.lower() for t in terms}) != len(terms):
            raise InvalidRequest("HasData: términos repetidos.")
        body = self._get(self._params(",".join(terms), geo, date, gprop, "timeseries"))
        timeline = (body.get("interestOverTime") or {}).get("timelineData")
        if not isinstance(timeline, list):
            raise InvalidRequest("HasData: respuesta sin serie temporal.")
        by_name = {t.lower(): t for t in terms}
        series: dict[str, list[TrendPoint]] = {t: [] for t in terms}
        for item in timeline:
            if not isinstance(item, dict):
                continue
            try:
                moment = datetime.fromtimestamp(int(item["timestamp"]), tz=UTC)
            except (KeyError, ValueError, TypeError):
                continue
            values = item.get("values")
            if not isinstance(values, list):
                continue
            entries = [e for e in values if isinstance(e, dict)]
            names = [str(e.get("query", "")).strip().lower() for e in entries]
            # Por el nombre que devuelve HasData; si no coincide (p. ej. normaliza el texto),
            # por la posición, que respeta el orden pedido.
            by_name_ok = all(n in by_name for n in names) and len(set(names)) == len(names)
            for position, entry in enumerate(entries):
                if by_name_ok:
                    term = by_name[names[position]]
                elif position < len(terms) and len(entries) == len(terms):
                    term = terms[position]
                else:
                    continue
                value = (
                    _int_or_none(entry.get("extractedValue"))
                    if entry.get("hasData") is True
                    else None
                )
                series[term].append(
                    TrendPoint(timestamp=moment, value=value, partial=bool(item.get("isPartial")))
                )
        if not any(series.values()):
            raise InvalidRequest("HasData: la respuesta no trae los términos pedidos.")
        return series

    def related_queries(
        self, query: str, *, geo: str = "", date: str = "today 12-m", gprop: str = "youtube"
    ) -> list[RelatedQuery]:
        """Consultas relacionadas (top y en alza) de una sola consulta (10 créditos)."""
        body = self._get(self._params(query, geo, date, gprop, "relatedQueries"))
        related = body.get("relatedQueries")
        if not isinstance(related, dict):
            raise InvalidRequest("HasData: respuesta sin consultas relacionadas.")
        out: list[RelatedQuery] = []
        for kind in ("top", "rising"):
            for item in related.get(kind) or []:
                if isinstance(item, dict) and isinstance(item.get("query"), str):
                    out.append(
                        RelatedQuery(
                            query=item["query"],
                            kind=kind,
                            value=_int_or_none(item.get("extractedValue")),
                        )
                    )
        return out
