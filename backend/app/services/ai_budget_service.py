"""Tope de tokens de IA (M5, spec §9.2): una llamada de IA solo ocurre si queda presupuesto.

No hay precios de modelos en el repositorio, así que el presupuesto se mide en **tokens reales**
(los que informa el proveedor en cada respuesta), no en USD. Hay dos topes:

- `AI_DAILY_TOKEN_LIMIT`: suma de todas las funciones en el día (asistente, clasificación, plan);
- `AI_RUN_TOKEN_LIMIT`: lo que puede gastar una sola corrida (p. ej. clasificar muchos videos).

Al alcanzarlos no se llama al proveedor: se lanza `BudgetExhausted` (`PARTIAL_BUDGET_EXHAUSTED`) y
quien llama conserva lo ya hecho. Cada llamada deja una fila en `provider_usage`. Si un proveedor
no informa el uso, se anota una estimación (4 caracteres por token) marcada como tal.
"""

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db import models as m
from app.providers.ai import AIClient, TokenUsage
from app.providers.base import BudgetExhausted
from app.services import vidiq_service

PROVIDER = "ai_tokens"
BUCKET = "ai_tokens"
CHARS_PER_TOKEN = 4


def _used(session: Session, *conditions: Any) -> int:
    total = session.scalar(
        select(func.coalesce(func.sum(m.ProviderUsage.units), 0)).where(
            m.ProviderUsage.provider == PROVIDER,
            m.ProviderUsage.quota_bucket == BUCKET,
            *conditions,
        )
    )
    return int(total or 0)


def tokens_today(session: Session, now: datetime) -> int:
    return _used(session, m.ProviderUsage.started_at >= vidiq_service.day_start(now))


def run_tokens(session: Session, run_id: str) -> int:
    return _used(session, m.ProviderUsage.run_id == run_id)


def check(session: Session, settings: Settings, *, run_id: str | None, now: datetime) -> None:
    """Lanza `BudgetExhausted` si ya se alcanzó el tope diario o el de la corrida."""
    today = tokens_today(session, now)
    if today >= settings.ai_daily_token_limit:
        raise BudgetExhausted(
            f"Tope diario de IA alcanzado: {today} de {settings.ai_daily_token_limit} tokens."
        )
    if run_id is not None:
        used = run_tokens(session, run_id)
        if used >= settings.ai_run_token_limit:
            raise BudgetExhausted(
                f"Tope de IA de la corrida: {used} de {settings.ai_run_token_limit} tokens."
            )


def _estimate(text: str) -> int:
    return -(-len(text) // CHARS_PER_TOKEN)


def record(
    session: Session,
    *,
    function: str,
    model: str,
    usage: TokenUsage | None,
    estimated_tokens: int,
    run_id: str | None,
    now: datetime,
) -> int:
    tokens = usage.total if usage is not None else estimated_tokens
    session.add(
        m.ProviderUsage(
            id=str(uuid4()),
            run_id=run_id,
            provider=PROVIDER,
            endpoint=f"{function}:{model}",
            quota_bucket=BUCKET,
            units=tokens,
            started_at=now,
            status="OK" if usage is not None else "ESTIMATED",
        )
    )
    session.flush()
    return tokens


def call(
    session: Session,
    client: AIClient,
    *,
    function: str,
    system: str,
    user: str,
    run_id: str | None,
    now: datetime,
    settings: Settings | None = None,
) -> str:
    """Llama a la IA dentro del presupuesto y registra el uso real de tokens."""
    cfg = settings or get_settings()
    check(session, cfg, run_id=run_id, now=now)
    try:
        text = client.complete(system, user)
    except Exception:
        # Una respuesta truncada sí consumió tokens: se cuentan si el proveedor los informó.
        usage = getattr(client, "last_usage", None)
        if usage is not None:
            record(
                session,
                function=function,
                model=client.model,
                usage=usage,
                estimated_tokens=0,
                run_id=run_id,
                now=now,
            )
        raise
    record(
        session,
        function=function,
        model=client.model,
        usage=getattr(client, "last_usage", None),
        estimated_tokens=_estimate(system) + _estimate(user) + _estimate(text),
        run_id=run_id,
        now=now,
    )
    return text


def snapshot(session: Session, settings: Settings, now: datetime) -> dict[str, Any]:
    rows = session.execute(
        select(m.ProviderUsage.endpoint, func.sum(m.ProviderUsage.units))
        .where(
            m.ProviderUsage.provider == PROVIDER,
            m.ProviderUsage.quota_bucket == BUCKET,
            m.ProviderUsage.started_at >= vidiq_service.day_start(now),
        )
        .group_by(m.ProviderUsage.endpoint)
    ).all()
    by_function: dict[str, int] = {}
    for endpoint, units in rows:
        function = str(endpoint).split(":", 1)[0]
        by_function[function] = by_function.get(function, 0) + int(units or 0)
    used = sum(by_function.values())
    return {
        "provider": PROVIDER,
        "day_start_utc": vidiq_service.day_start(now).isoformat(),
        "tokens_used": used,
        "tokens_daily_limit": settings.ai_daily_token_limit,
        "tokens_remaining": max(0, settings.ai_daily_token_limit - used),
        "tokens_run_limit": settings.ai_run_token_limit,
        "by_function": by_function,
    }
