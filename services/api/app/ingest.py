from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Connection, Engine, text

from app import audit, jobs
from app.adapters import ADAPTERS, IncomingObservation
from app.db import dumps
from app.fixtures import load_fixture

RECOMPUTE = "recompute_decision"


class FixtureMismatchError(ValueError):
    pass


@dataclass(frozen=True)
class DeliveryResult:
    new_observation_ids: list[int]
    clock_advanced: bool

    @property
    def changed(self) -> bool:
        return bool(self.new_observation_ids) or self.clock_advanced


def ingest(conn: Connection, submission_id: int, incoming: list[IncomingObservation]) -> list[int]:
    created: list[int] = []
    for obs in incoming:
        row = conn.execute(
            text(
                "INSERT INTO observations (submission_id, source, source_observation_id, subject, "
                "claim, value, observed_at, raw) "
                "VALUES (:submission_id, :source, :source_observation_id, :subject, :claim, "
                ":value, :observed_at, CAST(:raw AS jsonb)) "
                "ON CONFLICT (source, source_observation_id) DO NOTHING RETURNING id"
            ),
            {
                "submission_id": submission_id,
                "source": obs.source.value,
                "source_observation_id": obs.source_observation_id,
                "subject": obs.subject,
                "claim": obs.claim,
                "value": obs.value,
                "observed_at": obs.observed_at,
                "raw": dumps(obs.raw),
            },
        ).first()
        if row is None:
            continue
        created.append(int(row.id))
        audit.record(
            conn,
            submission_id,
            "observation_received",
            {
                "observation_id": int(row.id),
                "source": obs.source.value,
                "claim": obs.claim,
                "subject": obs.subject,
                "value": obs.value,
            },
        )
    return created


def deliver_fixture(engine: Engine, submission_id: int, name: str) -> DeliveryResult:
    fixture = load_fixture(name)
    with engine.begin() as conn:
        submission = conn.execute(
            text(
                "SELECT primary_domain, clock_origin, clock_offset_days FROM submissions "
                "WHERE id = :id FOR UPDATE"
            ),
            {"id": submission_id},
        ).first()
        if submission is None:
            raise FixtureMismatchError(f"unknown submission: {submission_id}")
        if fixture["primary_domain"] != submission.primary_domain:
            raise FixtureMismatchError(f"fixture {name} is not for {submission.primary_domain}")

        incoming: list[IncomingObservation] = []
        for delivery in fixture.get("deliveries", []):
            adapter = ADAPTERS[delivery["provider"]]
            incoming.extend(
                adapter.read(
                    delivery["records"], submission.clock_origin, submission.primary_domain
                )
            )
        created = ingest(conn, submission_id, incoming)

        advanced = False
        target_days = int(fixture.get("advance_clock_days", 0))
        if target_days > submission.clock_offset_days:
            conn.execute(
                text("UPDATE submissions SET clock_offset_days = :days WHERE id = :id"),
                {"days": target_days, "id": submission_id},
            )
            audit.record(
                conn,
                submission_id,
                "clock_advanced",
                {"from_days": submission.clock_offset_days, "to_days": target_days},
            )
            advanced = True

        result = DeliveryResult(created, advanced)
        if result.changed:
            jobs.enqueue(conn, RECOMPUTE, {"submission_id": submission_id})
    return result
