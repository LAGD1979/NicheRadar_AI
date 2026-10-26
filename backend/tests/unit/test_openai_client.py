"""Adaptador de OpenAI con transporte simulado: ninguna prueba sale a la red."""

import json
from typing import Any

import httpx
import pytest

from app.core.config import Settings
from app.providers.ai import OPENAI_URL, OpenAIClient, build_ai_client
from app.providers.base import (
    InvalidRequest,
    ProviderAuthError,
    ProviderNotConfigured,
    ProviderUnavailable,
)

KEY = "sk-TEST-NO-REAL-0123456789"


def _ok(content: str) -> dict[str, Any]:
    return {"choices": [{"index": 0, "message": {"role": "assistant", "content": content}}]}


def _client(handler: Any) -> OpenAIClient:
    return OpenAIClient(api_key=KEY, model="modelo-prueba", transport=httpx.MockTransport(handler))


def test_request_asks_for_json_with_system_and_user_messages() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_ok('{"schema_version":"1.0"}'))

    text = _client(handler).complete("sistema", "usuario")
    assert text == '{"schema_version":"1.0"}'
    request = seen[0]
    assert str(request.url) == OPENAI_URL
    assert request.headers["authorization"] == f"Bearer {KEY}"
    body = json.loads(request.content)
    assert body["model"] == "modelo-prueba"
    assert "temperature" not in body  # los modelos GPT-6 rechazan 0
    assert body["response_format"] == {"type": "json_object"}
    assert body["messages"] == [
        {"role": "system", "content": "sistema"},
        {"role": "user", "content": "usuario"},
    ]


def test_invalid_key_is_auth_error_and_never_echoes_it() -> None:
    client = _client(lambda r: httpx.Response(401, json={"error": {"message": KEY}}))
    with pytest.raises(ProviderAuthError) as info:
        client.complete("s", "u")
    assert KEY not in str(info.value)


def test_rate_limit_is_retried_then_succeeds() -> None:
    responses = iter([httpx.Response(429), httpx.Response(200, json=_ok("{}"))])
    assert _client(lambda r: next(responses)).complete("s", "u") == "{}"


def test_persistent_server_errors_become_unavailable() -> None:
    with pytest.raises(ProviderUnavailable):
        _client(lambda r: httpx.Response(503)).complete("s", "u")


def test_bad_request_is_not_retried() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(400, json={"error": {"message": "parámetro no admitido"}})

    with pytest.raises(InvalidRequest):
        _client(handler).complete("s", "u")
    assert len(calls) == 1


@pytest.mark.parametrize(
    "payload", [{"choices": []}, {"choices": [{"message": {"content": ""}}]}, {}]
)
def test_empty_answers_are_invalid_requests(payload: dict[str, Any]) -> None:
    with pytest.raises(InvalidRequest):
        _client(lambda r: httpx.Response(200, json=payload)).complete("s", "u")


def test_factory_builds_openai_client_when_selected_and_configured() -> None:
    settings = Settings(ai_provider="openai", openai_api_key=KEY, ai_model="modelo-prueba")  # type: ignore[arg-type]
    client = build_ai_client(settings)
    assert isinstance(client, OpenAIClient)
    assert client.model == "modelo-prueba"
    client.close()


def test_factory_refuses_openai_without_key_or_model() -> None:
    with pytest.raises(ProviderNotConfigured):
        build_ai_client(Settings(ai_provider="openai", openai_api_key="", ai_model="m"))  # type: ignore[arg-type]
    with pytest.raises(ProviderNotConfigured):
        build_ai_client(Settings(ai_provider="openai", openai_api_key=KEY, ai_model=""))  # type: ignore[arg-type]


def test_openai_truncated_response_is_reported() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"finish_reason": "length", "message": {"role": "assistant", "content": "{"}}
                ]
            },
        )

    with pytest.raises(InvalidRequest):
        _client(handler).complete("s", "u")
