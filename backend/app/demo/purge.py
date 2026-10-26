"""Quita los datos de la demo (synthetic_v1) de la base, sin tocar lo real (D-65).

Uso (por defecto solo simula y no borra nada):

  python -m app.demo.purge            # lista lo que se borraría y lo que se conserva
  python -m app.demo.purge --apply    # borra, en una sola transacción

Qué se borra: los registros del fixture (nichos, formatos, canales, videos, oportunidades, la
corrida y la auditoría de la carga) y todo lo que cuelga de esas oportunidades: evaluaciones,
evidencia, anotaciones, planes, búsquedas, coincidencias, modelos de costo y mediciones de demanda.

Qué NO se toca: videos y canales reales (aunque se hayan anotado a una oportunidad de la demo),
oportunidades reales, corridas y su historial de auditoría. Si una oportunidad real usa un nicho
o formato de la demo, el comando se detiene y lo informa: no adivina.
"""

import argparse
import sys
from typing import Any

import structlog
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db import models as m
from app.db.session import get_session_factory
from app.demo.seed import load_fixture

log = structlog.get_logger("demo_purge")


def fixture_ids(data: dict[str, Any]) -> dict[str, set[str]]:
    return {
        "niches": {item["id"] for item in data["niches"]},
        "formats": {item["id"] for item in data["formats"]},
        "channels": {item["id"] for item in data["channels"]},
        "videos": {item["id"] for item in data["videos"]},
        "opportunities": {item["id"] for item in data["opportunities"]},
    }


def _count(session: Session, model: type[m.Base], *conditions: Any) -> int:
    return int(session.scalar(select(func.count()).select_from(model).where(*conditions)) or 0)


def blockers(session: Session, ids: dict[str, set[str]]) -> list[str]:
    """Oportunidades reales que dependen de un nicho o formato de la demo."""
    rows = session.execute(
        select(m.Opportunity.id, m.Opportunity.niche_id, m.Opportunity.format_id).where(
            m.Opportunity.id.not_in(ids["opportunities"])
        )
    ).all()
    return [
        opportunity_id
        for opportunity_id, niche_id, format_id in rows
        if niche_id in ids["niches"] or format_id in ids["formats"]
    ]


def plan(session: Session, data: dict[str, Any]) -> dict[str, dict[str, int]]:
    """Cuántas filas se borrarían por tabla y cuántas quedan de lo real."""
    ids = fixture_ids(data)
    run_id = data["run"]["id"]
    opps = ids["opportunities"]
    # Un canal de la demo solo se borra si no le quedan videos reales.
    channel_keepers = set(
        session.scalars(
            select(m.Video.channel_id).where(
                m.Video.id.not_in(ids["videos"]), m.Video.channel_id.in_(ids["channels"])
            )
        )
    )
    delete_counts = {
        "demand_observations": _count(
            session, m.DemandObservation, m.DemandObservation.opportunity_id.in_(opps)
        ),
        "discovery_matches": _count(
            session, m.DiscoveryMatch, m.DiscoveryMatch.opportunity_id.in_(opps)
        ),
        "source_queries": _count(session, m.SourceQuery, m.SourceQuery.opportunity_id.in_(opps)),
        "video_annotations": _count(
            session, m.VideoAnnotation, m.VideoAnnotation.opportunity_id.in_(opps)
        ),
        "opportunity_evidence": _count(
            session, m.OpportunityEvidence, m.OpportunityEvidence.opportunity_id.in_(opps)
        ),
        "evaluations": _count(session, m.Evaluation, m.Evaluation.opportunity_id.in_(opps)),
        "spanish_search_plans": _count(
            session, m.SpanishSearchPlan, m.SpanishSearchPlan.opportunity_id.in_(opps)
        ),
        "cost_models": _count(session, m.CostModel, m.CostModel.opportunity_id.in_(opps)),
        "opportunities": _count(session, m.Opportunity, m.Opportunity.id.in_(opps)),
        "videos": _count(session, m.Video, m.Video.id.in_(ids["videos"])),
        "channels": _count(session, m.Channel, m.Channel.id.in_(ids["channels"] - channel_keepers)),
        "niches": _count(session, m.Niche, m.Niche.id.in_(ids["niches"])),
        "formats": _count(session, m.Format, m.Format.id.in_(ids["formats"])),
        "research_runs": _count(session, m.ResearchRun, m.ResearchRun.id == run_id),
    }
    keep_counts = {
        "videos_reales": _count(session, m.Video, m.Video.id.not_in(ids["videos"])),
        "canales_reales": _count(session, m.Channel, m.Channel.id.not_in(ids["channels"]))
        + len(channel_keepers),
        "oportunidades_reales": _count(session, m.Opportunity, m.Opportunity.id.not_in(opps)),
        "corridas_reales": _count(session, m.ResearchRun, m.ResearchRun.id != run_id),
    }
    return {"borrar": delete_counts, "conservar": keep_counts}


def apply(session: Session, data: dict[str, Any]) -> dict[str, int]:
    ids = fixture_ids(data)
    run_id = data["run"]["id"]
    opps = ids["opportunities"]
    channel_keepers = set(
        session.scalars(
            select(m.Video.channel_id).where(
                m.Video.id.not_in(ids["videos"]), m.Video.channel_id.in_(ids["channels"])
            )
        )
    )
    steps: list[tuple[str, Any]] = [
        (
            "demand_observations",
            delete(m.DemandObservation).where(m.DemandObservation.opportunity_id.in_(opps)),
        ),
        (
            "discovery_matches",
            delete(m.DiscoveryMatch).where(m.DiscoveryMatch.opportunity_id.in_(opps)),
        ),
        ("source_queries", delete(m.SourceQuery).where(m.SourceQuery.opportunity_id.in_(opps))),
        (
            "video_annotations",
            delete(m.VideoAnnotation).where(m.VideoAnnotation.opportunity_id.in_(opps)),
        ),
        (
            "opportunity_evidence",
            delete(m.OpportunityEvidence).where(m.OpportunityEvidence.opportunity_id.in_(opps)),
        ),
        ("evaluations", delete(m.Evaluation).where(m.Evaluation.opportunity_id.in_(opps))),
        (
            "spanish_search_plans",
            delete(m.SpanishSearchPlan).where(m.SpanishSearchPlan.opportunity_id.in_(opps)),
        ),
        ("cost_models", delete(m.CostModel).where(m.CostModel.opportunity_id.in_(opps))),
        ("opportunities", delete(m.Opportunity).where(m.Opportunity.id.in_(opps))),
        (
            "video_annotations_de_videos_demo",
            delete(m.VideoAnnotation).where(m.VideoAnnotation.video_id.in_(ids["videos"])),
        ),
        ("videos", delete(m.Video).where(m.Video.id.in_(ids["videos"]))),
        ("channels", delete(m.Channel).where(m.Channel.id.in_(ids["channels"] - channel_keepers))),
        ("niches", delete(m.Niche).where(m.Niche.id.in_(ids["niches"]))),
        ("formats", delete(m.Format).where(m.Format.id.in_(ids["formats"]))),
        ("run_tasks", delete(m.RunTask).where(m.RunTask.run_id == run_id)),
        ("audit_events", delete(m.AuditEvent).where(m.AuditEvent.run_id == run_id)),
        ("research_runs", delete(m.ResearchRun).where(m.ResearchRun.id == run_id)),
    ]
    deleted: dict[str, int] = {}
    for name, statement in steps:
        result = session.execute(statement)
        deleted[name] = int(getattr(result, "rowcount", 0) or 0)
    return deleted


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Quita los datos de la demo de la base.")
    parser.add_argument(
        "--apply", action="store_true", help="borra de verdad (sin esto, solo simula)"
    )
    args = parser.parse_args(argv)
    data = load_fixture()
    with get_session_factory()() as session, session.begin():
        ids = fixture_ids(data)
        stuck = blockers(session, ids)
        if stuck:
            print("DETENIDO: estas oportunidades reales usan un nicho o formato de la demo:")
            for opportunity_id in stuck:
                print(f"  - {opportunity_id}")
            print("Cámbielas a un nicho y formato propios antes de quitar la demo.")
            return 2
        summary = plan(session, data)
        print("Se borraría:" if not args.apply else "Se borra:")
        for table, count in summary["borrar"].items():
            print(f"  {table:24} {count}")
        print("Se conserva (lo real):")
        for table, count in summary["conservar"].items():
            print(f"  {table:24} {count}")
        if not args.apply:
            print("\nSimulación: no se borró nada. Use --apply para borrar.")
            return 0
        deleted = apply(session, data)
    log.info("demo_purged", deleted=deleted)
    print("\nListo. Filas borradas por paso:", {k: v for k, v in deleted.items() if v})
    return 0


if __name__ == "__main__":
    sys.exit(main())
