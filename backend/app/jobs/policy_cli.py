"""Registro de aprobaciones de políticas (spec §0.8, §5.5). Solo por línea de comandos.

No hay endpoint ni pantalla para conceder aprobaciones: así una aprobación exige una decisión
explícita, con referencia documental y caducidad. Ejemplo:

  python -m app.jobs.policy_cli grant --capability advanced_scores \
      --provider youtube_official --scope "cohorte X" --approval-ref "DOC-2026-001" \
      --reviewer "nombre" --expires 2027-01-31 --notes "Condiciones de métricas derivadas"
  python -m app.jobs.policy_cli list
  python -m app.jobs.policy_cli revoke --id <uuid>
"""

import argparse
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select

from app.db import models as m
from app.db.session import get_session_factory
from app.services.compliance_service import CAPABILITIES


def _grant(args: argparse.Namespace) -> int:
    if args.capability not in CAPABILITIES:
        raise SystemExit(f"Capacidad desconocida: {args.capability}")
    if not args.approval_ref.strip():
        raise SystemExit("La referencia documental es obligatoria.")
    expires = datetime.combine(date.fromisoformat(args.expires), datetime.max.time(), tzinfo=UTC)
    if expires <= datetime.now(UTC):
        raise SystemExit("La fecha de caducidad debe estar en el futuro.")
    approval = m.PolicyApproval(
        id=str(uuid.uuid4()),
        provider=args.provider,
        capability=args.capability,
        scope=args.scope,
        status="ACTIVE",
        approval_ref=args.approval_ref.strip(),
        reviewed_by=args.reviewer,
        effective_at=datetime.now(UTC),
        expires_at=expires,
        notes=args.notes,
    )
    with get_session_factory()() as session, session.begin():
        session.add(approval)
    print(f"Aprobación registrada: {approval.id} (vence {expires.date().isoformat()})")
    return 0


def _revoke(args: argparse.Namespace) -> int:
    with get_session_factory()() as session, session.begin():
        approval = session.get(m.PolicyApproval, args.id)
        if approval is None:
            raise SystemExit("Aprobación no encontrada.")
        approval.status = "REVOKED"
    print(f"Aprobación revocada: {args.id}")
    return 0


def _list(_: argparse.Namespace) -> int:
    with get_session_factory()() as session:
        rows = session.scalars(
            select(m.PolicyApproval).order_by(m.PolicyApproval.effective_at)
        ).all()
        for row in rows:
            print(
                f"{row.id} | {row.capability} | {row.status} | {row.approval_ref} "
                f"| vence {row.expires_at}"
            )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Aprobaciones de políticas de NicheRadar")
    sub = parser.add_subparsers(dest="command", required=True)

    grant = sub.add_parser("grant", help="registrar una aprobación vigente")
    grant.add_argument("--capability", required=True)
    grant.add_argument("--provider", required=True)
    grant.add_argument("--scope", required=True)
    grant.add_argument("--approval-ref", required=True)
    grant.add_argument("--reviewer", required=True)
    grant.add_argument("--expires", required=True, help="AAAA-MM-DD")
    grant.add_argument("--notes", default=None)
    grant.set_defaults(func=_grant)

    revoke = sub.add_parser("revoke", help="revocar una aprobación")
    revoke.add_argument("--id", required=True)
    revoke.set_defaults(func=_revoke)

    listing = sub.add_parser("list", help="listar aprobaciones")
    listing.set_defaults(func=_list)

    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
