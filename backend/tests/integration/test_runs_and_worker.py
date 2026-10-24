from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db import models as m
from app.db.session import get_session_factory
from app.jobs import worker
from app.jobs.worker import process_once


def _drain(factory: sessionmaker[Session]) -> int:
    processed = 0
    while process_once(factory):
        processed += 1
    return processed


def test_create_run_returns_202_and_does_not_execute_inline(client: TestClient) -> None:
    response = client.post("/api/v1/research-runs", json={"kind": "demo"})
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "QUEUED"
    run = client.get(f"/api/v1/research-runs/{body['id']}").json()
    assert run["status"] == "QUEUED"
    assert run["params"]["network"] is False


def test_only_demo_kind_is_accepted_in_m0(client: TestClient) -> None:
    response = client.post("/api/v1/research-runs", json={"kind": "full"})
    assert response.status_code == 422


def test_worker_completes_demo_run_once(client: TestClient) -> None:
    run_id = client.post("/api/v1/research-runs", json={"kind": "demo"}).json()["id"]
    factory = get_session_factory()
    assert _drain(factory) == 1
    run = client.get(f"/api/v1/research-runs/{run_id}").json()
    assert run["status"] == "COMPLETED"
    assert run["coverage"]["network"] is False
    assert run["coverage"]["channels"] == 10
    # Reintentar la cola no vuelve a ejecutar nada (T21).
    assert process_once(factory) is False


def test_repeated_requests_create_separate_runs_without_duplicate_work(client: TestClient) -> None:
    client.post("/api/v1/research-runs", json={"kind": "demo"})
    client.post("/api/v1/research-runs", json={"kind": "demo"})
    factory = get_session_factory()
    assert _drain(factory) == 2
    with factory() as session:
        completed = session.scalar(
            select(func.count())
            .select_from(m.ResearchRun)
            .where(
                m.ResearchRun.status == "COMPLETED",
                m.ResearchRun.id != "syn-run-demo-01",  # corrida sembrada, no creada por la API
            )
        )
    assert completed == 2


def test_stale_running_task_is_recovered(client: TestClient, monkeypatch: Any) -> None:
    """Un worker caído deja la tarea RUNNING; tras el arrendamiento otro worker la completa."""
    run_id = client.post("/api/v1/research-runs", json={"kind": "demo"}).json()["id"]
    factory = get_session_factory()
    with factory() as session, session.begin():
        task = session.scalars(select(m.RunTask).where(m.RunTask.run_id == run_id)).one()
        task.status = "RUNNING"
        task.locked_at = datetime.now(UTC) - worker.LEASE - timedelta(minutes=1)
        task.attempts = 1
    assert _drain(factory) == 1
    assert client.get(f"/api/v1/research-runs/{run_id}").json()["status"] == "COMPLETED"


def test_failing_task_is_retried_then_marks_run_failed(
    client: TestClient, monkeypatch: Any
) -> None:
    run_id = client.post("/api/v1/research-runs", json={"kind": "demo"}).json()["id"]

    def boom(session: Session, run_id: str) -> dict[str, Any]:
        raise RuntimeError("fallo simulado")

    monkeypatch.setitem(worker.HANDLERS, "demo_research", boom)
    factory = get_session_factory()
    now = datetime.now(UTC)
    for _ in range(worker.MAX_ATTEMPTS):
        # Forzar que el reintento esté disponible de inmediato en el test.
        with factory() as session, session.begin():
            session.execute(
                m.RunTask.__table__.update().values(next_attempt_at=now - timedelta(seconds=1))
            )
        process_once(factory)

    run = client.get(f"/api/v1/research-runs/{run_id}").json()
    assert run["status"] == "FAILED"
    assert run["errors"][0]["code"] == "RuntimeError"
