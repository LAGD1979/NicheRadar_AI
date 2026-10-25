"""Infraestructura de pruebas.

Las pruebas de integración usan PostgreSQL real (el servicio `db` de Compose) en una base
aparte `nicheradar_test`. Ningún test llama a red ni a APIs externas.
"""

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from alembic import command
from alembic.config import Config
from app.core.config import get_settings
from app.db.models import Base
from app.db.session import get_session_factory, reset_engine_cache
from app.demo.seed import load_fixture, seed_fixture

DEFAULT_TEST_URL = "postgresql+psycopg://nicheradar:nicheradar@db:5432/nicheradar_test"


def _reset_settings() -> None:
    get_settings.cache_clear()
    reset_engine_cache()


@pytest.fixture(scope="session")
def test_database_url() -> Iterator[str]:
    url = os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_URL)
    database = make_url(url).database
    admin = create_engine(make_url(url).set(database="postgres"), isolation_level="AUTOCOMMIT")
    # Base recreada en cada sesión: las migraciones se prueban desde cero.
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{database}"'))
    admin.dispose()

    os.environ["DATABASE_URL"] = url
    # Las pruebas nunca llaman a YouTube: la clave real, si existe en el entorno, se anula aquí.
    os.environ["YOUTUBE_API_KEY"] = ""
    # Las pruebas fijan el modo de cumplimiento: no heredan la configuración local (.env).
    os.environ["COMPLIANCE_MODE"] = "restricted"
    os.environ["ADVANCED_ANALYTICS_ENABLED"] = "false"
    _reset_settings()
    command.upgrade(Config("alembic.ini"), "head")
    yield url


def truncate_all(session: Session) -> None:
    tables = ", ".join(f'"{t.name}"' for t in reversed(Base.metadata.sorted_tables))
    session.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    session.commit()


@pytest.fixture
def empty_db(test_database_url: str) -> Iterator[Session]:
    factory = get_session_factory()
    with factory() as session:
        truncate_all(session)
        yield session


@pytest.fixture
def seeded_db(empty_db: Session) -> Session:
    seed_fixture(empty_db, load_fixture())
    empty_db.commit()
    return empty_db


@pytest.fixture
def client(seeded_db: Session) -> Iterator[TestClient]:
    # Import diferido: la app lee la configuración al crearse, con la URL de prueba ya fijada.
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
