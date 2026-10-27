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
from app.providers.ai import AIClient
from app.providers.base import ProviderError
from app.providers.factory import build_hasdata_source, build_vidiq_source
from app.providers.vidiq_mcp import OutlierParams
from app.services import (
    ai_selection_service,
    alerts_service,
    competitor_ai_service,
    compliance_service,
    demand_service,
    persistence_service,
    retention_service,
    spanish_service,
    vidiq_service,
    watchlist_service,
)
from app.services.ingestion_service import DiscoverySource, QueryPlan, run_discovery


@dataclass
class HandlerContext:
    settings: Settings
    make_source: Callable[[], DiscoverySource]
    # Sin esto, cada función usa el modelo elegido en Configuración (ai_selections) o, si no hay
    # elección, AI_PROVIDER y AI_MODEL. Las pruebas lo reemplazan por un doble.
    make_ai: Callable[[], AIClient] | None = None
    # Cliente de vidIQ: outliers, palabras clave e historial de videos (los dobles de prueba
    # implementan solo lo que cada prueba necesita).
    make_vidiq: Callable[[], Any] = field(default=lambda: build_vidiq_source(get_settings()))
    make_hasdata: Callable[[], Any] = field(default=lambda: build_hasdata_source(get_settings()))


def _ai_client(session: Session, ctx: HandlerContext, function: str) -> AIClient:
    if ctx.make_ai is not None:
        return ctx.make_ai()
    return ai_selection_service.build_client(session, ctx.settings, function)


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


def run_vidiq_discovery(session: Session, task: m.RunTask, ctx: HandlerContext) -> str:
    """Outliers de vidIQ por categoría/idioma. Exige la compuerta `vidiq_api` y gasta créditos."""
    run = session.get(m.ResearchRun, task.run_id)
    if run is None:
        raise LookupError(f"Corrida inexistente: {task.run_id}")
    decision = compliance_service.decide("vidiq_api", ctx.settings, session)
    if not decision.allowed:
        run.errors_json = [
            *run.errors_json,
            {"code": "POLICY_RESTRICTED", "detail": decision.reason},
        ]
        return "FAILED"
    payload = task.payload_json
    searches = [
        vidiq_service.OutlierSearch(
            OutlierParams(
                language=str(s["language"]),
                content_type=str(s.get("content_type", "long")),
                published_within=s.get("published_within"),
                trend_categories=tuple(s.get("trend_categories") or ()),
                keyword=s.get("keyword"),
                max_subscribers=s.get("max_subscribers"),
                min_views=s.get("min_views"),
                limit=int(s.get("limit", 20)),
            )
        )
        for s in payload["searches"]
    ]
    try:
        source = ctx.make_vidiq()
    except ProviderError as exc:
        run.errors_json = [*run.errors_json, {"code": exc.code, "detail": str(exc)}]
        return "FAILED"
    try:
        outcome = vidiq_service.run_outlier_discovery(
            session,
            source,
            ctx.settings,
            run_id=task.run_id,
            searches=searches,
            completed_keys=set(task.result_json.get("completed", [])),
            max_calls=int(payload["max_calls"]),
            now=datetime.now(UTC),
        )
    finally:
        close = getattr(source, "close", None)
        if callable(close):
            close()
    task.result_json = {"completed": outcome.completed}
    run.errors_json = [*run.errors_json, *outcome.errors]
    run.coverage_json = {
        "searches_total": len(searches),
        "searches_completed": len(outcome.completed),
        "calls": outcome.calls,
        "credits": outcome.credits,
        "videos_new": outcome.videos_new,
        "videos_enriched": outcome.videos_enriched,
        "records_skipped": outcome.skipped_records,
    }
    _audit(session, task.run_id, f"VIDIQ_{outcome.outcome}", {"credits": outcome.credits})
    return outcome.outcome


def _close(client: Any) -> None:
    close = getattr(client, "close", None)
    if callable(close):
        close()


def run_demand_observation(session: Session, task: m.RunTask, ctx: HandlerContext) -> str:
    """Mide la demanda en español con Trends (HasData) y palabras clave (vidIQ)."""
    run = session.get(m.ResearchRun, task.run_id)
    if run is None:
        raise LookupError(f"Corrida inexistente: {task.run_id}")
    payload = task.payload_json
    gates = {"trends": "google_trends", "vidiq": "vidiq_api"}
    allowed: list[str] = []
    for source in payload["sources"]:
        decision = compliance_service.decide(gates[source], ctx.settings, session)
        if decision.allowed:
            allowed.append(source)
        else:
            run.errors_json = [
                *run.errors_json,
                {"code": "POLICY_RESTRICTED", "detail": f"{source}: {decision.reason}"},
            ]
    if not allowed:
        return "FAILED"
    trends: Any = None
    keywords_source: Any = None
    try:
        if "trends" in allowed:
            trends = ctx.make_hasdata()
        if "vidiq" in allowed:
            keywords_source = ctx.make_vidiq()
    except ProviderError as exc:
        run.errors_json = [*run.errors_json, {"code": exc.code, "detail": str(exc)}]
        _close(trends)
        return "FAILED"
    try:
        outcome = demand_service.observe(
            session,
            ctx.settings,
            opportunity_id=str(payload["opportunity_id"]),
            keywords=[str(k) for k in payload["keywords"]],
            geo=payload.get("geo"),
            sources=allowed,
            include_related=bool(payload.get("include_related", False)),
            trends=trends,
            vidiq=keywords_source,
            run_id=task.run_id,
            completed_keys=set(task.result_json.get("completed", [])),
            now=datetime.now(UTC),
            force=bool(payload.get("force", False)),
        )
    finally:
        _close(trends)
        _close(keywords_source)
    task.result_json = {"completed": outcome.completed}
    run.errors_json = [*run.errors_json, *outcome.errors]
    run.coverage_json = {
        "observations": outcome.observations,
        "hasdata_calls": outcome.hasdata_calls,
        "vidiq_credits": outcome.vidiq_credits,
        "sources": allowed,
    }
    _audit(
        session, task.run_id, f"DEMAND_{outcome.outcome}", {"observations": outcome.observations}
    )
    return outcome.outcome


def run_vidiq_history(session: Session, task: m.RunTask, ctx: HandlerContext) -> str:
    """Mide la persistencia de la velocidad de los videos agrupados (resiliencia temporal)."""
    run = session.get(m.ResearchRun, task.run_id)
    if run is None:
        raise LookupError(f"Corrida inexistente: {task.run_id}")
    decision = compliance_service.decide("vidiq_api", ctx.settings, session)
    if not decision.allowed:
        run.errors_json = [
            *run.errors_json,
            {"code": "POLICY_RESTRICTED", "detail": decision.reason},
        ]
        return "FAILED"
    payload = task.payload_json
    try:
        source = ctx.make_vidiq()
    except ProviderError as exc:
        run.errors_json = [*run.errors_json, {"code": exc.code, "detail": str(exc)}]
        return "FAILED"
    try:
        outcome = persistence_service.measure(
            session,
            ctx.settings,
            source,
            opportunity_id=str(payload["opportunity_id"]),
            max_calls=int(payload["max_calls"]),
            run_id=task.run_id,
            now=datetime.now(UTC),
        )
    finally:
        _close(source)
    run.errors_json = [*run.errors_json, *outcome.errors]
    run.coverage_json = {
        "videos_measured": outcome.videos_measured,
        "videos_skipped_fresh": outcome.videos_skipped_fresh,
        "calls": outcome.calls,
        "credits": outcome.credits,
        "temporal_resilience": outcome.aggregate,
    }
    _audit(session, task.run_id, f"HISTORY_{outcome.outcome}", {"credits": outcome.credits})
    return outcome.outcome


def run_match_ai_review(session: Session, task: m.RunTask, ctx: HandlerContext) -> str:
    """Pide a la IA una sugerencia de calidad para cada competidor en español sin revisar."""
    run = session.get(m.ResearchRun, task.run_id)
    if run is None:
        raise LookupError(f"Corrida inexistente: {task.run_id}")
    try:
        client = _ai_client(session, ctx, "classification")
    except ProviderError as exc:
        run.errors_json = [*run.errors_json, {"code": exc.code, "detail": str(exc)}]
        return "FAILED"
    try:
        outcome = competitor_ai_service.classify(
            session,
            client,
            str(task.payload_json["opportunity_id"]),
            run_id=task.run_id,
            now=datetime.now(UTC),
        )
    finally:
        client.close()
    run.errors_json = [*run.errors_json, *outcome.errors]
    run.coverage_json = {
        "batches": outcome.batches,
        "suggested": outcome.suggested,
        "pending_left": outcome.pending_left,
    }
    _audit(session, task.run_id, f"MATCH_AI_{outcome.outcome}", {"suggested": outcome.suggested})
    return outcome.outcome


def run_retention_purge(session: Session, task: m.RunTask, ctx: HandlerContext) -> str:
    run = session.get(m.ResearchRun, task.run_id)
    if run is None:
        raise LookupError(f"Corrida inexistente: {task.run_id}")
    counts = retention_service.purge_expired(session, datetime.now(UTC))
    run.coverage_json = counts
    return "COMPLETED"


def run_alerts_check(session: Session, task: m.RunTask, ctx: HandlerContext) -> str:
    """Busca alertas del sistema con los datos ya guardados (sin llamar a proveedores)."""
    run = session.get(m.ResearchRun, task.run_id)
    if run is None:
        raise LookupError(f"Corrida inexistente: {task.run_id}")
    run.coverage_json = alerts_service.check_system(session, ctx.settings, datetime.now(UTC))
    return "COMPLETED"


def run_watchlist_recheck(session: Session, task: m.RunTask, ctx: HandlerContext) -> str:
    """Recalcula las oportunidades en seguimiento con datos guardados y avisa de cambios."""
    run = session.get(m.ResearchRun, task.run_id)
    if run is None:
        raise LookupError(f"Corrida inexistente: {task.run_id}")
    run.coverage_json = watchlist_service.recheck(session, ctx.settings, datetime.now(UTC))
    return "COMPLETED"


def run_spanish_plan(session: Session, task: m.RunTask, ctx: HandlerContext) -> str:
    """Pide a la IA un plan en español. Si la respuesta no es válida, queda NEEDS_REVIEW."""
    run = session.get(m.ResearchRun, task.run_id)
    if run is None:
        raise LookupError(f"Corrida inexistente: {task.run_id}")
    try:
        client = _ai_client(session, ctx, "plan")
    except ProviderError as exc:
        run.errors_json = [*run.errors_json, {"code": exc.code, "detail": str(exc)}]
        return "FAILED"
    try:
        plan = spanish_service.generate_plan_with_ai(
            session, client, str(task.payload_json["opportunity_id"]), run_id=task.run_id
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
    "vidiq_discovery": run_vidiq_discovery,
    "demand_observation": run_demand_observation,
    "vidiq_history": run_vidiq_history,
    "match_ai_review": run_match_ai_review,
    "retention_purge": run_retention_purge,
    "alerts_check": run_alerts_check,
    "watchlist_recheck": run_watchlist_recheck,
    "spanish_plan": run_spanish_plan,
    "spanish_validation": run_spanish_validation,
}
