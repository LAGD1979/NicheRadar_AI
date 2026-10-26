"""Adaptador de Anthropic con transporte simulado: ninguna prueba sale a la red."""

import json

import httpx
import pytest

from app.providers.ai import ANTHROPIC_URL, AnthropicClient
from app.providers.base import InvalidRequest

KEY = "sk-ant-TEST-NO-REAL-0123456789"


def test_request_has_no_temperature_and_returns_text() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"content": [{"type": "text", "text": '{"ok":1}'}]})

    client = AnthropicClient(
        api_key=KEY, model="modelo-prueba", transport=httpx.MockTransport(handler)
    )
    assert client.complete("sistema", "usuario") == '{"ok":1}'
    request = seen[0]
    assert str(request.url) == ANTHROPIC_URL
    assert request.headers["x-api-key"] == KEY
    body = json.loads(request.content)
    # Los modelos recientes rechazan `temperature` con HTTP 400 (comprobado en vivo, D-56).
    assert "temperature" not in body
    assert body["model"] == "modelo-prueba"
    assert body["messages"] == [{"role": "user", "content": "usuario"}]


def test_truncated_response_is_reported_not_parsed() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"stop_reason": "max_tokens", "content": [{"type": "text", "text": '{"a":'}]}
        )

    client = AnthropicClient(api_key=KEY, model="m", transport=httpx.MockTransport(handler))
    with pytest.raises(InvalidRequest):
        client.complete("s", "u")


def test_output_limit_leaves_room_for_reasoning() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"content": [{"type": "text", "text": "{}"}]})

    AnthropicClient(api_key=KEY, model="m", transport=httpx.MockTransport(handler)).complete(
        "s", "u"
    )
    assert json.loads(seen[0].content)["max_tokens"] >= 8000
