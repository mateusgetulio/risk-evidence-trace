from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy import Engine, text

from app import audit, jobs
from app.config import carrier_client_timeout, carrier_retry_delay_seconds, carrier_url
from app.db import dumps

SEND_JOB = "send_to_carrier"
MAX_ATTEMPTS = 2


class SendRefusedError(ValueError):
    pass


@dataclass(frozen=True)
class SendResult:
    transmission_id: int
    state: str
    queued: bool
    replay: bool


def idempotency_key(submission_id: int, decision_run_id: int) -> str:
    return f"quote-{submission_id}-run-{decision_run_id}"


def request_send(engine: Engine, submission_id: int) -> SendResult:
    with engine.begin() as conn:
        found = conn.execute(
            text("SELECT id FROM submissions WHERE id = :id FOR UPDATE"), {"id": submission_id}
        ).first()
        if found is None:
            raise SendRefusedError(f"Unknown submission: {submission_id}")
        run = conn.execute(
            text(
                "SELECT id, outcome FROM decision_runs WHERE submission_id = :id "
                "ORDER BY id DESC LIMIT 1"
            ),
            {"id": submission_id},
        ).first()
        if run is None:
            raise SendRefusedError("There is no decision to send yet")
        if run.outcome != "QUOTE":
            raise SendRefusedError(
                f"Only a QUOTE can be sent to the carrier, this one is {run.outcome}"
            )

        key = idempotency_key(submission_id, int(run.id))
        created = conn.execute(
            text(
                "INSERT INTO transmissions (decision_run_id, idempotency_key) "
                "VALUES (:run, :key) ON CONFLICT (idempotency_key) DO NOTHING RETURNING id"
            ),
            {"run": int(run.id), "key": key},
        ).first()
        if created is not None:
            transmission_id = int(created.id)
            audit.record(
                conn,
                submission_id,
                "transmission_created",
                {"transmission_id": transmission_id, "idempotency_key": key},
            )
            jobs.enqueue(
                conn, SEND_JOB, {"submission_id": submission_id, "transmission_id": transmission_id}
            )
            return SendResult(transmission_id, "pending", queued=True, replay=False)

        existing = conn.execute(
            text("SELECT id, state FROM transmissions WHERE idempotency_key = :key"), {"key": key}
        ).one()
        transmission_id = int(existing.id)
        if existing.state == "pending":
            pulled = conn.execute(
                text(
                    "UPDATE jobs SET run_at = now() "
                    "WHERE kind = :kind AND (payload->>'transmission_id')::bigint = :id "
                    "AND run_at > now() AND locked_at IS NULL RETURNING id"
                ),
                {"kind": SEND_JOB, "id": transmission_id},
            ).first()
            if pulled is None:
                return SendResult(transmission_id, "pending", queued=False, replay=False)
            audit.record(
                conn,
                submission_id,
                "transmission_retry_requested",
                {"transmission_id": transmission_id},
            )
            return SendResult(transmission_id, "pending", queued=True, replay=False)
        replay = existing.state == "delivered"
        if not replay:
            conn.execute(
                text(
                    "UPDATE transmissions SET state = 'pending', last_error = NULL WHERE id = :id"
                ),
                {"id": transmission_id},
            )
        jobs.enqueue(
            conn,
            SEND_JOB,
            {"submission_id": submission_id, "transmission_id": transmission_id, "replay": replay},
        )
        return SendResult(transmission_id, existing.state, queued=True, replay=replay)


def _post(row: Any, key: str) -> httpx.Response:
    return httpx.post(
        f"{carrier_url()}/quotes",
        json={
            "submission_id": int(row.submission_id),
            "decision_run_id": int(row.decision_run_id),
            "outcome": row.outcome,
            "total_points": int(row.total_points),
        },
        headers={"Idempotency-Key": key},
        timeout=httpx.Timeout(carrier_client_timeout()),
    )


def _bump_attempts(engine: Engine, transmission_id: int) -> int:
    with engine.begin() as conn:
        row = conn.execute(
            text(
                "UPDATE transmissions SET attempts = attempts + 1 WHERE id = :id RETURNING attempts"
            ),
            {"id": transmission_id},
        ).one()
    return int(row.attempts)


def _record_failure(
    engine: Engine,
    submission_id: int,
    transmission_id: int,
    attempt: int,
    error: str,
    retry_in_seconds: float | None,
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE transmissions SET last_error = :error WHERE id = :id"),
            {"id": transmission_id, "error": error},
        )
        audit.record(
            conn,
            submission_id,
            "transmission_attempt_failed",
            {
                "transmission_id": transmission_id,
                "attempt": attempt,
                "error": error,
                "retry_in_seconds": retry_in_seconds,
            },
        )
        if retry_in_seconds is not None:
            conn.execute(
                text(
                    "INSERT INTO jobs (kind, payload, run_at) "
                    "VALUES (:kind, CAST(:payload AS jsonb), now() + make_interval(secs => :delay))"
                ),
                {
                    "kind": SEND_JOB,
                    "payload": dumps(
                        {
                            "submission_id": submission_id,
                            "transmission_id": transmission_id,
                            "retry": True,
                        }
                    ),
                    "delay": retry_in_seconds,
                },
            )


def send_to_carrier(engine: Engine, payload: dict[str, Any]) -> None:
    transmission_id = int(payload["transmission_id"])
    replay = bool(payload.get("replay", False))
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT t.id, t.state, t.idempotency_key, t.decision_run_id, "
                "r.submission_id, r.outcome, r.total_points "
                "FROM transmissions t JOIN decision_runs r ON r.id = t.decision_run_id "
                "WHERE t.id = :id"
            ),
            {"id": transmission_id},
        ).one()
    if row.state == "delivered" and not replay:
        return
    submission_id = int(row.submission_id)
    if replay:
        _replay(engine, row, submission_id, transmission_id)
        return

    is_retry = bool(payload.get("retry", False))
    attempt = _bump_attempts(engine, transmission_id)
    try:
        response = _post(row, row.idempotency_key)
    except httpx.TimeoutException:
        error = "timeout"
    except httpx.TransportError as exc:
        error = f"connection error: {type(exc).__name__}"
    else:
        if response.status_code < 400:
            _succeed(engine, submission_id, transmission_id, attempt, response)
            return
        if response.status_code < 500:
            _fail(engine, submission_id, transmission_id, f"rejected {response.status_code}")
            return
        error = f"carrier error {response.status_code}"

    if is_retry:
        _record_failure(engine, submission_id, transmission_id, attempt, error, None)
        _fail(engine, submission_id, transmission_id, error, attempts=MAX_ATTEMPTS)
    else:
        delay = carrier_retry_delay_seconds()
        _record_failure(engine, submission_id, transmission_id, attempt, error, delay)


def _replay(engine: Engine, row: Any, submission_id: int, transmission_id: int) -> None:
    try:
        response = _post(row, row.idempotency_key)
    except httpx.TimeoutException:
        error = "timeout"
    except httpx.TransportError as exc:
        error = f"connection error: {type(exc).__name__}"
    else:
        if response.status_code < 400:
            with engine.begin() as conn:
                audit.record(
                    conn,
                    submission_id,
                    "transmission_replayed",
                    {
                        "transmission_id": transmission_id,
                        "acknowledgement_id": response.json()["acknowledgement_id"],
                        "same_as_original": response.headers.get("Idempotent-Replay") == "true",
                    },
                )
            return
        error = f"carrier error {response.status_code}"
    with engine.begin() as conn:
        audit.record(
            conn,
            submission_id,
            "transmission_replay_failed",
            {"transmission_id": transmission_id, "error": error},
        )


def _succeed(
    engine: Engine,
    submission_id: int,
    transmission_id: int,
    attempt: int,
    response: httpx.Response,
) -> None:
    acknowledgement = response.json()
    already_had_it = response.headers.get("Idempotent-Replay") == "true"
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE transmissions SET state = 'delivered', last_error = NULL WHERE id = :id"),
            {"id": transmission_id},
        )
        conn.execute(
            text("UPDATE submissions SET status = 'quote_sent' WHERE id = :id"),
            {"id": submission_id},
        )
        audit.record(
            conn,
            submission_id,
            "transmission_delivered",
            {
                "transmission_id": transmission_id,
                "acknowledgement_id": acknowledgement["acknowledgement_id"],
                "attempts": attempt,
                "carrier_already_had_it": already_had_it,
            },
        )


def _fail(
    engine: Engine,
    submission_id: int,
    transmission_id: int,
    error: str,
    attempts: int | None = None,
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE transmissions SET state = 'failed', last_error = :error WHERE id = :id"),
            {"id": transmission_id, "error": error},
        )
        audit.record(
            conn,
            submission_id,
            "transmission_failed",
            {"transmission_id": transmission_id, "error": error, "attempts": attempts},
        )
