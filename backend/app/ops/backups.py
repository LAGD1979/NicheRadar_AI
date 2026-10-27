"""Línea de comandos de los backups locales (D-71).

  python -m app.ops.backups list                      # backups de la carpeta local
  python -m app.ops.backups verify NOMBRE.dump        # huella + restauración de prueba
  python -m app.ops.backups restore NOMBRE.dump       # simulacro: verifica y no toca nada
  python -m app.ops.backups restore NOMBRE.dump --apply
                                                      # REEMPLAZA la base por el backup

`--apply` es destructivo: antes hace un backup de seguridad de la base actual y exige que la
API y el worker estén detenidos. Lo normal es usar `scripts/restore.ps1`, que se ocupa de eso.
"""

import argparse
import sys
from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services import backup_service
from app.services.backup_service import BackupError


def _list() -> int:
    items = backup_service.list_backups(get_settings())
    if not items:
        print("No hay backups en la carpeta.")
    for item in items:
        state = "probada" if item.get("verified") else "NO verificada"
        gone = "" if item.get("present") else "  (archivo ausente)"
        print(
            f"{item['file']}  {item['rows']} filas  restauración {state}  "
            f"caduca {item['expires_at']}{gone}"
        )
    return 0


def _verify(name: str) -> int:
    settings = get_settings()
    engine = create_engine(make_url(settings.database_url))
    try:
        with Session(engine) as session:
            result = backup_service.verify_file(session, settings, name)
    finally:
        engine.dispose()
    if result["ok"]:
        print(f"OK: {name} restaura bien ({result['rows']} filas, {result['tables']} tablas).")
        return 0
    print(f"FALLA: {result.get('error') or result.get('mismatched')}")
    return 1


def _restore(name: str, apply: bool) -> int:
    settings = get_settings()
    if not apply:
        code = _verify(name)
        if code == 0:
            print("Simulacro: no se cambió nada. Agregue --apply para reemplazar la base.")
        return code
    result = backup_service.restore_backup(settings, name, datetime.now(UTC))
    print(
        f"Restaurado {result['restored_from']} en «{result['database']}»: {result['rows']} filas."
    )
    if result["safety_backup"]:
        print(f"Backup de seguridad de la base anterior: {result['safety_backup']}")
    purged = {k: v for k, v in result["purged_expired"].items() if v}
    if purged:
        print(f"Se purgaron datos de terceros vencidos: {purged}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.ops.backups", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    sub.add_parser("verify").add_argument("name")
    restore = sub.add_parser("restore")
    restore.add_argument("name")
    restore.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "list":
            return _list()
        if args.command == "verify":
            return _verify(args.name)
        return _restore(args.name, args.apply)
    except BackupError as exc:
        print(f"ERROR {exc.code}: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
