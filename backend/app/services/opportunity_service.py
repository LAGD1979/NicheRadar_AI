from typing import Any

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session

from app.api.v1.schemas import (
    CompareItem,
    CompareResponse,
    EvaluationOut,
    EvidenceOut,
    FieldDef,
    FieldValue,
    FormatOut,
    NicheOut,
    OpportunityDetail,
    OpportunityItem,
    ScoreOut,
)
from app.core.config import Settings
from app.core.errors import ProblemError
from app.db import models as m
from app.services.compliance_service import decide

SCORE_KEYS = ("international", "spanish", "feasibility", "integrated")

FILTER_COLUMNS: dict[str, Any] = {
    "status": m.Opportunity.status,
    "video_type": m.Opportunity.video_type,
    "confidence": m.Evaluation.confidence,
    "saturation_es": m.Evaluation.spanish_json["saturation_state"].astext,
    "spanish_demand_state": m.Evaluation.spanish_json["spanish_demand_state"].astext,
    "entry_decision": m.Evaluation.spanish_json["entry_decision"].astext,
    "replication_state": m.Evaluation.international_json["replication_state"].astext,
    "faceless_state": m.Evaluation.feasibility_json["faceless_state"].astext,
    "rights_risk": m.Evaluation.feasibility_json["rights_risk"].astext,
}

SORT_COLUMNS: dict[str, Any] = {
    "name": m.Niche.canonical_name_es,
    "status": m.Opportunity.status,
    "confidence": m.Evaluation.confidence,
    "video_type": m.Opportunity.video_type,
}

# (clave, etiqueta, grupo, ruta en la evaluación; "" = dato de la oportunidad)
COMPARE_FIELDS: list[tuple[str, str, str, str]] = [
    ("niche", "Nicho", "Resumen", ""),
    ("format", "Formato", "Resumen", ""),
    ("video_type", "Tipo de video", "Resumen", ""),
    ("target_lang", "Idioma destino", "Resumen", ""),
    ("status", "Estado", "Resumen", ""),
    ("confidence", "Confianza", "Resumen", "confidence"),
    ("recommendation", "Recomendación", "Decisión", "recommendation"),
    ("gates", "Compuertas que bloquean", "Decisión", "gates"),
    (
        "international.replication_state",
        "Replicación internacional",
        "Internacional",
        "international.replication_state",
    ),
    (
        "international.independent_channels_observed",
        "Canales independientes",
        "Internacional",
        "international.independent_channels_observed",
    ),
    (
        "international.relevant_videos_observed",
        "Videos relevantes",
        "Internacional",
        "international.relevant_videos_observed",
    ),
    ("spanish.saturation_state", "Saturación ES", "Español", "spanish.saturation_state"),
    ("spanish.spanish_demand_state", "Demanda ES", "Español", "spanish.spanish_demand_state"),
    ("spanish.entry_decision", "Decisión de entrada", "Español", "spanish.entry_decision"),
    (
        "spanish.query_coverage_count",
        "Consultas ES ejecutadas",
        "Español",
        "spanish.query_coverage_count",
    ),
    ("feasibility.faceless_state", "Faceless", "Producción", "feasibility.faceless_state"),
    (
        "feasibility.complexity_1_to_5",
        "Complejidad IA (1–5)",
        "Producción",
        "feasibility.complexity_1_to_5",
    ),
    ("feasibility.rights_risk", "Riesgo de derechos", "Producción", "feasibility.rights_risk"),
    (
        "feasibility.human_minutes_per_video",
        "Minutos humanos por video",
        "Producción",
        "feasibility.human_minutes_per_video",
    ),
    (
        "feasibility.usd_per_video_scenarios.low",
        "USD por video (bajo)",
        "Producción",
        "feasibility.usd_per_video_scenarios.low",
    ),
    (
        "feasibility.usd_per_video_scenarios.base",
        "USD por video (base)",
        "Producción",
        "feasibility.usd_per_video_scenarios.base",
    ),
    (
        "feasibility.usd_per_video_scenarios.high",
        "USD por video (alto)",
        "Producción",
        "feasibility.usd_per_video_scenarios.high",
    ),
    ("scores.integrated", "Índice integrado", "Evaluación", "scores.integrated"),
]


def _dig(data: dict[str, Any] | None, path: str) -> Any:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _latest_evaluation_subquery() -> Any:
    ranked = select(
        m.Evaluation.id.label("eval_id"),
        m.Evaluation.opportunity_id.label("opportunity_id"),
        func.row_number()
        .over(
            partition_by=m.Evaluation.opportunity_id,
            order_by=m.Evaluation.evaluation_version.desc(),
        )
        .label("rn"),
    )
    return ranked.subquery("ranked_evaluations")


def opportunity_rows_stmt() -> Select[Any]:
    """Oportunidad + nicho + formato + evaluación vigente (la de mayor versión).

    Las oportunidades sin evaluación siguen apareciendo, con los campos en NULL.
    """
    latest = _latest_evaluation_subquery()
    return (
        select(m.Opportunity, m.Niche, m.Format, m.Evaluation)
        .join(m.Niche, m.Niche.id == m.Opportunity.niche_id)
        .join(m.Format, m.Format.id == m.Opportunity.format_id)
        .outerjoin(
            latest,
            and_(latest.c.opportunity_id == m.Opportunity.id, latest.c.rn == 1),
        )
        .outerjoin(m.Evaluation, m.Evaluation.id == latest.c.eval_id)
    )


def list_opportunities(
    session: Session,
    *,
    page: int,
    page_size: int,
    q: str | None,
    filters: dict[str, str],
    sort: str,
) -> tuple[list[OpportunityItem], int]:
    stmt = opportunity_rows_stmt()
    if q:
        stmt = stmt.where(
            or_(
                m.Niche.canonical_name_es.icontains(q, autoescape=True),
                m.Format.canonical_name_es.icontains(q, autoescape=True),
            )
        )
    for name, value in filters.items():
        stmt = stmt.where(FILTER_COLUMNS[name] == value)

    column = SORT_COLUMNS[sort.removeprefix("-")]
    ordering = column.desc() if sort.startswith("-") else column.asc()

    total = session.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = session.execute(
        stmt.order_by(ordering, m.Opportunity.id).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return [_to_item(opp, niche, fmt, ev) for opp, niche, fmt, ev in rows], int(total or 0)


def parse_sort(sort: str) -> str:
    if sort.removeprefix("-") not in SORT_COLUMNS:
        raise ProblemError(
            422, "INVALID_SORT", "Orden no permitido", f"Valores: {sorted(SORT_COLUMNS)}"
        )
    return sort


def _to_item(
    opp: m.Opportunity, niche: m.Niche, fmt: m.Format, ev: m.Evaluation | None
) -> OpportunityItem:
    spanish = ev.spanish_json if ev else None
    feasibility = ev.feasibility_json if ev else None
    international = ev.international_json if ev else None
    return OpportunityItem(
        id=opp.id,
        recommendation=ev.recommendation if ev else None,
        niche=niche.canonical_name_es,
        format=fmt.canonical_name_es,
        target_lang=opp.target_lang,
        video_type=opp.video_type,
        status=opp.status,
        confidence=ev.confidence if ev else None,
        replication_state=_dig(international, "replication_state"),
        saturation_es=_dig(spanish, "saturation_state"),
        spanish_demand_state=_dig(spanish, "spanish_demand_state"),
        entry_decision=_dig(spanish, "entry_decision"),
        faceless_state=_dig(feasibility, "faceless_state"),
        complexity_1_to_5=_dig(feasibility, "complexity_1_to_5"),
        rights_risk=_dig(feasibility, "rights_risk"),
        observed_at=ev.observed_at if ev else None,
        data_source=ev.source_data_type if ev else "SIN_EVALUACION",
    )


def _restricted_scores(settings: Settings) -> dict[str, ScoreOut]:
    decision = decide("advanced_scores", settings)
    return {
        key: ScoreOut(value=None, state="RESTRICTED", reason=decision.reason) for key in SCORE_KEYS
    }


def get_opportunity_detail(
    session: Session, settings: Settings, opportunity_id: str
) -> OpportunityDetail:
    row = session.execute(opportunity_rows_stmt().where(m.Opportunity.id == opportunity_id)).first()
    if row is None:
        raise ProblemError(404, "OPPORTUNITY_NOT_FOUND", "Oportunidad no encontrada")
    opp, niche, fmt, ev = row
    evaluation = (
        EvaluationOut(
            evaluation_version=ev.evaluation_version,
            confidence=ev.confidence,
            reason_codes=ev.reason_codes_json,
            recommendation=ev.recommendation,
            metric_policy_state=ev.metric_policy_state,
            international=ev.international_json,
            spanish=ev.spanish_json,
            feasibility=ev.feasibility_json,
            scores=_restricted_scores(settings),
            data_source=ev.source_data_type,
            observed_at=ev.observed_at,
            run_id=ev.run_id,
        )
        if ev
        else None
    )
    return OpportunityDetail(
        id=opp.id,
        niche=NicheOut(
            id=niche.id,
            name=niche.canonical_name_es,
            definition=niche.definition,
            exclusions=niche.exclusions_json,
        ),
        format=FormatOut(
            id=fmt.id,
            name=fmt.canonical_name_es,
            story_structure=fmt.story_structure,
            visual_grammar=fmt.visual_grammar,
            audio_grammar=fmt.audio_grammar,
            min_assets=fmt.min_assets,
        ),
        target_lang=opp.target_lang,
        video_type=opp.video_type,
        status=opp.status,
        owner_notes=opp.owner_notes,
        source_languages=opp.source_languages_json,
        evaluation=evaluation,
        evidence=_load_evidence(session, opportunity_id),
    )


def _load_evidence(session: Session, opportunity_id: str) -> list[EvidenceOut]:
    rows = session.scalars(
        select(m.OpportunityEvidence)
        .where(m.OpportunityEvidence.opportunity_id == opportunity_id)
        .order_by(m.OpportunityEvidence.id)
    ).all()
    video_ids = [r.entity_id for r in rows if r.entity_type == "VIDEO"]
    channel_ids = [r.entity_id for r in rows if r.entity_type == "CHANNEL"]
    videos = {
        v.youtube_video_id: v
        for v in session.scalars(select(m.Video).where(m.Video.youtube_video_id.in_(video_ids)))
    }
    channels = {
        c.youtube_channel_id: c
        for c in session.scalars(
            select(m.Channel).where(m.Channel.youtube_channel_id.in_(channel_ids))
        )
    }
    out: list[EvidenceOut] = []
    for r in rows:
        title: str | None = None
        channel_title: str | None = None
        if r.entity_type == "VIDEO" and r.entity_id in videos:
            video = videos[r.entity_id]
            title = video.title
            owner = session.get(m.Channel, video.channel_id)
            channel_title = owner.title_current if owner else None
        elif r.entity_type == "CHANNEL" and r.entity_id in channels:
            channel_title = channels[r.entity_id].title_current
        out.append(
            EvidenceOut(
                id=r.id,
                market=r.market,
                role=r.role,
                entity_type=r.entity_type,
                entity_id=r.entity_id,
                title=title,
                channel_title=channel_title,
                evidence_text=r.evidence_text,
                source=r.source,
                observed_at=r.observed_at,
                support_strength=r.support_strength,
                availability=r.availability,
            )
        )
    return out


def compare(session: Session, settings: Settings, ids: list[str]) -> CompareResponse:
    if len(set(ids)) != len(ids):
        raise ProblemError(
            422, "DUPLICATE_OPPORTUNITY", "Oportunidades repetidas en la comparación"
        )
    decision = decide("advanced_scores", settings)
    fields = [FieldDef(key=k, label=label, group=group) for k, label, group, _ in COMPARE_FIELDS]

    items: list[CompareItem] = []
    for opportunity_id in ids:
        row = session.execute(
            opportunity_rows_stmt().where(m.Opportunity.id == opportunity_id)
        ).first()
        if row is None:
            raise ProblemError(404, "OPPORTUNITY_NOT_FOUND", "Oportunidad no encontrada")
        opp, niche, fmt, ev = row
        summary: dict[str, Any] = {
            "niche": niche.canonical_name_es,
            "format": fmt.canonical_name_es,
            "video_type": opp.video_type,
            "target_lang": opp.target_lang,
            "status": opp.status,
        }
        ev_source = f"{ev.source_data_type} · evaluación v{ev.evaluation_version}" if ev else None
        ev_observed = ev.observed_at if ev else None
        ev_json: dict[str, Any] = (
            {
                "confidence": ev.confidence,
                "recommendation": ev.recommendation,
                "gates": ", ".join(ev.reason_codes_json),
                "international": ev.international_json,
                "spanish": ev.spanish_json,
                "feasibility": ev.feasibility_json,
            }
            if ev
            else {}
        )

        values: dict[str, FieldValue] = {}
        for key, _label, _group, path in COMPARE_FIELDS:
            if key.startswith("scores."):
                values[key] = FieldValue(
                    value=None,
                    state="RESTRICTED",
                    source=ev_source,
                    observed_at=ev_observed,
                    reason=decision.reason,
                )
                continue
            source: str | None
            if key in summary:
                raw = summary[key]
                source = "registro de oportunidad"
            else:
                raw = _dig(ev_json, path)
                source = ev_source
            values[key] = FieldValue(
                value=raw,
                state="AVAILABLE" if raw is not None else "NOT_AVAILABLE",
                source=source,
                observed_at=ev_observed,
                reason=None
                if raw is not None
                else ("Sin evaluación" if ev is None else "Sin dato observado"),
            )
        items.append(
            CompareItem(
                id=opp.id,
                title=f"{niche.canonical_name_es} · {fmt.canonical_name_es}",
                values=values,
            )
        )
    return CompareResponse(fields=fields, items=items)
