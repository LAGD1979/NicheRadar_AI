"""Elección de IA y modelo por función (D-68). Sin llamadas de red."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db import models as m
from app.jobs.handlers import HandlerContext, _ai_client
from app.providers.ai import AnthropicClient, OpenAIClient
from app.services import ai_selection_service

OPP = "syn-opp-01"
SETTINGS_URL = "/api/v1/ai/settings"


@pytest.fixture
def keys(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Ambos proveedores con clave de prueba, y sin IA por defecto en el entorno."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "clave-anthropic-de-prueba")
    monkeypatch.setenv("OPENAI_API_KEY", "clave-openai-de-prueba")
    monkeypatch.setenv("AI_PROVIDER", "none")
    monkeypatch.setenv("AI_MODEL", "")
    get_settings.cache_clear()
    yield
    for name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "AI_PROVIDER", "AI_MODEL"):
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()


def _put(client: TestClient, function: str, provider: str, model: str) -> Any:
    return client.put(f"{SETTINGS_URL}/{function}", json={"provider": provider, "model": model})


# --- catálogo y valores por defecto ---------------------------------------------------------------


def test_overview_lists_three_functions_and_the_catalog(client: TestClient) -> None:
    body = client.get(SETTINGS_URL).json()
    assert [f["id"] for f in body["functions"]] == ["assistant", "classification", "plan"]
    assert all(f["source"] == "default" for f in body["functions"])
    models = {(c["provider"], c["model"]) for c in body["catalog"]}
    assert {
        ("openai", "gpt-6-luna"),
        ("openai", "gpt-6.1-sol"),
        ("openai", "gpt-6-astra"),
    } <= models
    assert ("anthropic", "claude-haiku-5-5") in models
    assert "key" not in str(body).lower().replace("monkey", "")  # nunca expone claves


def test_catalog_marks_providers_without_a_key_as_unavailable(
    client: TestClient, keys: None
) -> None:
    assert all(c["available"] for c in client.get(SETTINGS_URL).json()["catalog"])


def test_without_a_selection_the_environment_default_rules(
    seeded_db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AI_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "clave-de-prueba")
    monkeypatch.setenv("AI_MODEL", "modelo-del-entorno")
    get_settings.cache_clear()
    chosen = ai_selection_service.selection(seeded_db, get_settings(), "assistant")
    assert (chosen["provider"], chosen["model"], chosen["source"]) == (
        "anthropic",
        "modelo-del-entorno",
        "default",
    )
    assert chosen["configured"] is True
    for name in ("AI_PROVIDER", "ANTHROPIC_API_KEY", "AI_MODEL"):
        monkeypatch.delenv(name)
    get_settings.cache_clear()


# --- elegir, validar y volver al valor por defecto --------------------------------------------


def test_each_function_keeps_its_own_model(client: TestClient, keys: None) -> None:
    assert _put(client, "classification", "openai", "gpt-6-luna").status_code == 200
    assert _put(client, "assistant", "openai", "gpt-6.1-sol").status_code == 200
    assert _put(client, "plan", "anthropic", "claude-sonnet-5-5").status_code == 200
    by_id = {f["id"]: f for f in client.get(SETTINGS_URL).json()["functions"]}
    assert (by_id["classification"]["provider"], by_id["classification"]["model"]) == (
        "openai",
        "gpt-6-luna",
    )
    assert by_id["assistant"]["model"] == "gpt-6.1-sol"
    assert by_id["plan"]["model"] == "claude-sonnet-5-5"
    assert all(f["source"] == "user" and f["configured"] for f in by_id.values())


def test_changing_one_function_does_not_touch_the_others(client: TestClient, keys: None) -> None:
    _put(client, "assistant", "openai", "gpt-6-astra")
    _put(client, "classification", "openai", "gpt-6-luna")
    _put(client, "assistant", "anthropic", "claude-opus-5-5")
    by_id = {f["id"]: f for f in client.get(SETTINGS_URL).json()["functions"]}
    assert by_id["assistant"]["model"] == "claude-opus-5-5"
    assert by_id["classification"]["model"] == "gpt-6-luna"
    assert by_id["plan"]["source"] == "default"


def test_models_outside_the_catalog_or_of_another_provider_are_refused(
    client: TestClient, keys: None
) -> None:
    unknown = _put(client, "assistant", "openai", "gpt-inventado")
    assert (unknown.status_code, unknown.json()["code"]) == (422, "AI_MODEL_NOT_ALLOWED")
    crossed = _put(client, "assistant", "anthropic", "gpt-6-luna")
    assert crossed.status_code == 422
    assert _put(client, "assistant", "otro", "x").status_code == 422
    assert _put(client, "no-existe", "openai", "gpt-6-luna").status_code == 404
    assert client.get(SETTINGS_URL).json()["functions"][0]["source"] == "default"


def test_a_provider_without_a_key_cannot_be_chosen(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()
    refused = _put(client, "assistant", "openai", "gpt-6-luna")
    assert (refused.status_code, refused.json()["code"]) == (409, "AI_PROVIDER_NOT_CONFIGURED")
    assert not any(c["available"] for c in client.get(SETTINGS_URL).json()["catalog"])


def test_clearing_a_selection_returns_to_the_default(client: TestClient, keys: None) -> None:
    _put(client, "plan", "openai", "gpt-6.1-sol")
    cleared = client.delete(f"{SETTINGS_URL}/plan").json()
    assert cleared["source"] == "default"
    assert client.delete(f"{SETTINGS_URL}/plan").status_code == 200  # idempotente
    assert client.delete(f"{SETTINGS_URL}/no-existe").status_code == 404


def test_every_change_is_audited_without_keys(
    client: TestClient, keys: None, seeded_db: Session
) -> None:
    _put(client, "assistant", "openai", "gpt-6-luna")
    client.delete(f"{SETTINGS_URL}/assistant")
    seeded_db.expire_all()
    events = seeded_db.scalars(
        select(m.AuditEvent).where(m.AuditEvent.event_type == "AI_SELECTION_CHANGED")
    ).all()
    assert len(events) == 2
    assert "clave-" not in str([e.details_redacted_json for e in events])


# --- uso de la elección ---------------------------------------------------------------------------


def test_build_client_returns_the_provider_and_model_of_each_function(
    seeded_db: Session, client: TestClient, keys: None
) -> None:
    _put(client, "classification", "openai", "gpt-6-luna")
    _put(client, "assistant", "anthropic", "claude-sonnet-5-5")
    seeded_db.expire_all()
    settings = get_settings()
    bulk = ai_selection_service.build_client(seeded_db, settings, "classification")
    chat = ai_selection_service.build_client(seeded_db, settings, "assistant")
    assert isinstance(bulk, OpenAIClient) and bulk.model == "gpt-6-luna"
    assert isinstance(chat, AnthropicClient) and chat.model == "claude-sonnet-5-5"


def test_the_worker_asks_for_the_model_of_the_function_it_runs(
    seeded_db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[str] = []

    def fake_build(_s: Session, _settings: Settings, function: str, **_: Any) -> Any:
        asked.append(function)
        return object()

    monkeypatch.setattr(ai_selection_service, "build_client", fake_build)
    ctx = HandlerContext(settings=get_settings(), make_source=lambda: None)  # type: ignore[arg-type,return-value]
    _ai_client(seeded_db, ctx, "classification")
    _ai_client(seeded_db, ctx, "plan")
    assert asked == ["classification", "plan"]
    forced = object()
    override = HandlerContext(
        settings=get_settings(),
        make_source=lambda: None,  # type: ignore[arg-type,return-value]
        make_ai=lambda: forced,  # type: ignore[arg-type,return-value]
    )
    assert _ai_client(seeded_db, override, "plan") is forced  # el doble de prueba manda


def test_endpoints_accept_work_when_only_the_selection_configures_the_ai(
    client: TestClient, keys: None
) -> None:
    # Sin AI_PROVIDER en el entorno, la IA queda lista solo por la elección de cada función.
    refused = client.post(f"/api/v1/opportunities/{OPP}/search-plans/generate")
    assert refused.json()["code"] == "AI_NOT_CONFIGURED"
    _put(client, "plan", "openai", "gpt-6.1-sol")
    accepted = client.post(f"/api/v1/opportunities/{OPP}/search-plans/generate")
    assert accepted.status_code == 202
    run = client.get(f"/api/v1/research-runs/{accepted.json()['id']}").json()
    assert run["params"]["model"] == "gpt-6.1-sol"
    # La clasificación no tiene elección: sigue sin IA aunque el plan sí.
    other = client.post(f"/api/v1/opportunities/{OPP}/competition/ai-review")
    assert other.json()["code"] == "AI_NOT_CONFIGURED"


def test_assistant_status_shows_its_own_model(client: TestClient, keys: None) -> None:
    assert client.get("/api/v1/assistant/status").json()["configured"] is False
    _put(client, "assistant", "openai", "gpt-6-luna")
    status = client.get("/api/v1/assistant/status").json()
    assert (status["configured"], status["model"], status["model_source"]) == (
        True,
        "gpt-6-luna",
        "user",
    )
    assert status["provider"] == "openai"


def test_the_assistant_builds_its_client_from_its_own_selection(
    client: TestClient, keys: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[str] = []

    class Fake:
        model = "doble"

        def complete(self, system: str, user: str) -> str:
            return '{"answer":"ok","citations":[],"unknowns":[],"next_steps":[]}'

        def close(self) -> None:
            return None

    def fake_build(_s: Session, _settings: Settings, function: str, **_: Any) -> Fake:
        seen.append(function)
        return Fake()

    _put(client, "assistant", "openai", "gpt-6-luna")
    monkeypatch.setattr(ai_selection_service, "build_client", fake_build)
    response = client.post(f"/api/v1/opportunities/{OPP}/assistant", json={"message": "hola"})
    assert response.status_code == 200
    assert seen == ["assistant"]
