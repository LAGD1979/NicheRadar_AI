"""Proveedor de IA tipado (spec §4.1, §11). Devuelve texto; la validación la hace el dominio.

Sin proveedor, modelo o clave, no hay cliente y la fase de IA se detiene (T13, spec §17).
"""

import json
from typing import Any

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
RETRYABLE = {429, 500, 502, 503, 529}


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
        for attempt in range(1, 4):
            try:
                response = self._http.post(ANTHROPIC_URL, headers=headers, content=json.dumps(body))
            except httpx.TimeoutException as exc:
                if attempt < 3:
                    continue
                raise ProviderUnavailable("IA: tiempo de espera agotado") from exc
            if response.status_code < 400:
                return _text_of(response.json())
            if response.status_code in (401, 403):
                raise ProviderAuthError(f"IA: credencial rechazada (HTTP {response.status_code})")
            if response.status_code in RETRYABLE and attempt < 3:
                continue
            if response.status_code in RETRYABLE:
                raise ProviderUnavailable(f"IA: HTTP {response.status_code}")
            raise InvalidRequest(f"IA: HTTP {response.status_code}")
        raise ProviderUnavailable("IA: reintentos agotados")


def _text_of(payload: dict[str, Any]) -> str:
    parts = payload.get("content") or []
    texts = [
        str(p.get("text", "")) for p in parts if isinstance(p, dict) and p.get("type") == "text"
    ]
    if not texts:
        raise InvalidRequest("IA: respuesta sin texto")
    return "".join(texts)


def build_ai_client(settings: Settings) -> AnthropicClient:
    if settings.ai_provider == "none":
        raise ProviderNotConfigured("AI_PROVIDER=none: la fase de IA está desactivada.")
    if settings.ai_provider == "openai":
        raise ProviderNotConfigured("OpenAI aún no está implementado en M2.")
    return AnthropicClient(
        api_key=settings.anthropic_api_key.get_secret_value(),
        model=settings.ai_model,
    )
