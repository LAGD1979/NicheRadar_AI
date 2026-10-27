"""Backup local de la base con restauración probada (M5, spec §13).

Cada backup es un `pg_dump` en formato personalizado dentro de una carpeta local (`BACKUP_DIR`,
`./backups` en el equipo, fuera de Git) con un manifiesto JSON al lado. Un backup solo cuenta
como bueno si se **restaura de verdad**: tras el volcado se crea una base temporal, se restaura
ahí y se comparan las filas de cada tabla y la versión de migración con las de la base viva.

Los datos de terceros de YouTube no pueden conservarse más de 29 días (D-63), y un volcado los
copia. Por eso cada backup caduca en `BACKUP_RETENTION_DAYS` o, si antes, cuando vence el primer
dato de terceros que contiene; `prune` borra los caducados. Las claves de API no están en la
base y por tanto tampoco en el backup.
"""

import hashlib
import json
import os
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import Engine, create_engine, func, select, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db import models as m
from app.services import retention_service

PREFIX = "nicheradar_"
DUMP_SUFFIX = ".dump"
MANIFEST_SUFFIX = ".json"
PART_SUFFIX = ".part"
TOOL_TIMEOUT_SECONDS = 900
MAX_ERROR_CHARS = 400


class BackupError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise BackupError(
            "BACKUP_TOOL_MISSING",
            f"No se encontró «{name}» (cliente de PostgreSQL). Reconstruya la imagen de la API.",
        )
    return path


def _run(command: list[str], url: URL) -> None:
    """Ejecuta una herramienta de PostgreSQL. La clave va por entorno, nunca en los argumentos."""
    env = {**os.environ, "PGPASSWORD": url.password or ""}
    try:
        done = subprocess.run(  # noqa: S603 - argumentos fijos, sin shell
            command, capture_output=True, text=True, timeout=TOOL_TIMEOUT_SECONDS, env=env
        )
    except subprocess.TimeoutExpired as exc:
        raise BackupError("BACKUP_TIMEOUT", f"{Path(command[0]).name} tardó demasiado") from exc
    if done.returncode != 0:
        detail = (done.stderr or done.stdout or "").strip()[:MAX_ERROR_CHARS]
        raise BackupError("BACKUP_TOOL_FAILED", f"{Path(command[0]).name} falló: {detail}")


def _conn_args(url: URL, database: str) -> list[str]:
    return [
        "-h",
        url.host or "localhost",
        "-p",
        str(url.port or 5432),
        "-U",
        url.username or "postgres",
        "-d",
        database,
    ]


def table_counts(engine_or_session: Engine | Session) -> dict[str, int]:
    """Filas por tabla del modelo, más la versión de migración (`alembic_version`)."""
    names = [t.name for t in m.Base.metadata.sorted_tables]

    def count(conn: Any, name: str) -> int:
        return int(conn.execute(text(f'SELECT count(*) FROM "{name}"')).scalar_one())

    def read(conn: Any) -> dict[str, int]:
        return {name: count(conn, name) for name in names}

    if isinstance(engine_or_session, Session):
        return read(engine_or_session)
    with engine_or_session.connect() as conn:
        return read(conn)


def _revision(engine_or_session: Engine | Session) -> str | None:
    query = text("SELECT version_num FROM alembic_version")
    if isinstance(engine_or_session, Session):
        return engine_or_session.execute(query).scalar_one_or_none()
    with engine_or_session.connect() as conn:
        return conn.execute(query).scalar_one_or_none()


def third_party_deadline(session: Session) -> datetime | None:
    """Primer vencimiento entre los datos de terceros vigentes (lo que el volcado copia)."""
    deadlines = [
        session.scalar(
            select(func.min(model.retention_deadline)).where(
                model.retention_deadline.is_not(None), *extra
            )
        )
        for model, extra in (
            (m.Video, (m.Video.owner_authorized.is_(False), m.Video.availability != "EXPIRED")),
            (
                m.Channel,
                (m.Channel.owner_authorized.is_(False), m.Channel.subscriber_band != "EXPIRED"),
            ),
            (m.DemandObservation, (m.DemandObservation.availability != "EXPIRED",)),
        )
    ]
    found = [d for d in deadlines if d is not None]
    return min(found) if found else None


def expiry(session: Session, settings: Settings, now: datetime) -> datetime:
    limit = now + timedelta(days=settings.backup_retention_days)
    deadline = third_party_deadline(session)
    if deadline is None:
        return limit
    return max(now, min(limit, deadline))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_restore(
    dump: Path, url: URL, before: dict[str, int], after: dict[str, int], revision: str | None
) -> dict[str, Any]:
    """Restaura el volcado en una base temporal y la compara con la base viva."""
    pg_restore = _tool("pg_restore")
    scratch = f"nicheradar_restore_check_{uuid4().hex[:10]}"
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{scratch}"'))
        _run(
            [pg_restore, "--no-owner", "--exit-on-error", *_conn_args(url, scratch), str(dump)],
            url,
        )
        probe = create_engine(url.set(database=scratch))
        try:
            restored = table_counts(probe)
            restored_revision = _revision(probe)
        finally:
            probe.dispose()
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{scratch}" WITH (FORCE)'))
        admin.dispose()
    # El volcado es una foto consistente; la base viva pudo cambiar un instante antes o después.
    mismatched = {
        name: {"restored": rows, "live_before": before[name], "live_after": after[name]}
        for name, rows in restored.items()
        if not min(before[name], after[name]) <= rows <= max(before[name], after[name])
    }
    ok = not mismatched and restored_revision == revision
    return {
        "ok": ok,
        "tables": len(restored),
        "rows": sum(restored.values()),
        "revision": restored_revision,
        "mismatched": mismatched,
    }


def _write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    part = path.with_suffix(path.suffix + PART_SUFFIX)
    part.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    part.replace(path)


def create_backup(
    session: Session, settings: Settings, now: datetime, *, directory: Path | None = None
) -> dict[str, Any]:
    """Hace el volcado, lo restaura de prueba y deja el manifiesto. Devuelve el manifiesto."""
    folder = directory or Path(settings.backup_dir)
    folder.mkdir(parents=True, exist_ok=True)
    pg_dump = _tool("pg_dump")
    url = make_url(settings.database_url)
    stamp = now.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    dump = folder / f"{PREFIX}{stamp}{DUMP_SUFFIX}"
    part = dump.with_suffix(dump.suffix + PART_SUFFIX)
    manifest_path = dump.with_suffix(MANIFEST_SUFFIX)

    before = table_counts(session)
    revision = _revision(session)
    deadline = expiry(session, settings, now)
    try:
        _run(
            [
                pg_dump,
                "--format=custom",
                "--no-owner",
                *_conn_args(url, str(url.database)),
                "--file",
                str(part),
            ],
            url,
        )
    except BackupError:
        part.unlink(missing_ok=True)
        raise
    part.replace(dump)
    after = table_counts(session)

    manifest: dict[str, Any] = {
        "file": dump.name,
        "created_at": now.isoformat(),
        "expires_at": deadline.isoformat(),
        "size_bytes": dump.stat().st_size,
        "sha256": _sha256(dump),
        "revision": revision,
        "rows": sum(after.values()),
        "counts_before": before,
        "counts_after": after,
        "restore_check": None,
    }
    try:
        manifest["restore_check"] = verify_restore(dump, url, before, after, revision)
    except BackupError as exc:
        manifest["restore_check"] = {"ok": False, "error_code": exc.code, "error": str(exc)}
    manifest["verified"] = bool(manifest["restore_check"]["ok"])
    _write_manifest(manifest_path, manifest)
    return manifest


def _manifests(folder: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path in sorted(folder.glob(f"{PREFIX}*{MANIFEST_SUFFIX}"), reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and "file" in data:
            out.append(data)
    return out


def list_backups(settings: Settings, *, directory: Path | None = None) -> list[dict[str, Any]]:
    """Backups conocidos, del más nuevo al más viejo. Marca los que perdieron su archivo."""
    folder = directory or Path(settings.backup_dir)
    if not folder.is_dir():
        return []
    rows = []
    for manifest in _manifests(folder):
        present = (folder / str(manifest["file"])).is_file()
        rows.append({**manifest, "present": present})
    return rows


def verify_file(
    session: Session, settings: Settings, name: str, *, directory: Path | None = None
) -> dict[str, Any]:
    """Comprueba un backup existente: el archivo íntegro (sha256) y que restaura."""
    folder = directory or Path(settings.backup_dir)
    try:
        dump, manifest = _load(folder, name)
    except BackupError as exc:
        if exc.code == "BACKUP_DAMAGED":
            return {"ok": False, "error": str(exc)}
        raise
    url = make_url(settings.database_url)
    return verify_restore(
        dump, url, manifest["counts_before"], manifest["counts_after"], manifest.get("revision")
    )


def _load(folder: Path, name: str) -> tuple[Path, dict[str, Any]]:
    """Archivo y manifiesto de un backup, con el nombre validado y la huella comprobada."""
    if Path(name).name != name or not name.startswith(PREFIX) or not name.endswith(DUMP_SUFFIX):
        raise BackupError("BACKUP_NAME_INVALID", "Nombre de backup no válido")
    dump = folder / name
    manifest_path = dump.with_suffix(MANIFEST_SUFFIX)
    if not dump.is_file() or not manifest_path.is_file():
        raise BackupError("BACKUP_NOT_FOUND", "No existe ese backup")
    manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    if _sha256(dump) != manifest.get("sha256"):
        raise BackupError("BACKUP_DAMAGED", "El archivo no coincide con su huella: está dañado.")
    return dump, manifest


def _known_revisions() -> set[str]:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(Config("alembic.ini"))
    return {rev.revision for rev in script.walk_revisions()}


def restore_backup(
    settings: Settings,
    name: str,
    now: datetime,
    *,
    directory: Path | None = None,
    database: str | None = None,
    safety_backup: bool = True,
) -> dict[str, Any]:
    """Reemplaza la base por el contenido de un backup. **Destructivo** sobre la base destino.

    Antes de tocar nada: comprueba la huella, que la versión de migración sea conocida por este
    código y que el backup restaure de verdad en una base temporal. Después hace un backup de
    seguridad de la base actual y recién entonces la recrea. Quien llama debe haber detenido la
    API y el worker. Terminada la restauración se purgan los datos de terceros vencidos.
    """
    folder = directory or Path(settings.backup_dir)
    dump, manifest = _load(folder, name)
    revision = manifest.get("revision")
    if revision is not None and revision not in _known_revisions():
        raise BackupError(
            "BACKUP_FROM_NEWER_VERSION",
            f"El backup es de una versión más nueva ({revision}): actualice la aplicación antes.",
        )
    url = make_url(settings.database_url)
    target = database or str(url.database)
    check = verify_restore(dump, url, manifest["counts_before"], manifest["counts_after"], revision)
    if not check["ok"]:
        raise BackupError(
            "BACKUP_NOT_RESTORABLE", "El backup no restaura bien; la base actual no se tocó."
        )

    safety: str | None = None
    if safety_backup and target == url.database:
        live = create_engine(url)
        try:
            with Session(live) as session:
                made = create_backup(session, settings, now, directory=folder)
        finally:
            live.dispose()
        if not made["verified"]:
            raise BackupError(
                "SAFETY_BACKUP_FAILED",
                "No se pudo hacer un backup de seguridad verificado; la base actual no se tocó.",
            )
        safety = str(made["file"])

    pg_restore = _tool("pg_restore")
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{target}" WITH (FORCE)'))
            conn.execute(text(f'CREATE DATABASE "{target}"'))
    finally:
        admin.dispose()
    _run([pg_restore, "--no-owner", "--exit-on-error", *_conn_args(url, target), str(dump)], url)

    engine = create_engine(url.set(database=target))
    try:
        counts = table_counts(engine)
        with Session(engine) as session:
            purged = retention_service.purge_expired(session, now)
            session.commit()
    finally:
        engine.dispose()
    return {
        "restored_from": name,
        "safety_backup": safety,
        "database": target,
        "rows": sum(counts.values()),
        "purged_expired": purged,
    }


def prune(settings: Settings, now: datetime, *, directory: Path | None = None) -> list[str]:
    """Borra los backups caducados y los restos de volcados interrumpidos."""
    folder = directory or Path(settings.backup_dir)
    if not folder.is_dir():
        return []
    removed: list[str] = []
    for manifest in _manifests(folder):
        try:
            expires = datetime.fromisoformat(str(manifest["expires_at"]))
        except (KeyError, ValueError):
            continue
        if expires <= now:
            name = str(manifest["file"])
            (folder / name).unlink(missing_ok=True)
            (folder / name).with_suffix(MANIFEST_SUFFIX).unlink(missing_ok=True)
            removed.append(name)
    for leftover in folder.glob(f"{PREFIX}*{PART_SUFFIX}"):
        if datetime.fromtimestamp(leftover.stat().st_mtime, UTC) < now - timedelta(hours=1):
            leftover.unlink(missing_ok=True)
    return removed
