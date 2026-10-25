"""Proveedores de IA tipados (spec §4.1, §11). Devuelven texto; la validación la hace el dominio.

Sin proveedor, modelo o clave no hay cliente, y la fase de IA se detiene (T13, spec §17).
Anthropic y OpenAI comparten interfaz: `model`, `complete(system, user)` y `close()`.
"""

import json
from typing import Any, Protocol

import httpx

from app.core.config import Settings
from app.providers.base import (
    InvalidRequest,
    ProviderAuthError,
    ProviderNotConfigured,
    ProviderUnavailable,
)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
RETRYABLE = {429, 500, 502, 503, 529}
MAX_ATTEMPTS = 3


class AIClient(Protocol):
    @property
    def model(self) -> str: ...

    def complete(self, system: str, user: str) -> str: ...

    def close(self) -> None: ...


def _post_with_retries(
    http: httpx.Client, url: str, headers: dict[str, str], body: dict[str, Any], label: str
) -> dict[str, Any]:
    """Envía la petición con reintentos ante timeouts y errores transitorios. Sin claves."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = http.post(url, headers=headers, content=json.dumps(body))
        except httpx.TimeoutException as exc:
            if attempt < MAX_ATTEMPTS:
                continue
            raise ProviderUnavailable(f"{label}: tiempo de espera agotado") from exc
        if response.status_code < 400:
            payload: dict[str, Any] = response.json()
            return payload
        if response.status_code in (401, 403):
            raise ProviderAuthError(f"{label}: credencial rechazada (HTTP {response.status_code})")
        if response.status_code in RETRYABLE:
            if attempt < MAX_ATTEMPTS:
                continue
            raise ProviderUnavailable(f"{label}: HTTP {response.status_code}")
        raise InvalidRequest(f"{label}: HTTP {response.status_code}")
    raise ProviderUnavailable(f"{label}: reintentos agotados")


class AnthropicClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        max_tokens: int = 2000,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 60.0,
    ) -> None:
        if not api_key or not model:
            raise ProviderNotConfigured("Faltan ANTHROPIC_API_KEY o AI_MODEL.")
        self._api_key = api_key
        self._model = model
        self._max_tokens = max_tokens
        self._http = httpx.Client(timeout=timeout, transport=transport)

    @property
    def model(self) -> str:
        return self._model

    def close(self) -> None:
        self._http.close()

    def complete(self, system: str, user: str) -> str:
        body: dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "temperature": 0,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        payload = _post_with_retries(self._http, ANTHROPIC_URL, headers, body, "IA (Anthropic)")
        return _anthropic_text(payload)


class OpenAIClient:
    """Chat Completions con salida JSON forzada. Requiere que el prompt mencione JSON (lo hace)."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        max_output_tokens: int = 2000,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 60.0,
    ) -> None:
        if not api_key or not model:
            raise ProviderNotConfigured("Faltan OPENAI_API_KEY o AI_MODEL.")
        self._api_key = api_key
        self._model = model
        self._max_output_tokens = max_output_tokens
        self._http = httpx.Client(timeout=timeout, transport=transport)

    @property
    def model(self) -> str:
        return self._model

    def close(self) -> None:
        self._http.close()

    def complete(self, system: str, user: str) -> str:
        body: dict[str, Any] = {
            "model": self._model,
            "temperature": 0,
            "max_completion_tokens": self._max_output_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "content-type": "application/json",
        }
        payload = _post_with_retries(self._http, OPENAI_URL, headers, body, "IA (OpenAI)")
        return _openai_text(payload)


def _anthropic_text(payload: dict[str, Any]) -> str:
    parts = payload.get("content") or []
    texts = [
        str(p.get("text", "")) for p in parts if isinstance(p, dict) and p.get("type") == "text"
    ]
    if not texts:
        raise InvalidRequest("IA: respuesta sin texto")
    return "".join(texts)


def _openai_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        raise InvalidRequest("IA (OpenAI): respuesta sin opciones")
    message = choices[0].get("message") or {}
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise InvalidRequest("IA (OpenAI): respuesta sin texto")
    return content


def build_ai_client(settings: Settings) -> AIClient:
    if settings.ai_provider == "none":
        raise ProviderNotConfigured("AI_PROVIDER=none: la fase de IA está desactivada.")
    if settings.ai_provider == "openai":
        return OpenAIClient(
            api_key=settings.openai_api_key.get_secret_value(),
            model=settings.ai_model,
        )
    return AnthropicClient(
        api_key=settings.anthropic_api_key.get_secret_value(),
        model=settings.ai_model,
    )
