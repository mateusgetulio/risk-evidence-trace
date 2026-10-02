from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from app import carrier
from app.main import create_app
from app.seed import seed
from app.transmit import SendRefusedError, request_send
from app.worker import run_until_idle
from sqlalchemy import Engine, text


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def live_carrier(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    import uvicorn

    port = free_port()
    url = f"http://127.0.0.1:{port}/carrier"
    monkeypatch.setenv("CARRIER_URL", url)
    monkeypatch.setenv("CARRIER_CLIENT_TIMEOUT", "0.3")
    monkeypatch.setenv("CARRIER_STALL_SECONDS", "1.0")
    monkeypatch.setenv("DEMO_MODE", "1")
    carrier.state.set_mode("ok")
    server = uvicorn.Server(
        uvicorn.Config(create_app(engine), host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    assert server.started
    yield url
    server.should_exit = True
    thread.join(timeout=5)
    carrier.state.set_mode("ok")


def audit_events(engine: Engine, submission_id: int) -> list[Any]:
    with engine.connect() as conn:
        return list(
            conn.execute(
                text("SELECT kind, detail FROM audit_events WHERE submission_id = :id ORDER BY id"),
                {"id": submission_id},
            ).all()
        )


def scalar(engine: Engine, sql: str) -> Any:
    with engine.connect() as conn:
        return conn.execute(text(sql)).scalar_one()


def test_first_attempt_times_out_and_the_retry_returns_the_original_acknowledgement(
    engine: Engine, live_carrier: str
) -> None:
    harbor = seed(engine)["harbor.test"]
    carrier.state.set_mode("timeout_once")

    result = request_send(engine, harbor)
    assert result.queued and not result.replay
    run_until_idle(engine)

    with engine.connect() as conn:
        transmission = conn.execute(
            text("SELECT state, attempts, last_error FROM transmissions")
        ).one()
    assert (transmission.state, transmission.attempts) == ("delivered", 2)
    assert scalar(engine, "SELECT count(*) FROM carrier_receipts") == 1

    events = audit_events(engine, harbor)
    transmission_kinds = [e.kind for e in events if e.kind.startswith("transmission_")]
    assert transmission_kinds == [
        "transmission_created",
        "transmission_attempt_failed",
        "transmission_delivered",
    ]
    failed = next(e for e in events if e.kind == "transmission_attempt_failed")
    delivered = next(e for e in events if e.kind == "transmission_delivered")
    assert failed.detail["error"] == "timeout" and failed.detail["attempt"] == 1
    assert delivered.detail["attempts"] == 2
    assert delivered.detail["carrier_already_had_it"] is True
    stored = scalar(engine, "SELECT acknowledgement->>'acknowledgement_id' FROM carrier_receipts")
    assert delivered.detail["acknowledgement_id"] == stored


def test_send_again_returns_the_same_acknowledgement_and_creates_no_second_effect(
    engine: Engine, live_carrier: str
) -> None:
    harbor = seed(engine)["harbor.test"]
    carrier.state.set_mode("timeout_once")
    request_send(engine, harbor)
    run_until_idle(engine)
    original = scalar(engine, "SELECT acknowledgement->>'acknowledgement_id' FROM carrier_receipts")

    again = request_send(engine, harbor)
    assert again.replay and again.queued
    run_until_idle(engine)

    assert scalar(engine, "SELECT count(*) FROM transmissions") == 1
    assert scalar(engine, "SELECT count(*) FROM carrier_receipts") == 1
    replayed = [e for e in audit_events(engine, harbor) if e.kind == "transmission_replayed"]
    assert len(replayed) == 1
    assert replayed[0].detail["acknowledgement_id"] == original
    assert replayed[0].detail["same_as_original"] is True
    assert scalar(engine, "SELECT state FROM transmissions") == "delivered"
    assert scalar(engine, "SELECT attempts FROM transmissions") == 2


def test_healthy_carrier_delivers_on_the_first_attempt(engine: Engine, live_carrier: str) -> None:
    harbor = seed(engine)["harbor.test"]
    request_send(engine, harbor)
    run_until_idle(engine)
    assert scalar(engine, "SELECT attempts FROM transmissions") == 1
    assert scalar(engine, f"SELECT status FROM submissions WHERE id = {harbor}") == "quote_sent"
    delivered = next(e for e in audit_events(engine, harbor) if e.kind == "transmission_delivered")
    assert delivered.detail["carrier_already_had_it"] is False


def test_requesting_a_send_twice_before_the_worker_runs_creates_one_transmission_and_job(
    engine: Engine, live_carrier: str
) -> None:
    harbor = seed(engine)["harbor.test"]
    first = request_send(engine, harbor)
    second = request_send(engine, harbor)
    assert first.transmission_id == second.transmission_id
    assert first.queued and not second.queued
    assert scalar(engine, "SELECT count(*) FROM transmissions") == 1
    assert scalar(engine, "SELECT count(*) FROM jobs") == 1


def test_transmission_and_job_are_created_in_one_transaction(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    harbor = seed(engine)["harbor.test"]

    def broken_enqueue(*_args: Any, **_kwargs: Any) -> int:
        raise RuntimeError("queue is down")

    monkeypatch.setattr("app.transmit.jobs.enqueue", broken_enqueue)
    with pytest.raises(RuntimeError):
        request_send(engine, harbor)
    assert scalar(engine, "SELECT count(*) FROM transmissions") == 0
    assert "transmission_created" not in [e.kind for e in audit_events(engine, harbor)]


def test_only_a_quote_can_be_sent(engine: Engine, live_carrier: str) -> None:
    acme = seed(engine)["acme.test"]
    from app.ingest import deliver_fixture

    deliver_fixture(engine, acme, "acme_late_scan")
    run_until_idle(engine)
    with pytest.raises(SendRefusedError, match="REFER"):
        request_send(engine, acme)
    assert scalar(engine, "SELECT count(*) FROM transmissions") == 0


def test_unreachable_carrier_fails_after_two_attempts_and_send_again_recovers(
    engine: Engine, live_carrier: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    harbor = seed(engine)["harbor.test"]
    monkeypatch.setenv("CARRIER_URL", f"http://127.0.0.1:{free_port()}/carrier")
    request_send(engine, harbor)
    run_until_idle(engine)
    with engine.connect() as conn:
        row = conn.execute(text("SELECT state, attempts, last_error FROM transmissions")).one()
    assert (row.state, row.attempts) == ("failed", 2)
    assert row.last_error.startswith("connection error")
    assert scalar(engine, "SELECT count(*) FROM carrier_receipts") == 0

    monkeypatch.setenv("CARRIER_URL", live_carrier)
    retry = request_send(engine, harbor)
    assert retry.queued and not retry.replay
    run_until_idle(engine)
    assert scalar(engine, "SELECT state FROM transmissions") == "delivered"
    assert scalar(engine, "SELECT count(*) FROM transmissions") == 1
    assert scalar(engine, "SELECT count(*) FROM carrier_receipts") == 1


def test_carrier_requires_an_idempotency_key_and_a_quote(live_carrier: str) -> None:
    body = {"submission_id": 1, "decision_run_id": 1, "outcome": "QUOTE", "total_points": -5}
    assert httpx.post(f"{live_carrier}/quotes", json=body).status_code == 400
    refer = {**body, "outcome": "REFER"}
    response = httpx.post(f"{live_carrier}/quotes", json=refer, headers={"Idempotency-Key": "k"})
    assert response.status_code == 422


def test_same_key_returns_the_stored_acknowledgement(live_carrier: str) -> None:
    body = {"submission_id": 1, "decision_run_id": 1, "outcome": "QUOTE", "total_points": -5}
    headers = {"Idempotency-Key": "quote-1-run-1"}
    first = httpx.post(f"{live_carrier}/quotes", json=body, headers=headers)
    second = httpx.post(f"{live_carrier}/quotes", json=body, headers=headers)
    assert first.json() == second.json()
    assert "idempotent-replay" not in first.headers
    assert second.headers["idempotent-replay"] == "true"
    receipts = httpx.get(f"{live_carrier}/receipts").json()
    assert len(receipts) == 1


def test_graphql_send_to_carrier_flow_shows_the_transmission(
    engine: Engine, live_carrier: str
) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_app(engine))
    harbor = seed(engine)["harbor.test"]
    send = "mutation ($id: Int!) { sendToCarrier(submissionId: $id) { state queued replay } }"
    read = (
        "query ($id: Int!) { submission(id: $id) { pendingJobs "
        "transmission { state attempts acknowledgementId idempotencyKey } } }"
    )
    first = client.post("/graphql", json={"query": send, "variables": {"id": harbor}}).json()
    assert first["data"]["sendToCarrier"] == {"state": "pending", "queued": True, "replay": False}
    run_until_idle(engine)
    done = client.post("/graphql", json={"query": read, "variables": {"id": harbor}}).json()
    transmission = done["data"]["submission"]["transmission"]
    assert transmission["state"] == "delivered"
    assert transmission["acknowledgementId"].startswith("ack-")
    assert transmission["idempotencyKey"].startswith(f"quote-{harbor}-run-")


def test_a_failed_replay_never_changes_the_delivered_transmission(
    engine: Engine, live_carrier: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    harbor = seed(engine)["harbor.test"]
    request_send(engine, harbor)
    run_until_idle(engine)
    monkeypatch.setenv("CARRIER_URL", f"http://127.0.0.1:{free_port()}/carrier")

    again = request_send(engine, harbor)
    assert again.replay
    run_until_idle(engine)

    with engine.connect() as conn:
        row = conn.execute(text("SELECT state, attempts, last_error FROM transmissions")).one()
    assert (row.state, row.attempts, row.last_error) == ("delivered", 1, None)
    kinds = [e.kind for e in audit_events(engine, harbor)]
    assert kinds[-1] == "transmission_replay_failed"
    assert "transmission_failed" not in kinds
