from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from alembic.config import Config
from alembic.script import ScriptDirectory
from app.db.session import get_session

router = APIRouter(prefix="/health", tags=["health"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/live")
def live() -> dict[str, str]:
    """El proceso responde. No comprueba dependencias."""
    return {"status": "ok"}


def _expected_head() -> str | None:
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    return script.get_current_head()


@router.get("/ready")
def ready(session: SessionDep) -> JSONResponse:
    """Listo si la base responde y la versión de migraciones coincide con la del código."""
    try:
        session.execute(text("SELECT 1"))
        current = session.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    except Exception:
        return JSONResponse(
            {"status": "not_ready", "reason": "database_or_migrations"}, status_code=503
        )
    head = _expected_head()
    if current != head:
        return JSONResponse(
            {
                "status": "not_ready",
                "reason": "migrations_pending",
                "current": current,
                "head": head,
            },
            status_code=503,
        )
    return JSONResponse({"status": "ready", "migration": current})
