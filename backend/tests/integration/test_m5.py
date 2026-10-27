"""M5: trabajos programados, alertas y seguimiento de oportunidades."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ProblemError
from app.db import models as m
from app.db.session import get_session_factory
from app.jobs import worker
from app.jobs.handlers import HandlerContext
from app.services import alerts_service, evaluation_service, scheduler_service, vidiq_service
from app.services import watchlist_service as wl

OPP = "syn-opp-01"
NOW = datetime.now(UTC)


def _count(session: Session, model: type[m.Base], *conditions: Any) -> int:
    return int(session.scalar(select(func.count()).select_from(model).where(*conditions)) or 0)


def _alerts(session: Session) -> list[m.Alert]:
    session.expire_all()
    return list(session.scalars(select(m.Alert).order_by(m.Alert.created_at)))


# --- trabajos programados ---------------------------------------------------------------------


def test_defaults_create_the_four_jobs_enabled_and_due(seeded_db: Session) -> None:
    scheduler_service.ensure_defaults(seeded_db, NOW)
    jobs = {j.job_type: j for j in seeded_db.scalars(select(m.ScheduledJob))}
    assert set(jobs) == {"retention_purge", "alerts_check", "watchlist_recheck", "db_backup"}
    assert all(j.enabled and j.next_run_at <= NOW for j in jobs.values())
    scheduler_service.ensure_defaults(seeded_db, NOW)  # idempotente
    assert _count(seeded_db, m.ScheduledJob) == 4


def test_tick_enqueues_due_jobs_as_runs_and_reschedules_them(seeded_db: Session) -> None:
    enqueued = scheduler_service.tick(seeded_db, get_settings(), NOW)
    assert sorted(enqueued) == [
        "alerts_check",
        "db_backup",
        "retention_purge",
        "watchlist_recheck",
    ]
    kinds = {r.kind for r in seeded_db.scalars(select(m.ResearchRun)) if r.status == "QUEUED"}
    assert {"purge", "alerts", "watchlist"} <= kinds
    purge = seeded_db.get(m.ScheduledJob, "retention_purge")
    assert purge is not None
    assert purge.next_run_at == NOW + timedelta(hours=24)
    assert purge.last_run_id is not None
    events = seeded_db.scalars(
        select(m.AuditEvent).where(m.AuditEvent.event_type == "RUN_REQUESTED")
    ).all()
    assert {e.actor for e in events} == {"scheduler"}


def test_a_second_tick_does_not_enqueue_again(seeded_db: Session) -> None:
    scheduler_service.tick(seeded_db, get_settings(), NOW)
    seeded_db.commit()
    with get_session_factory()() as other:  # otro worker
        assert scheduler_service.tick(other, get_settings(), NOW) == []
        other.rollback()
    assert scheduler_service.tick(seeded_db, get_settings(), NOW + timedelta(minutes=5)) == []


def test_after_downtime_a_job_runs_once_not_once_per_missed_interval(seeded_db: Session) -> None:
    scheduler_service.ensure_defaults(seeded_db, NOW)
    long_ago = NOW - timedelta(days=10)
    for job in seeded_db.scalars(select(m.ScheduledJob)):
        job.next_run_at = long_ago
    assert len(scheduler_service.tick(seeded_db, get_settings(), NOW)) == 4
    assert _count(seeded_db, m.ResearchRun, m.ResearchRun.kind == "purge") == 1


def test_disabled_jobs_and_overlapping_runs_are_skipped(seeded_db: Session) -> None:
    scheduler_service.update_job(
        seeded_db, "alerts_check", enabled=False, interval_hours=None, by="t", now=NOW
    )
    assert "alerts_check" not in scheduler_service.tick(seeded_db, get_settings(), NOW)
    # La purga ya está en cola: la siguiente vuelta no la duplica (contrapresión).
    later = NOW + timedelta(hours=25)
    scheduler_service.tick(seeded_db, get_settings(), later)
    assert _count(seeded_db, m.ResearchRun, m.ResearchRun.kind == "purge") == 1
    purge = seeded_db.get(m.ScheduledJob, "retention_purge")
    assert purge is not None and purge.next_run_at == later + timedelta(hours=24)


def test_job_settings_are_validated_and_audited(seeded_db: Session) -> None:
    with pytest.raises(ProblemError) as bad:
        scheduler_service.update_job(
            seeded_db, "retention_purge", enabled=None, interval_hours=0, by="t", now=NOW
        )
    assert bad.value.code == "INVALID_INTERVAL"
    with pytest.raises(ProblemError) as unknown:
        scheduler_service.update_job(
            seeded_db, "no-existe", enabled=True, interval_hours=1, by="t", now=NOW
        )
    assert unknown.value.status == 404
    view = scheduler_service.update_job(
        seeded_db, "retention_purge", enabled=None, interval_hours=12, by="local_owner", now=NOW
    )
    assert view["interval_hours"] == 12
    assert _count(seeded_db, m.AuditEvent, m.AuditEvent.event_type == "SCHEDULED_JOB_CHANGED") == 1


def test_the_worker_tick_runs_the_jobs_end_to_end(seeded_db: Session) -> None:
    seeded_db.commit()
    factory = get_session_factory()
    enqueued = worker.run_scheduler_tick(factory, get_settings(), NOW)
    assert len(enqueued) == 4
    ctx = HandlerContext(settings=get_settings(), make_source=lambda: None)  # type: ignore[arg-type,return-value]
    while worker.process_once(factory, ctx):
        pass
    seeded_db.expire_all()
    runs = seeded_db.scalars(
        select(m.ResearchRun).where(
            m.ResearchRun.kind.in_(("purge", "alerts", "watchlist", "backup"))
        )
    ).all()
    assert len(runs) == 4 and {r.status for r in runs} == {"COMPLETED"}
    assert _count(seeded_db, m.AuditEvent, m.AuditEvent.event_type == "RETENTION_PURGE") == 1


def test_a_failing_tick_never_stops_the_worker(
    seeded_db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_a: Any, **_k: Any) -> list[str]:
        raise RuntimeError("falla")

    monkeypatch.setattr(scheduler_service, "tick", boom)
    assert worker.run_scheduler_tick(get_session_factory(), get_settings(), NOW) == []


def test_jobs_api_lists_updates_and_runs_now(client: TestClient) -> None:
    jobs = client.get("/api/v1/scheduler/jobs").json()
    assert [j["job_type"] for j in jobs] == [
        "retention_purge",
        "alerts_check",
        "watchlist_recheck",
        "db_backup",
    ]
    patched = client.patch(
        "/api/v1/scheduler/jobs/alerts_check", json={"enabled": False, "interval_hours": 3}
    ).json()
    assert (patched["enabled"], patched["interval_hours"]) == (False, 3)
    assert (
        client.patch("/api/v1/scheduler/jobs/alerts_check", json={"interval_hours": 0}).status_code
        == 422
    )
    assert (
        client.patch("/api/v1/scheduler/jobs/no-existe", json={"enabled": True}).status_code == 404
    )
    first = client.post("/api/v1/scheduler/jobs/retention_purge/run")
    assert first.status_code == 202
    again = client.post("/api/v1/scheduler/jobs/retention_purge/run")
    assert (again.status_code, again.json()["code"]) == (409, "JOB_ALREADY_RUNNING")
    listed = {j["job_type"]: j for j in client.get("/api/v1/scheduler/jobs").json()}
    assert listed["retention_purge"]["last_status"] == "QUEUED"


# --- alertas ----------------------------------------------------------------------------------


def test_nothing_to_report_means_no_alerts(seeded_db: Session) -> None:
    counts = alerts_service.check_system(seeded_db, get_settings(), NOW)
    assert counts == {"quota": 0, "stale": 0, "policy": 0, "source": 0, "backup": 0}
    assert _alerts(seeded_db) == []


def _use_vidiq_credits(session: Session, units: int) -> None:
    session.add(
        m.ProviderUsage(
            id=str(uuid4()),
            run_id=None,
            provider=vidiq_service.PROVIDER,
            endpoint="test",
            quota_bucket=vidiq_service.QUOTA_BUCKET,
            units=units,
            started_at=NOW,
            status="OK",
        )
    )
    session.flush()


def test_quota_warning_fires_at_80_percent_and_again_when_exhausted(seeded_db: Session) -> None:
    _use_vidiq_credits(seeded_db, 150)  # 150 de 200: 75 %, todavía no
    assert alerts_service.check_system(seeded_db, get_settings(), NOW)["quota"] == 0
    _use_vidiq_credits(seeded_db, 15)  # 165: 82 %
    assert alerts_service.check_system(seeded_db, get_settings(), NOW)["quota"] == 1
    assert alerts_service.check_system(seeded_db, get_settings(), NOW)["quota"] == 0  # sin repetir
    _use_vidiq_credits(seeded_db, 40)  # 205: agotada
    assert alerts_service.check_system(seeded_db, get_settings(), NOW)["quota"] == 1
    severities = [a.severity for a in _alerts(seeded_db)]
    assert severities == ["WARNING", "CRITICAL"]
    assert "vidIQ" in _alerts(seeded_db)[0].message


def test_stale_data_alert_counts_only_what_expires_soon(seeded_db: Session) -> None:
    video = seeded_db.scalars(select(m.Video)).first()
    assert video is not None
    video.owner_authorized = False
    video.retention_deadline = NOW + timedelta(days=30)
    assert alerts_service.check_system(seeded_db, get_settings(), NOW)["stale"] == 0
    video.retention_deadline = NOW + timedelta(days=2)
    assert alerts_service.check_system(seeded_db, get_settings(), NOW)["stale"] == 1
    assert alerts_service.check_system(seeded_db, get_settings(), NOW)["stale"] == 0
    assert _alerts(seeded_db)[0].details_json["videos"] == 1


def _approval(session: Session, expires: datetime) -> m.PolicyApproval:
    approval = m.PolicyApproval(
        id=str(uuid4()),
        provider="hasdata",
        capability="google_trends",
        scope="prueba",
        status="ACTIVE",
        effective_at=NOW - timedelta(days=100),
        expires_at=expires,
    )
    session.add(approval)
    session.flush()
    return approval


def test_policy_alerts_warn_before_and_after_expiry(seeded_db: Session) -> None:
    far = _approval(seeded_db, NOW + timedelta(days=90))
    assert alerts_service.check_system(seeded_db, get_settings(), NOW)["policy"] == 0
    far.expires_at = NOW + timedelta(days=10)
    assert alerts_service.check_system(seeded_db, get_settings(), NOW)["policy"] == 1
    far.expires_at = NOW - timedelta(days=1)
    assert alerts_service.check_system(seeded_db, get_settings(), NOW)["policy"] == 1
    assert [a.severity for a in _alerts(seeded_db)] == ["WARNING", "CRITICAL"]
    assert "bloqueada" in _alerts(seeded_db)[1].message


def test_credential_rejections_raise_a_source_alert_without_secrets(seeded_db: Session) -> None:
    seeded_db.add(
        m.ResearchRun(
            id=str(uuid4()),
            kind="demand",
            status="FAILED",
            params_json={},
            algorithm_version="t",
            policy_mode="restricted",
            errors_json=[
                {"code": "AUTH_ERROR", "detail": "vidiq: credencial rechazada (HTTP 401)"}
            ],
            coverage_json={},
            budget_json={},
            created_at=NOW,
        )
    )
    seeded_db.flush()
    assert alerts_service.check_system(seeded_db, get_settings(), NOW)["source"] == 1
    alert = _alerts(seeded_db)[0]
    assert alert.severity == "CRITICAL" and "credencial rechazada" in alert.message
    assert alerts_service.check_system(seeded_db, get_settings(), NOW)["source"] == 0


def test_alerts_api_lists_and_acknowledges(client: TestClient, seeded_db: Session) -> None:
    _use_vidiq_credits(seeded_db, 210)
    alerts_service.check_system(seeded_db, get_settings(), NOW)
    seeded_db.commit()
    body = client.get("/api/v1/alerts").json()
    assert (body["open"], body["critical"]) == (1, 1)
    alert_id = body["items"][0]["id"]
    assert client.post(f"/api/v1/alerts/{alert_id}/acknowledge").json()["acknowledged_at"]
    assert client.get("/api/v1/alerts").json()["open"] == 0
    assert len(client.get("/api/v1/alerts?include_acknowledged=true").json()["items"]) == 1
    assert client.post("/api/v1/alerts/no-existe/acknowledge").status_code == 404
    assert client.post("/api/v1/alerts/acknowledge-all").json() == {"acknowledged": 0}


# --- seguimiento ------------------------------------------------------------------------------


def _watch(session: Session, **over: Any) -> m.Watchlist:
    args: dict[str, Any] = {
        "priority": "MEDIUM",
        "notes": "idea para probar",
        "review_days": 7,
        "actor": "local_owner",
        "now": NOW,
    }
    return wl.add(session, OPP, **{**args, **over})


def test_adding_takes_a_snapshot_and_records_the_decision(seeded_db: Session) -> None:
    entry = _watch(seeded_db)
    assert entry.next_review_at == NOW + timedelta(days=7)
    assert entry.snapshot_json["confidence"]
    action = seeded_db.scalars(select(m.ReviewAction)).one()
    assert (action.action, action.reason, action.actor) == (
        "WATCH",
        "idea para probar",
        "local_owner",
    )


def test_watch_rules(seeded_db: Session) -> None:
    with pytest.raises(ProblemError) as missing:
        wl.add(
            seeded_db, "no-existe", priority="LOW", notes=None, review_days=7, actor="t", now=NOW
        )
    assert missing.value.status == 404
    with pytest.raises(ProblemError) as bad:
        _watch(seeded_db, priority="URGENTE")
    assert bad.value.code == "INVALID_PRIORITY"
    _watch(seeded_db)
    with pytest.raises(ProblemError) as twice:
        _watch(seeded_db)
    assert twice.value.status == 409


def test_update_keeps_the_pilot_plan_the_owner_wrote(seeded_db: Session) -> None:
    _watch(seeded_db)
    plan = {
        "hypothesis": "Funciona en español",
        "proposed_videos": ["uno", "dos"],
        "success_metrics": "CTR",
    }
    entry = wl.update(
        seeded_db,
        OPP,
        priority="HIGH",
        notes="nuevas notas",
        next_review_at=None,
        pilot_plan=plan,
        actor="local_owner",
        now=NOW,
    )
    assert (entry.priority, entry.notes, entry.pilot_plan_json) == ("HIGH", "nuevas notas", plan)
    assert "result" not in str(entry.pilot_plan_json).lower()  # no hay resultados inventados


def test_removing_requires_a_reason_and_keeps_the_history(seeded_db: Session) -> None:
    _watch(seeded_db)
    with pytest.raises(ProblemError) as short:
        wl.remove(seeded_db, OPP, reason="no", actor="t", now=NOW)
    assert short.value.code == "REASON_REQUIRED"
    wl.remove(seeded_db, OPP, reason="Ya hay demasiada competencia", actor="local_owner", now=NOW)
    assert _count(seeded_db, m.Watchlist) == 0
    actions = [
        a.action
        for a in seeded_db.scalars(select(m.ReviewAction).order_by(m.ReviewAction.created_at))
    ]
    assert actions == ["WATCH", "UNWATCH"]
    _watch(seeded_db)  # se puede volver a seguir
    with pytest.raises(ProblemError) as gone:
        wl.remove(seeded_db, "syn-opp-02", reason="motivo válido", actor="t", now=NOW)
    assert gone.value.code == "NOT_IN_WATCHLIST"


def _improve(session: Session, *, confidence: str = "MEDIUM", **spanish: Any) -> None:
    previous = evaluation_service.latest_evaluation(session, OPP)
    assert previous is not None
    evaluation_service.append_evaluation(
        session,
        OPP,
        now=NOW + timedelta(days=1),
        source="CALCULATED",
        spanish={**previous.spanish_json, **spanish},
        confidence=confidence,
    )


def test_changes_are_listed_against_the_snapshot_and_alerts_are_not_repeated(
    seeded_db: Session,
) -> None:
    previous = evaluation_service.latest_evaluation(seeded_db, OPP)
    assert previous is not None
    before_signals = (previous.spanish_json.get("demand_signals") or {}).get(
        "independent_signals"
    ) or 0
    _watch(seeded_db, now=NOW)
    seeded_db.commit()
    quiet = wl.recheck(seeded_db, get_settings(), NOW)
    assert quiet == {"reviewed": 1, "alerts_created": 0}  # nada cambió: nada que avisar

    _improve(
        seeded_db,
        confidence="HIGH" if previous.confidence != "HIGH" else "MEDIUM",
        demand_signals={"independent_signals": before_signals + 1},
    )
    view = wl.view(seeded_db, OPP, NOW + timedelta(days=1))
    assert {"independent_signals", "confidence"} <= {c["key"] for c in view["changes"]}

    first = wl.recheck(seeded_db, get_settings(), NOW + timedelta(days=1))
    assert first["alerts_created"] >= 1
    types = {a.alert_type for a in _alerts(seeded_db)}
    assert "SPANISH_DEMAND_SIGNAL" in types
    assert wl.recheck(seeded_db, get_settings(), NOW + timedelta(days=2))["alerts_created"] == 0


def test_a_confidence_downgrade_is_not_announced_as_an_upgrade(seeded_db: Session) -> None:
    _improve(seeded_db, confidence="HIGH")
    _watch(seeded_db)
    _improve(seeded_db, confidence="LOW")
    wl.recheck(seeded_db, get_settings(), NOW + timedelta(days=2))
    assert "OPPORTUNITY_CONFIDENCE_UPGRADE" not in {a.alert_type for a in _alerts(seeded_db)}


def test_competition_increase_needs_a_reliable_comparison(seeded_db: Session) -> None:
    # Con poca revisión humana, más «exactos» no es una comparación confiable: no se avisa.
    _improve(seeded_db, exact_matches=2, reviewed_matches=2, es_verified_videos=10)
    _watch(seeded_db)
    _improve(seeded_db, exact_matches=5, reviewed_matches=3, es_verified_videos=10)
    wl.recheck(seeded_db, get_settings(), NOW + timedelta(days=2))
    assert "SPANISH_COMPETITION_INCREASE" not in {a.alert_type for a in _alerts(seeded_db)}

    wl.remove(seeded_db, OPP, reason="reiniciar prueba", actor="t", now=NOW)
    _improve(seeded_db, exact_matches=2, reviewed_matches=9, es_verified_videos=10)
    _watch(seeded_db)
    _improve(seeded_db, exact_matches=4, reviewed_matches=10, es_verified_videos=10)
    wl.recheck(seeded_db, get_settings(), NOW + timedelta(days=3))
    assert "SPANISH_COMPETITION_INCREASE" in {a.alert_type for a in _alerts(seeded_db)}


def test_marking_reviewed_clears_the_changes_and_schedules_the_next_review(
    seeded_db: Session,
) -> None:
    _watch(seeded_db)
    _improve(seeded_db, confidence="HIGH", exact_matches=7)
    later = NOW + timedelta(days=3)
    assert wl.view(seeded_db, OPP, later)["changes"]
    entry = wl.mark_reviewed(seeded_db, OPP, review_days=14, actor="local_owner", now=later)
    assert entry.next_review_at == later + timedelta(days=14)
    assert wl.view(seeded_db, OPP, later)["changes"] == []
    assert (
        seeded_db.scalars(
            select(m.ReviewAction.action).order_by(m.ReviewAction.created_at.desc())
        ).first()
        == "REVIEWED"
    )


def test_list_orders_by_priority_and_flags_overdue_reviews(seeded_db: Session) -> None:
    wl.add(seeded_db, "syn-opp-02", priority="LOW", notes=None, review_days=1, actor="t", now=NOW)
    wl.add(seeded_db, "syn-opp-03", priority="HIGH", notes=None, review_days=30, actor="t", now=NOW)
    _watch(seeded_db, priority="MEDIUM", review_days=7)
    rows = wl.list_watchlist(seeded_db, NOW + timedelta(days=2))
    assert [r["priority"] for r in rows] == ["HIGH", "MEDIUM", "LOW"]
    assert {r["opportunity_id"]: r["review_overdue"] for r in rows}["syn-opp-02"] is True
    assert rows[0]["niche"] and rows[0]["format"]


def test_watchlist_api_round_trip(client: TestClient) -> None:
    created = client.post(
        f"/api/v1/opportunities/{OPP}/watch", json={"priority": "HIGH", "notes": "n"}
    )
    assert created.status_code == 201 and created.json()["priority"] == "HIGH"
    assert client.post(f"/api/v1/opportunities/{OPP}/watch", json={}).status_code == 409
    assert client.post("/api/v1/opportunities/no-existe/watch", json={}).status_code == 404
    plan = {"hypothesis": "h", "proposed_videos": ["a", "b", "c"], "success_metrics": "m"}
    patched = client.patch(f"/api/v1/watchlist/{OPP}", json={"pilot_plan": plan, "notes": "otra"})
    assert patched.json()["pilot_plan"]["proposed_videos"] == ["a", "b", "c"]
    too_many = {"proposed_videos": ["1", "2", "3", "4", "5", "6"]}
    assert (
        client.patch(f"/api/v1/watchlist/{OPP}", json={"pilot_plan": too_many}).status_code == 422
    )
    assert client.patch(f"/api/v1/watchlist/{OPP}", json={"priority": "X"}).status_code == 422
    assert [w["opportunity_id"] for w in client.get("/api/v1/watchlist").json()] == [OPP]
    assert (
        client.post(f"/api/v1/watchlist/{OPP}/reviewed", json={"review_days": 3}).status_code == 200
    )
    assert client.post(f"/api/v1/watchlist/{OPP}/remove", json={"reason": "x"}).status_code == 422
    assert (
        client.post(f"/api/v1/watchlist/{OPP}/remove", json={"reason": "ya no aplica"}).status_code
        == 200
    )
    assert client.get("/api/v1/watchlist").json() == []
    assert client.patch(f"/api/v1/watchlist/{OPP}", json={"notes": "x"}).status_code == 404
