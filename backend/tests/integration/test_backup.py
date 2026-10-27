"""Backup local con restauración probada (D-71)."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import models as m
from app.services import alerts_service, backup_service
from app.services.backup_service import BackupError

NOW = datetime(2026, 10, 26, 15, 0, tzinfo=UTC)


def _make(session: Session, folder: Path) -> dict[str, Any]:
    return backup_service.create_backup(session, get_settings(), NOW, directory=folder)


def test_a_backup_is_written_restored_and_verified(seeded_db: Session, tmp_path: Path) -> None:
    manifest = _make(seeded_db, tmp_path)
    assert manifest["verified"] is True, manifest["restore_check"]
    assert manifest["restore_check"]["ok"] is True
    assert manifest["restore_check"]["rows"] == manifest["rows"] > 0
    assert (tmp_path / manifest["file"]).stat().st_size == manifest["size_bytes"] > 0
    stored = json.loads((tmp_path / manifest["file"]).with_suffix(".json").read_text("utf-8"))
    assert stored["sha256"] == manifest["sha256"]
    # El backup no puede contener claves: la base no las guarda, pero tampoco su manifiesto.
    assert "key" not in json.dumps(stored).lower().replace("keyword", "")


def test_the_scratch_database_is_always_dropped(seeded_db: Session, tmp_path: Path) -> None:
    _make(seeded_db, tmp_path)
    left = seeded_db.execute(
        text("SELECT datname FROM pg_database WHERE datname LIKE 'nicheradar_restore_check_%'")
    ).all()
    assert left == []


def test_a_restore_that_does_not_match_the_live_data_is_not_verified(
    seeded_db: Session, tmp_path: Path
) -> None:
    manifest = _make(seeded_db, tmp_path)
    url = backup_service.make_url(get_settings().database_url)
    wrong = {k: v + 5 for k, v in manifest["counts_after"].items()}
    result = backup_service.verify_restore(
        tmp_path / manifest["file"], url, wrong, wrong, manifest["revision"]
    )
    assert result["ok"] is False and result["mismatched"]
    bad_revision = backup_service.verify_restore(
        tmp_path / manifest["file"],
        url,
        manifest["counts_before"],
        manifest["counts_after"],
        "0000_otra",
    )
    assert bad_revision["ok"] is False


def test_verify_file_detects_a_damaged_backup(seeded_db: Session, tmp_path: Path) -> None:
    manifest = _make(seeded_db, tmp_path)
    settings = get_settings()
    good = backup_service.verify_file(seeded_db, settings, manifest["file"], directory=tmp_path)
    assert good["ok"] is True
    with (tmp_path / manifest["file"]).open("ab") as handle:
        handle.write(b"basura")
    bad = backup_service.verify_file(seeded_db, settings, manifest["file"], directory=tmp_path)
    assert bad["ok"] is False and "dañado" in bad["error"]


@pytest.mark.parametrize("name", ["../x.dump", "otro.dump", "nicheradar_a.sql", "/etc/passwd"])
def test_verify_file_rejects_names_outside_the_folder(
    seeded_db: Session, tmp_path: Path, name: str
) -> None:
    with pytest.raises(BackupError) as caught:
        backup_service.verify_file(seeded_db, get_settings(), name, directory=tmp_path)
    assert caught.value.code == "BACKUP_NAME_INVALID"


def test_a_missing_postgres_client_is_reported_not_faked(
    seeded_db: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(backup_service.shutil, "which", lambda _name: None)
    with pytest.raises(BackupError) as caught:
        _make(seeded_db, tmp_path)
    assert caught.value.code == "BACKUP_TOOL_MISSING"
    assert list(tmp_path.iterdir()) == []


# --- caducidad ---------------------------------------------------------------------------------


def test_a_backup_expires_with_its_earliest_third_party_data(seeded_db: Session) -> None:
    settings = get_settings()
    base = backup_service.expiry(seeded_db, settings, NOW)
    video = seeded_db.scalars(select(m.Video)).first()
    assert video is not None
    video.owner_authorized = False
    video.availability = "AVAILABLE"
    video.retention_deadline = NOW + timedelta(days=3)
    seeded_db.flush()
    assert backup_service.expiry(seeded_db, settings, NOW) == NOW + timedelta(days=3)
    video.retention_deadline = NOW + timedelta(days=settings.backup_retention_days + 10)
    seeded_db.flush()
    assert backup_service.expiry(seeded_db, settings, NOW) == min(
        base, NOW + timedelta(days=settings.backup_retention_days)
    )
    video.retention_deadline = NOW - timedelta(days=1)  # ya vencido: no adelanta nada
    seeded_db.flush()
    assert backup_service.expiry(seeded_db, settings, NOW) >= NOW


def test_prune_removes_expired_backups_and_stale_leftovers(tmp_path: Path) -> None:
    def fake(stamp: str, expires: datetime) -> str:
        name = f"nicheradar_{stamp}.dump"
        (tmp_path / name).write_bytes(b"x")
        (tmp_path / name).with_suffix(".json").write_text(
            json.dumps({"file": name, "expires_at": expires.isoformat()}), encoding="utf-8"
        )
        return name

    old = fake("20260101T000000Z", NOW - timedelta(days=1))
    keep = fake("20260102T000000Z", NOW + timedelta(days=1))
    leftover = tmp_path / "nicheradar_20260103T000000Z.dump.part"
    leftover.write_bytes(b"x")
    stale = (NOW - timedelta(hours=3)).timestamp()
    import os

    os.utime(leftover, (stale, stale))
    removed = backup_service.prune(get_settings(), NOW, directory=tmp_path)
    assert removed == [old]
    assert sorted(p.name for p in tmp_path.iterdir()) == [keep, keep.replace(".dump", ".json")]


# --- trabajo programado, alertas y API ----------------------------------------------------------


def test_the_scheduled_job_creates_a_verified_backup(
    seeded_db: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.db.session import get_session_factory
    from app.jobs import worker
    from app.jobs.handlers import HandlerContext

    monkeypatch.setenv("BACKUP_DIR", str(tmp_path))
    get_settings.cache_clear()
    factory = get_session_factory()
    assert "db_backup" in worker.run_scheduler_tick(factory, get_settings(), NOW)
    ctx = HandlerContext(settings=get_settings(), make_source=lambda: None)  # type: ignore[arg-type,return-value]
    while worker.process_once(factory, ctx):
        pass
    seeded_db.expire_all()
    run = seeded_db.scalars(select(m.ResearchRun).where(m.ResearchRun.kind == "backup")).one()
    assert run.status == "COMPLETED"
    assert run.coverage_json["restore_ok"] is True
    assert len(list(tmp_path.glob("nicheradar_*.dump"))) == 1
    get_settings.cache_clear()


def _backup_run(session: Session, status: str, *, finished: datetime, detail: str = "") -> str:
    run_id = str(uuid4())
    session.add(
        m.ResearchRun(
            id=run_id,
            kind="backup",
            status=status,
            params_json={},
            algorithm_version="t",
            policy_mode="restricted",
            errors_json=[{"code": "BACKUP_TOOL_FAILED", "detail": detail}] if detail else [],
            coverage_json={},
            budget_json={},
            created_at=finished,
            finished_at=finished,
        )
    )
    session.flush()
    return run_id


def test_a_failed_backup_raises_a_critical_alert_once(seeded_db: Session) -> None:
    from app.services import scheduler_service

    scheduler_service.ensure_defaults(seeded_db, NOW)
    _backup_run(seeded_db, "FAILED", finished=NOW, detail="pg_dump falló: sin espacio")
    assert alerts_service.check_system(seeded_db, get_settings(), NOW)["backup"] == 1
    assert alerts_service.check_system(seeded_db, get_settings(), NOW)["backup"] == 0
    alert = seeded_db.scalars(select(m.Alert).where(m.Alert.alert_type == "BACKUP_FAILED")).one()
    assert alert.severity == "CRITICAL" and "sin espacio" in alert.message


def test_a_backup_that_is_too_old_raises_a_stale_alert(seeded_db: Session) -> None:
    from app.services import scheduler_service

    scheduler_service.ensure_defaults(seeded_db, NOW)
    _backup_run(seeded_db, "COMPLETED", finished=NOW - timedelta(hours=30))
    assert alerts_service.check_system(seeded_db, get_settings(), NOW)["backup"] == 0
    _backup_run(seeded_db, "COMPLETED", finished=NOW - timedelta(hours=60))
    assert alerts_service.check_system(seeded_db, get_settings(), NOW)["backup"] == 0
    seeded_db.execute(m.ResearchRun.__table__.delete().where(m.ResearchRun.kind == "backup"))
    _backup_run(seeded_db, "COMPLETED", finished=NOW - timedelta(hours=60))
    assert alerts_service.check_system(seeded_db, get_settings(), NOW)["backup"] == 1


def test_no_backup_alert_when_the_job_is_disabled(seeded_db: Session) -> None:
    from app.services import scheduler_service

    scheduler_service.update_job(
        seeded_db, "db_backup", enabled=False, interval_hours=None, by="t", now=NOW
    )
    _backup_run(seeded_db, "FAILED", finished=NOW, detail="x")
    assert alerts_service.check_system(seeded_db, get_settings(), NOW)["backup"] == 0


def test_the_api_lists_backups_from_the_local_folder(
    client: TestClient, seeded_db: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path))
    get_settings.cache_clear()
    empty = client.get("/api/v1/backups").json()
    assert empty["items"] == [] and empty["directory"] == str(tmp_path)
    manifest = backup_service.create_backup(seeded_db, get_settings(), NOW, directory=tmp_path)
    listed = client.get("/api/v1/backups").json()
    assert [i["file"] for i in listed["items"]] == [manifest["file"]]
    assert listed["items"][0]["verified"] is True and listed["items"][0]["present"] is True
    (tmp_path / manifest["file"]).unlink()
    assert client.get("/api/v1/backups").json()["items"][0]["present"] is False
    get_settings.cache_clear()


# --- restauración ------------------------------------------------------------------------------


@pytest.fixture
def scratch_target() -> Any:
    """Base de destino aparte: la restauración nunca pisa la base de pruebas en uso."""
    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url

    name = f"nicheradar_restore_target_{uuid4().hex[:8]}"
    url = make_url(get_settings().database_url)
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    yield name
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    admin.dispose()


def _rows_in(name: str) -> dict[str, int]:
    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url

    engine = create_engine(make_url(get_settings().database_url).set(database=name))
    try:
        return backup_service.table_counts(engine)
    finally:
        engine.dispose()


def test_restore_recreates_the_database_from_a_backup(
    seeded_db: Session, tmp_path: Path, scratch_target: str
) -> None:
    manifest = _make(seeded_db, tmp_path)
    result = backup_service.restore_backup(
        get_settings(), manifest["file"], NOW, directory=tmp_path, database=scratch_target
    )
    assert result["database"] == scratch_target and result["safety_backup"] is None
    # Tras restaurar se purga lo vencido, y la purga deja una auditoría (+1 en audit_events).
    expected = {
        **manifest["counts_after"],
        "audit_events": manifest["counts_after"]["audit_events"] + 1,
    }
    assert _rows_in(scratch_target) == expected and result["rows"] == manifest["rows"]


def test_restore_replaces_existing_content(
    seeded_db: Session, tmp_path: Path, scratch_target: str
) -> None:
    manifest = _make(seeded_db, tmp_path)
    settings = get_settings()
    backup_service.restore_backup(
        settings, manifest["file"], NOW, directory=tmp_path, database=scratch_target
    )
    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url

    engine = create_engine(make_url(settings.database_url).set(database=scratch_target))
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM alerts"))
        conn.execute(text("DELETE FROM provider_usage"))
    engine.dispose()
    backup_service.restore_backup(
        settings, manifest["file"], NOW, directory=tmp_path, database=scratch_target
    )
    again = _rows_in(scratch_target)
    assert again["alerts"] == manifest["counts_after"]["alerts"]
    assert again["provider_usage"] == manifest["counts_after"]["provider_usage"]


def test_restore_makes_a_safety_backup_of_the_current_database_first(
    seeded_db: Session, tmp_path: Path, scratch_target: str
) -> None:
    manifest = _make(seeded_db, tmp_path)
    settings = get_settings()
    backup_service.restore_backup(
        settings, manifest["file"], NOW, directory=tmp_path, database=scratch_target
    )
    # La base «viva» de este caso es la de destino: así se prueba la rama con copia de seguridad
    # sin pisar la base de pruebas.
    url = backup_service.make_url(settings.database_url).set(database=scratch_target)
    live = settings.model_copy(update={"database_url": url.render_as_string(hide_password=False)})
    later = NOW + timedelta(hours=1)
    result = backup_service.restore_backup(live, manifest["file"], later, directory=tmp_path)
    safety = result["safety_backup"]
    assert safety is not None and safety != manifest["file"]
    stored = json.loads((tmp_path / safety).with_suffix(".json").read_text("utf-8"))
    assert stored["verified"] is True  # la copia de seguridad también se restauró de prueba
    assert result["database"] == scratch_target


def test_restore_refuses_damaged_unknown_and_newer_backups(
    seeded_db: Session, tmp_path: Path, scratch_target: str
) -> None:
    settings = get_settings()
    manifest = _make(seeded_db, tmp_path)
    path = tmp_path / manifest["file"]

    manifest_path = path.with_suffix(".json")
    data = json.loads(manifest_path.read_text("utf-8"))
    data["revision"] = "9999_del_futuro"
    manifest_path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(BackupError) as newer:
        backup_service.restore_backup(
            settings, manifest["file"], NOW, directory=tmp_path, database=scratch_target
        )
    assert newer.value.code == "BACKUP_FROM_NEWER_VERSION"

    with pytest.raises(BackupError) as missing:
        backup_service.restore_backup(
            settings, "nicheradar_no_existe.dump", NOW, directory=tmp_path, database=scratch_target
        )
    assert missing.value.code == "BACKUP_NOT_FOUND"

    with path.open("ab") as handle:
        handle.write(b"basura")
    with pytest.raises(BackupError) as damaged:
        backup_service.restore_backup(
            settings, manifest["file"], NOW, directory=tmp_path, database=scratch_target
        )
    assert damaged.value.code == "BACKUP_DAMAGED"
    # Nada se tocó: la base de destino ni siquiera se creó.
    with pytest.raises(Exception):  # noqa: B017, PT011
        _rows_in(scratch_target)


def test_restore_purges_third_party_data_that_expired_meanwhile(
    seeded_db: Session, tmp_path: Path, scratch_target: str
) -> None:
    video = seeded_db.scalars(select(m.Video)).first()
    assert video is not None
    video.owner_authorized = False
    video.availability = "AVAILABLE"
    video.retention_deadline = NOW + timedelta(days=2)
    seeded_db.commit()
    manifest = _make(seeded_db, tmp_path)
    result = backup_service.restore_backup(
        get_settings(),
        manifest["file"],
        NOW + timedelta(days=3),  # el backup ya habría caducado; lo vencido no vuelve a la vida
        directory=tmp_path,
        database=scratch_target,
    )
    assert result["purged_expired"]["videos_expired"] >= 1


def test_the_cli_lists_verifies_and_simulates(
    seeded_db: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from app.ops import backups as cli

    monkeypatch.setenv("BACKUP_DIR", str(tmp_path))
    get_settings.cache_clear()
    assert cli.main(["list"]) == 0
    assert "No hay backups" in capsys.readouterr().out
    manifest = _make(seeded_db, tmp_path)
    assert cli.main(["list"]) == 0 and manifest["file"] in capsys.readouterr().out
    assert cli.main(["verify", manifest["file"]]) == 0
    assert "restaura bien" in capsys.readouterr().out
    assert cli.main(["restore", manifest["file"]]) == 0  # sin --apply no cambia nada
    assert "Simulacro" in capsys.readouterr().out
    assert cli.main(["restore", "../x.dump"]) == 2
    get_settings.cache_clear()
