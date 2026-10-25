"""Manejadores de tareas. Cada uno devuelve un resultado; no lanza excepciones para pausar.

Resultados: COMPLETED | PARTIAL | PAUSED_QUOTA | FAILED. El worker traduce el resultado a estados.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db import models as m
from app.providers.ai import AnthropicClient, build_ai_client
from app.providers.base import ProviderError
from app.services import retention_service, spanish_service
from app.services.ingestion_service import DiscoverySource, QueryPlan, run_discovery


@dataclass
class HandlerContext:
    settings: Settings
    make_source: Callable[[], DiscoverySource]
    make_ai: Callable[[], AnthropicClient] = field(default=lambda: build_ai_client(get_settings()))


def _audit(session: Session, run_id: str, event_type: str, details: dict[str, Any]) -> None:
    session.add(
        m.AuditEvent(
            id=str(uuid4()),
            run_id=run_id,
            actor="worker",
            event_type=event_type,
            object_type="research_run",
            object_id=run_id,
            details_redacted_json=details,
        )
    )


def run_demo_research(session: Session, task: m.RunTask, ctx: HandlerContext) -> str:
    """Resume el dataset sintético. No hace red. Idempotente si ya terminó."""
    run = session.get(m.ResearchRun, task.run_id)
    if run is None:
        raise LookupError(f"Corrida inexistente: {task.run_id}")
    language_rows = session.execute(
        select(m.Video.language_state, func.count()).group_by(m.Video.language_state)
    ).all()
    channels = session.scalar(select(func.count()).select_from(m.Channel)) or 0
    run.coverage_json = {
        "dataset": "synthetic_v1",
        "network": False,
        "channels": int(channels),
        "videos_by_language_state": {str(s): int(c) for s, c in language_rows},
        "note": "Cobertura sintética; no representa el universo de YouTube.",
    }
    _audit(session, task.run_id, "RUN_COMPLETED", {"task": "demo_research"})
    return "COMPLETED"


def run_youtube_discovery(session: Session, task: m.RunTask, ctx: HandlerContext) -> str:
    """Búsqueda por idiomas y ventanas contra YouTube oficial. Reanuda desde lo ya completado."""
    run = session.get(m.ResearchRun, task.run_id)
    if run is None:
        raise LookupError(f"Corrida inexistente: {task.run_id}")
    payload = task.payload_json
    plans = [
        QueryPlan(
            language=str(q["language"]),
            query=str(q["query"]),
            window=str(q["window"]),
            region=q.get("region"),
        )
        for q in payload["queries"]
    ]
    try:
        source = ctx.make_source()
    except ProviderError as exc:
        run.errors_json = [*run.errors_json, {"code": exc.code, "detail": str(exc)}]
        return "FAILED"
    try:
        outcome = run_discovery(
            session,
            source,
            ctx.settings,
            run_id=task.run_id,
            plans=plans,
            completed_keys=set(task.result_json.get("completed", [])),
            max_search_calls=int(payload["max_search_calls"]),
            pages_per_query=int(payload["pages_per_query"]),
            now=datetime.now(UTC),
        )
    finally:
        close = getattr(source, "close", None)
        if callable(close):
            close()

    task.result_json = {"completed": outcome.completed}
    run.errors_json = [*run.errors_json, *outcome.errors]
    run.coverage_json = {
        "queries_total": len(plans),
        "queries_completed": len(outcome.completed),
        "searches": outcome.searches,
        "per_language": outcome.per_language,
    }
    _audit(session, task.run_id, f"DISCOVERY_{outcome.outcome}", {"searches": outcome.searches})
    return outcome.outcome


def run_retention_purge(session: Session, task: m.RunTask, ctx: HandlerContext) -> str:
    run = session.get(m.ResearchRun, task.run_id)
    if run is None:
        raise LookupError(f"Corrida inexistente: {task.run_id}")
    counts = retention_service.purge_expired(session, datetime.now(UTC))
    run.coverage_json = counts
    return "COMPLETED"


def run_spanish_plan(session: Session, task: m.RunTask, ctx: HandlerContext) -> str:
    """Pide a la IA un plan en español. Si la respuesta no es válida, queda NEEDS_REVIEW."""
    run = session.get(m.ResearchRun, task.run_id)
    if run is None:
        raise LookupError(f"Corrida inexistente: {task.run_id}")
    try:
        client = ctx.make_ai()
    except ProviderError as exc:
        run.errors_json = [*run.errors_json, {"code": exc.code, "detail": str(exc)}]
        return "FAILED"
    try:
        plan = spanish_service.generate_plan_with_ai(
            session, client, str(task.payload_json["opportunity_id"])
        )
    except ProviderError as exc:
        run.errors_json = [*run.errors_json, {"code": exc.code, "detail": str(exc)}]
        return "FAILED"
    finally:
        client.close()
    run.coverage_json = {
        "plan_id": plan.id,
        "plan_status": plan.status,
        "error_code": plan.error_code,
    }
    _audit(session, task.run_id, "SPANISH_PLAN_GENERATED", {"status": plan.status})
    return "COMPLETED" if plan.status == "PENDING_REVIEW" else "PARTIAL"


def run_spanish_validation(session: Session, task: m.RunTask, ctx: HandlerContext) -> str:
    """Busca en español con un plan aprobado y recalcula el estado del mercado español."""
    run = session.get(m.ResearchRun, task.run_id)
    if run is None:
        raise LookupError(f"Corrida inexistente: {task.run_id}")
    payload = task.payload_json
    opp_id = str(payload["opportunity_id"])
    plan = spanish_service.approved_plan(session, str(payload["plan_id"]), opp_id)
    plans = [
        QueryPlan(
            language="es",
            query=query,
            window=str(window),
            region="ES" if region == "ES" else None,
        )
        for region, query in spanish_service.plan_queries(plan)
        for window in payload["windows"]
    ]
    try:
        source = ctx.make_source()
    except ProviderError as exc:
        run.errors_json = [*run.errors_json, {"code": exc.code, "detail": str(exc)}]
        return "FAILED"
    try:
        outcome = run_discovery(
            session,
            source,
            ctx.settings,
            run_id=task.run_id,
            plans=plans,
            completed_keys=set(task.result_json.get("completed", [])),
            max_search_calls=int(payload["max_search_calls"]),
            pages_per_query=int(payload["pages_per_query"]),
            now=datetime.now(UTC),
            strategy="spanish_validation",
            opportunity_id=opp_id,
        )
    finally:
        close = getattr(source, "close", None)
        if callable(close):
            close()
    task.result_json = {"completed": outcome.completed}
    run.errors_json = [*run.errors_json, *outcome.errors]
    assessment = spanish_service.record_assessment(session, opp_id, task.run_id, datetime.now(UTC))
    run.coverage_json = {
        "queries_total": len(plans),
        "queries_completed": len(outcome.completed),
        "searches": outcome.searches,
        "spanish_assessment": assessment,
    }
    _audit(
        session,
        task.run_id,
        f"SPANISH_VALIDATION_{outcome.outcome}",
        {"searches": outcome.searches},
    )
    return outcome.outcome


HANDLERS: dict[str, Callable[[Session, m.RunTask, HandlerContext], str]] = {
    "demo_research": run_demo_research,
    "youtube_discovery": run_youtube_discovery,
    "retention_purge": run_retention_purge,
    "spanish_plan": run_spanish_plan,
    "spanish_validation": run_spanish_validation,
}
