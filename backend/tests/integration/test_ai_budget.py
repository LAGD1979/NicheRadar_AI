"""Topes de tokens de IA (D-70): real cuando el proveedor lo informa, estimado si no."""

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1 import assistant_routes
from app.core.config import get_settings
from app.db import models as m
from app.providers.ai import AnthropicClient, OpenAIClient, TokenUsage
from app.providers.base import BudgetExhausted, ResponseTruncated
from app.services import ai_budget_service as budget
from app.services import alerts_service
from app.services import competitor_ai_service as ai_svc
from tests.integration.test_competitor_ai import OPP, FakeAI, _seed, _titles

NOW = datetime(2026, 10, 26, 15, 0, tzinfo=UTC)


class UsageAI:
    """IA simulada que informa su uso, como lo hacen los proveedores reales."""

    model = "modelo-de-prueba"

    def __init__(self, reply: str = "{}", usage: TokenUsage | None = None) -> None:
        self.reply = reply
        self.usage = usage
        self.last_usage: TokenUsage | None = None
        self.calls = 0

    def complete(self, system: str, user: str) -> str:
        self.calls += 1
        self.last_usage = self.usage
        return self.reply

    def close(self) -> None:
        return None


@pytest.fixture
def limits(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    def set_limits(daily: int | None = None, run: int | None = None) -> None:
        if daily is not None:
            monkeypatch.setenv("AI_DAILY_TOKEN_LIMIT", str(daily))
        if run is not None:
            monkeypatch.setenv("AI_RUN_TOKEN_LIMIT", str(run))
        get_settings.cache_clear()

    yield set_limits
    for name in ("AI_DAILY_TOKEN_LIMIT", "AI_RUN_TOKEN_LIMIT"):
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()


def _call(session: Session, client: Any, run_id: str | None = None, **over: Any) -> str:
    args: dict[str, Any] = {
        "function": "assistant",
        "system": "sistema",
        "user": "usuario",
        "run_id": run_id,
        "now": NOW,
    }
    return budget.call(session, client, **{**args, **over})


def _rows(session: Session) -> list[m.ProviderUsage]:
    session.expire_all()
    return list(
        session.scalars(select(m.ProviderUsage).where(m.ProviderUsage.provider == budget.PROVIDER))
    )


# --- los clientes informan el uso real --------------------------------------------------------


def _anthropic(handler: Any) -> AnthropicClient:
    return AnthropicClient(api_key="k", model="m", transport=httpx.MockTransport(handler))


def _openai(handler: Any) -> OpenAIClient:
    return OpenAIClient(api_key="k", model="m", transport=httpx.MockTransport(handler))


def test_anthropic_reports_the_tokens_it_consumed() -> None:
    body = {
        "content": [{"type": "text", "text": "hola"}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 120, "output_tokens": 30},
    }
    client = _anthropic(lambda _r: httpx.Response(200, json=body))
    assert client.last_usage is None
    client.complete("s", "u")
    assert client.last_usage == TokenUsage(120, 30)
    assert client.last_usage.total == 150


def test_openai_reports_the_tokens_it_consumed() -> None:
    body = {
        "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 50, "completion_tokens": 8},
    }
    client = _openai(lambda _r: httpx.Response(200, json=body))
    client.complete("s", "u")
    assert client.last_usage == TokenUsage(50, 8)


def test_a_truncated_answer_still_reports_its_cost() -> None:
    body = {
        "content": [{"type": "text", "text": "x"}],
        "stop_reason": "max_tokens",
        "usage": {"input_tokens": 10, "output_tokens": 8000},
    }
    client = _anthropic(lambda _r: httpx.Response(200, json=body))
    with pytest.raises(ResponseTruncated):
        client.complete("s", "u")
    assert client.last_usage == TokenUsage(10, 8000)


def test_a_failed_call_does_not_inherit_the_previous_usage() -> None:
    ok = {
        "content": [{"type": "text", "text": "hola"}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 5, "output_tokens": 5},
    }
    responses = iter([httpx.Response(200, json=ok), httpx.Response(400)])
    client = _anthropic(lambda _r: next(responses))
    client.complete("s", "u")
    assert client.last_usage is not None
    with pytest.raises(Exception):  # noqa: B017, PT011 - cualquier error del proveedor
        client.complete("s", "u")
    assert client.last_usage is None


def test_a_response_without_usage_is_not_made_up() -> None:
    body = {"content": [{"type": "text", "text": "hola"}], "stop_reason": "end_turn"}
    client = _anthropic(lambda _r: httpx.Response(200, json=body))
    client.complete("s", "u")
    assert client.last_usage is None


# --- presupuesto ------------------------------------------------------------------------------


def test_real_usage_is_recorded_per_function(seeded_db: Session) -> None:
    ai = UsageAI(usage=TokenUsage(1000, 200))
    _call(seeded_db, ai, function="assistant")
    _call(seeded_db, ai, function="classification", run_id="run-1")
    rows = _rows(seeded_db)
    assert [(r.units, r.status) for r in rows] == [(1200, "OK"), (1200, "OK")]
    assert {r.endpoint for r in rows} == {
        "assistant:modelo-de-prueba",
        "classification:modelo-de-prueba",
    }
    snapshot = budget.snapshot(seeded_db, get_settings(), NOW)
    assert snapshot["tokens_used"] == 2400
    assert snapshot["by_function"] == {"assistant": 1200, "classification": 1200}
    assert snapshot["tokens_remaining"] == snapshot["tokens_daily_limit"] - 2400


def test_without_provider_usage_an_estimate_is_recorded_and_labelled(seeded_db: Session) -> None:
    _call(seeded_db, UsageAI(reply="a" * 400, usage=None), user="b" * 800)
    row = _rows(seeded_db)[0]
    assert row.status == "ESTIMATED"
    assert (
        row.units == (7 + 800 + 400 + 3) // 4
    )  # sistema + usuario + respuesta, 4 caracteres por token


def test_the_daily_limit_stops_calls_before_reaching_the_provider(
    seeded_db: Session, limits: Any
) -> None:
    limits(daily=100)
    ai = UsageAI(usage=TokenUsage(90, 20))
    _call(seeded_db, ai)  # 110 de 100: la siguiente ya no pasa
    with pytest.raises(BudgetExhausted) as stopped:
        _call(seeded_db, ai)
    assert stopped.value.code == "PARTIAL_BUDGET_EXHAUSTED"
    assert ai.calls == 1


def test_the_run_limit_is_per_run_and_the_daily_limit_is_shared(
    seeded_db: Session, limits: Any
) -> None:
    limits(daily=10_000, run=100)
    ai = UsageAI(usage=TokenUsage(90, 20))
    _call(seeded_db, ai, run_id="run-a")
    with pytest.raises(BudgetExhausted):
        _call(seeded_db, ai, run_id="run-a")
    _call(seeded_db, ai, run_id="run-b")  # otra corrida tiene su propio tope
    assert ai.calls == 2


def test_a_failed_call_without_usage_costs_nothing_but_a_truncated_one_does(
    seeded_db: Session,
) -> None:
    class Failing(UsageAI):
        def complete(self, system: str, user: str) -> str:
            self.calls += 1
            self.last_usage = self.usage
            raise ResponseTruncated("truncada")

    with pytest.raises(ResponseTruncated):
        _call(seeded_db, Failing(usage=TokenUsage(10, 8000)))
    assert [r.units for r in _rows(seeded_db)] == [8010]
    with pytest.raises(ResponseTruncated):
        _call(seeded_db, Failing(usage=None))
    assert len(_rows(seeded_db)) == 1  # sin uso informado no se inventa un costo


# --- aplicado a las funciones -----------------------------------------------------------------


def test_classification_stops_at_the_run_limit_and_keeps_what_it_did(
    seeded_db: Session, limits: Any
) -> None:
    limits(run=1)
    _seed(seeded_db, _titles(6))
    ai = FakeAI()
    outcome = ai_svc.classify(seeded_db, ai, OPP, run_id="run-x", now=NOW, batch_size=2)
    assert outcome.outcome == "PARTIAL"
    assert [e["code"] for e in outcome.errors][0] == "PARTIAL_BUDGET_EXHAUSTED"
    assert ai.calls == 1  # el primer lote se hizo y el resto no se pidió
    assert outcome.suggested == 2
    assert outcome.pending_left == 4
    assert outcome.batches == 1


def test_classification_without_limits_reached_is_unaffected(seeded_db: Session) -> None:
    _seed(seeded_db, _titles(6))
    outcome = ai_svc.classify(seeded_db, FakeAI(), OPP, run_id="run-y", now=NOW)
    assert outcome.outcome == "COMPLETED"
    assert budget.run_tokens(seeded_db, "run-y") > 0


@pytest.fixture
def assistant_ai(client: TestClient) -> Iterator[UsageAI]:
    fake = UsageAI(
        reply='{"answer":"ok","citations":[],"unknowns":[],"next_steps":[]}',
        usage=TokenUsage(600, 100),
    )
    from app.main import app

    app.dependency_overrides[assistant_routes.ai_client] = lambda: fake
    yield fake
    app.dependency_overrides.pop(assistant_routes.ai_client, None)


def test_the_assistant_answers_429_when_the_daily_tokens_are_gone(
    client: TestClient, assistant_ai: UsageAI, limits: Any
) -> None:
    limits(daily=500)
    url = f"/api/v1/opportunities/{OPP}/assistant"
    assert client.post(url, json={"message": "hola"}).status_code == 200
    blocked = client.post(url, json={"message": "otra"})
    assert (blocked.status_code, blocked.json()["code"]) == (429, "AI_BUDGET_EXHAUSTED")
    assert assistant_ai.calls == 1
    usage = client.get("/api/v1/usage/ai").json()
    assert usage["tokens_used"] == 700
    assert usage["by_function"] == {"assistant": 700}
    assert usage["tokens_remaining"] == 0


def test_usage_endpoint_starts_empty_and_exposes_both_limits(client: TestClient) -> None:
    usage = client.get("/api/v1/usage/ai").json()
    assert usage["tokens_used"] == 0 and usage["by_function"] == {}
    assert usage["tokens_daily_limit"] == 1_000_000
    assert usage["tokens_run_limit"] == 300_000


def test_the_plan_function_respects_the_budget(seeded_db: Session, limits: Any) -> None:
    from app.services import spanish_service

    limits(daily=1)
    # La función del plan usa la hora real, así que el gasto que agota el tope también.
    _call(seeded_db, UsageAI(usage=TokenUsage(5, 5)), now=datetime.now(UTC))
    ai = UsageAI()
    with pytest.raises(BudgetExhausted):
        spanish_service.generate_plan_with_ai(seeded_db, ai, OPP, run_id="run-plan")
    assert ai.calls == 0


def test_an_alert_warns_when_the_ai_tokens_reach_80_percent(
    seeded_db: Session, limits: Any
) -> None:
    limits(daily=1000)
    _call(seeded_db, UsageAI(usage=TokenUsage(700, 50)))  # 75 %
    assert alerts_service.check_system(seeded_db, get_settings(), NOW)["quota"] == 0
    _call(seeded_db, UsageAI(usage=TokenUsage(60, 0)))  # 81 %
    assert alerts_service.check_system(seeded_db, get_settings(), NOW)["quota"] == 1
    alert = seeded_db.scalars(select(m.Alert)).one()
    assert alert.alert_type == "QUOTA_WARNING" and "IA" in alert.message
    assert json.dumps(alert.details_json)  # serializable y sin claves
