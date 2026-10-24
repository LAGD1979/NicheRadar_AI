"""Carga idempotente del dataset sintético DEMO (synthetic_v1).

Cada registro tiene ID estable, así que `session.merge` actúa como UPSERT: ejecutar el seed
varias veces no duplica filas (T21). No usa red ni claves de API.
"""

import json
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db import models as m
from app.db.session import get_session_factory

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "synthetic_v1.json"

log = structlog.get_logger("seed")


def load_fixture(path: Path = FIXTURE_PATH) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    if data.get("dataset") != "synthetic_v1":
        raise ValueError("Fixture inesperado: se esperaba synthetic_v1.")
    return data


def _parse(key: str, value: Any) -> Any:
    if key.endswith("_at") and isinstance(value, str):
        return datetime.fromisoformat(value)
    return value


def _build(model: type[m.Base], defaults: Mapping[str, Any], item: Mapping[str, Any]) -> Any:
    columns = {column.name for column in model.__table__.columns}
    merged = {**defaults, **item}
    return model(**{k: _parse(k, v) for k, v in merged.items() if k in columns})


def seed_fixture(session: Session, data: dict[str, Any]) -> dict[str, int]:
    defaults: dict[str, Any] = data["defaults"]
    counts: dict[str, int] = {}

    run = data["run"]
    session.merge(
        _build(
            m.ResearchRun,
            {"started_at": None, "finished_at": None},
            run,
        )
    )
    counts["research_runs"] = 1

    for item in data["niches"]:
        session.merge(_build(m.Niche, defaults, item))
    counts["niches"] = len(data["niches"])

    for item in data["formats"]:
        session.merge(_build(m.Format, defaults, item))
    counts["formats"] = len(data["formats"])

    for item in data["channels"]:
        session.merge(_build(m.Channel, defaults, item))
    counts["channels"] = len(data["channels"])

    for item in data["videos"]:
        session.merge(_build(m.Video, defaults, item))
    counts["videos"] = len(data["videos"])

    evidence_count = 0
    evaluation_count = 0
    for raw in data["opportunities"]:
        # Copia: no mutar el fixture, para que una segunda ejecución del seed funcione igual.
        item = dict(raw)
        evaluation = item.pop("evaluation")
        evidence_rows = item.pop("evidence")
        session.merge(_build(m.Opportunity, {"target_lang": "es"}, item))

        # Una oportunidad sin evaluación (p. ej. solo descubierta) no tiene filas de evaluación.
        if evaluation is not None:
            session.merge(
                m.Evaluation(
                    id=evaluation["id"],
                    opportunity_id=item["id"],
                    run_id=defaults["run_id"],
                    evaluation_version=evaluation["evaluation_version"],
                    international_json=evaluation["international"],
                    spanish_json=evaluation["spanish"],
                    feasibility_json=evaluation["feasibility"],
                    scores_json=evaluation["scores"],
                    confidence=evaluation["confidence"],
                    reason_codes_json=evaluation["reason_codes"],
                    recommendation=evaluation["recommendation"],
                    metric_policy_state=evaluation["metric_policy_state"],
                    source_data_type=defaults["source_data_type"],
                    observed_at=datetime.fromisoformat(defaults["observed_at"]),
                )
            )
            evaluation_count += 1

        for row in evidence_rows:
            session.merge(
                _build(
                    m.OpportunityEvidence,
                    {
                        "opportunity_id": item["id"],
                        "observed_at": defaults["observed_at"],
                        "source_data_type": defaults["source_data_type"],
                    },
                    row,
                )
            )
            evidence_count += 1
    counts["opportunities"] = len(data["opportunities"])
    counts["evaluations"] = evaluation_count
    counts["opportunity_evidence"] = evidence_count

    session.merge(
        m.AuditEvent(
            id="syn-audit-seed-01",
            run_id=run["id"],
            actor="system",
            event_type="SYNTHETIC_SEED_LOADED",
            object_type="dataset",
            object_id=data["dataset"],
            details_redacted_json={"counts_expected": counts},
            created_at=datetime.fromisoformat(defaults["observed_at"]),
        )
    )
    return counts


def main() -> None:
    configure_logging(get_settings().log_level)
    data = load_fixture()
    with get_session_factory()() as session, session.begin():
        counts = seed_fixture(session, data)
    log.info("seed_completed", dataset=data["dataset"], counts=counts)


if __name__ == "__main__":
    main()
