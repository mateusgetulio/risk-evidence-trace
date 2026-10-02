from __future__ import annotations

from dataclasses import asdict
from datetime import timedelta
from typing import Any

from decision import RULE_SET_VERSION, Observation, Source, decide, input_hash
from sqlalchemy import Engine, text

from app import audit
from app.db import dumps


def recompute_decision(engine: Engine, submission_id: int) -> int | None:
    with engine.begin() as conn:
        submission = conn.execute(
            text(
                "SELECT clock_origin, clock_offset_days FROM submissions WHERE id = :id FOR UPDATE"
            ),
            {"id": submission_id},
        ).one()
        as_of = submission.clock_origin + timedelta(days=submission.clock_offset_days)

        rows = conn.execute(
            text(
                "SELECT id, source, subject, claim, value, observed_at FROM observations "
                "WHERE submission_id = :id ORDER BY id"
            ),
            {"id": submission_id},
        ).all()
        observations = [
            Observation(
                id=int(row.id),
                source=Source(row.source),
                subject=row.subject,
                claim=row.claim,
                value=bool(row.value),
                observed_at=row.observed_at,
            )
            for row in rows
        ]
        digest = input_hash([o.id for o in observations], as_of, RULE_SET_VERSION)

        latest = conn.execute(
            text(
                "SELECT input_hash, outcome, total_points FROM decision_runs "
                "WHERE submission_id = :id ORDER BY id DESC LIMIT 1"
            ),
            {"id": submission_id},
        ).first()
        if latest is not None and latest.input_hash == digest:
            audit.record(conn, submission_id, "decision_unchanged", {"input_hash": digest})
            return None

        decision = decide(observations, as_of, RULE_SET_VERSION)
        run = conn.execute(
            text(
                "INSERT INTO decision_runs (submission_id, as_of, rule_set_version, "
                "input_observation_ids, input_hash, outcome, total_points, contributions, "
                "blockers, superseded) "
                "VALUES (:submission_id, :as_of, :version, :ids, :hash, :outcome, :points, "
                "CAST(:contributions AS jsonb), CAST(:blockers AS jsonb), "
                "CAST(:superseded AS jsonb)) RETURNING id"
            ),
            {
                "submission_id": submission_id,
                "as_of": as_of,
                "version": RULE_SET_VERSION,
                "ids": [o.id for o in observations],
                "hash": digest,
                "outcome": decision.outcome.value,
                "points": decision.total_points,
                "contributions": dumps([asdict(c) for c in decision.contributions]),
                "blockers": dumps([asdict(b) for b in decision.blockers]),
                "superseded": dumps([asdict(s) for s in decision.superseded]),
            },
        ).one()
        detail: dict[str, Any] = {
            "decision_run_id": int(run.id),
            "outcome": decision.outcome.value,
            "total_points": decision.total_points,
            "previous_outcome": None if latest is None else latest.outcome,
            "previous_points": None if latest is None else latest.total_points,
        }
        audit.record(conn, submission_id, "decision_computed", detail)
        return int(run.id)
