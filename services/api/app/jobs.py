from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Connection, Engine, text

from app.db import dumps

MAX_ATTEMPTS = 5
LOCK_SECONDS = 60
RETRY_SECONDS = 2


@dataclass(frozen=True)
class Job:
    id: int
    kind: str
    payload: dict[str, Any]
    attempts: int
    locked_at: datetime


def enqueue(
    conn: Connection, kind: str, payload: dict[str, Any], run_at: datetime | None = None
) -> int:
    row = conn.execute(
        text(
            "INSERT INTO jobs (kind, payload, run_at) "
            "VALUES (:kind, CAST(:payload AS jsonb), COALESCE(:run_at, now())) RETURNING id"
        ),
        {"kind": kind, "payload": dumps(payload), "run_at": run_at},
    ).one()
    return int(row.id)


def claim(engine: Engine) -> Job | None:
    with engine.begin() as conn:
        row = conn.execute(
            text(
                "UPDATE jobs SET locked_at = now(), attempts = attempts + 1 "
                "WHERE id = ("
                "  SELECT id FROM jobs"
                "  WHERE run_at <= now() AND attempts < :max_attempts"
                "    AND (locked_at IS NULL"
                "         OR locked_at < now() - make_interval(secs => :lock_seconds))"
                "  ORDER BY run_at, id"
                "  FOR UPDATE SKIP LOCKED LIMIT 1"
                ") RETURNING id, kind, payload, attempts, locked_at"
            ),
            {"max_attempts": MAX_ATTEMPTS, "lock_seconds": LOCK_SECONDS},
        ).first()
    if row is None:
        return None
    return Job(
        id=int(row.id),
        kind=str(row.kind),
        payload=dict(row.payload),
        attempts=int(row.attempts),
        locked_at=row.locked_at,
    )


def complete(engine: Engine, job: Job) -> bool:
    with engine.begin() as conn:
        result = conn.execute(
            text("DELETE FROM jobs WHERE id = :id AND locked_at = :locked_at"),
            {"id": job.id, "locked_at": job.locked_at},
        )
    return result.rowcount == 1


def release_for_retry(engine: Engine, job: Job) -> bool:
    with engine.begin() as conn:
        result = conn.execute(
            text(
                "UPDATE jobs SET locked_at = NULL, "
                "run_at = now() + make_interval(secs => :retry_seconds) "
                "WHERE id = :id AND locked_at = :locked_at"
            ),
            {"id": job.id, "locked_at": job.locked_at, "retry_seconds": RETRY_SECONDS},
        )
    return result.rowcount == 1


def pending_count(conn: Connection, submission_id: int) -> int:
    row = conn.execute(
        text(
            "SELECT count(*) AS n FROM jobs "
            "WHERE (payload->>'submission_id')::int = :id AND attempts < :max_attempts "
            "AND run_at <= now()"
        ),
        {"id": submission_id, "max_attempts": MAX_ATTEMPTS},
    ).one()
    return int(row.n)
