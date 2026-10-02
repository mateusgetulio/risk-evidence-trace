from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from decision import RULE_SET_VERSION, RULE_TEXT, Source, decide, input_hash
from decision import Observation as EngineObservation
from decision.rules import FRESHNESS
from sqlalchemy import Engine, text

from app import api_types as t
from app import jobs

SOURCE_LABELS = {
    "applicant": "The applicant",
    "external_scan": "The external scan provider",
    "posture": "The security posture provider",
}

CLAIM_PHRASES = {
    ("mfa", True): "MFA is in place",
    ("mfa", False): "no MFA observed",
    ("critical_exposed_vuln", True): "a critical internet-exposed vulnerability",
    ("critical_exposed_vuln", False): "no critical internet-exposed vulnerability",
    ("backups_tested", True): "backups are tested",
    ("backups_tested", False): "backups are not tested",
    ("ransomware_indicator", True): "an active ransomware indicator",
    ("ransomware_indicator", False): "no ransomware indicator",
}


def _contribution(item: dict[str, Any], changed: bool) -> t.Contribution:
    return t.Contribution(
        rule_id=item["rule_id"],
        points=item["points"],
        observation_id=item["observation_id"],
        reason=item["reason"],
        missing_evidence=item.get("missing_evidence", False),
        rule_text=RULE_TEXT[item["rule_id"]],
        changed=changed,
    )


def _signature(item: dict[str, Any]) -> tuple[str, int, int | None]:
    return (item["rule_id"], item["points"], item["observation_id"])


def _decision_from_run(row: Any, previous: Any | None) -> t.Decision:
    previous_items = previous.contributions if previous is not None else []
    previous_signatures = {_signature(i) for i in previous_items}
    current_signatures = {_signature(i) for i in row.contributions}
    return t.Decision(
        run_id=int(row.id),
        as_of=row.as_of,
        rule_set_version=row.rule_set_version,
        input_hash=row.input_hash,
        outcome=row.outcome,
        total_points=row.total_points,
        contributions=[
            _contribution(i, previous is not None and _signature(i) not in previous_signatures)
            for i in row.contributions
        ],
        removed=[
            _contribution(i, True)
            for i in previous_items
            if _signature(i) not in current_signatures
        ],
        blockers=[t.Blocker(**b) for b in row.blockers],
        superseded=[t.Superseded(**s) for s in row.superseded],
        created_at=row.created_at,
        previous_outcome=None if previous is None else previous.outcome,
        previous_points=None if previous is None else previous.total_points,
    )


def _latest_two_runs(conn: Any, submission_id: int) -> list[Any]:
    return list(
        conn.execute(
            text("SELECT * FROM decision_runs WHERE submission_id = :id ORDER BY id DESC LIMIT 2"),
            {"id": submission_id},
        ).all()
    )


def get_submission(engine: Engine, submission_id: int) -> t.Submission | None:
    with engine.connect() as conn:
        sub = conn.execute(
            text("SELECT * FROM submissions WHERE id = :id"), {"id": submission_id}
        ).first()
        if sub is None:
            return None
        as_of = sub.clock_origin + timedelta(days=sub.clock_offset_days)
        runs = _latest_two_runs(conn, submission_id)
        decision = _decision_from_run(runs[0], runs[1] if len(runs) > 1 else None) if runs else None
        superseded_by = (
            {s.observation_id: s.superseded_by for s in decision.superseded} if decision else {}
        )
        rows = conn.execute(
            text("SELECT * FROM observations WHERE submission_id = :id ORDER BY id"),
            {"id": submission_id},
        ).all()
        pending = jobs.pending_count(conn, submission_id)
    observations = [
        t.Observation(
            id=int(r.id),
            source=r.source,
            source_observation_id=r.source_observation_id,
            subject=r.subject,
            claim=r.claim,
            value=bool(r.value),
            observed_at=r.observed_at,
            received_at=r.received_at,
            age_seconds=int((as_of - r.observed_at).total_seconds()),
            stale=(as_of - r.observed_at) > FRESHNESS[Source(r.source)],
            superseded_by=superseded_by.get(int(r.id)),
        )
        for r in rows
    ]
    return t.Submission(
        id=int(sub.id),
        company_name=sub.company_name,
        primary_domain=sub.primary_domain,
        status=sub.status,
        as_of=as_of,
        pending_jobs=pending,
        observations=observations,
        decision=decision,
    )


def decision_trace(engine: Engine, submission_id: int, as_of: datetime | None) -> t.Decision | None:
    with engine.connect() as conn:
        if as_of is None:
            runs = _latest_two_runs(conn, submission_id)
            if not runs:
                return None
            return _decision_from_run(runs[0], runs[1] if len(runs) > 1 else None)
        rows = conn.execute(
            text(
                "SELECT id, source, subject, claim, value, observed_at FROM observations "
                "WHERE submission_id = :id ORDER BY id"
            ),
            {"id": submission_id},
        ).all()
    observations = [
        EngineObservation(
            id=int(r.id),
            source=Source(r.source),
            subject=r.subject,
            claim=r.claim,
            value=bool(r.value),
            observed_at=r.observed_at,
        )
        for r in rows
    ]
    result = decide(observations, as_of, RULE_SET_VERSION)
    return t.Decision(
        run_id=None,
        as_of=as_of,
        rule_set_version=RULE_SET_VERSION,
        input_hash=input_hash([o.id for o in observations], as_of, RULE_SET_VERSION),
        outcome=result.outcome.value,
        total_points=result.total_points,
        contributions=[
            t.Contribution(
                rule_id=c.rule_id,
                points=c.points,
                observation_id=c.observation_id,
                reason=c.reason,
                missing_evidence=c.missing_evidence,
                rule_text=RULE_TEXT[c.rule_id],
                changed=False,
            )
            for c in result.contributions
        ],
        removed=[],
        blockers=[
            t.Blocker(kind=b.kind, observation_id=b.observation_id, reason=b.reason)
            for b in result.blockers
        ],
        superseded=[
            t.Superseded(observation_id=s.observation_id, superseded_by=s.superseded_by)
            for s in result.superseded
        ],
        created_at=None,
        previous_outcome=None,
        previous_points=None,
    )


def _message(kind: str, detail: dict[str, Any]) -> str:
    if kind == "observation_received":
        source = SOURCE_LABELS[detail["source"]]
        phrase = CLAIM_PHRASES[(detail["claim"], detail["value"])]
        return f"{source} reported {phrase} (evidence #{detail['observation_id']})."
    if kind == "clock_advanced":
        return f"Scenario time moved forward to day {detail['to_days']}."
    if kind == "decision_computed":
        before = detail["previous_outcome"]
        after = detail["outcome"]
        points = detail["total_points"]
        if before is None:
            return f"First decision: {after} with {points} points."
        if before == after:
            return f"Decision recomputed: still {after}, now {points} points."
        return f"Decision changed from {before} to {after}, now {points} points."
    if kind == "decision_unchanged":
        return "Recomputed with the same evidence and clock. Nothing changed."
    if kind == "transmission_created":
        return "Quote queued for the carrier partner."
    if kind == "transmission_attempt_failed":
        return f"Carrier partner attempt failed: {detail.get('error', 'unknown error')}."
    if kind == "transmission_delivered":
        return "Carrier partner acknowledged the quote."
    if kind == "transmission_replayed":
        return "Send again returned the carrier's original acknowledgement. Nothing was sent twice."
    return kind.replace("_", " ").capitalize() + "."


def timeline(engine: Engine, submission_id: int, limit: int = 100) -> list[t.TimelineEvent]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, at, kind, detail FROM audit_events WHERE submission_id = :id "
                "ORDER BY id DESC LIMIT :limit"
            ),
            {"id": submission_id, "limit": limit},
        ).all()
    return [
        t.TimelineEvent(
            id=int(r.id),
            at=r.at,
            kind=r.kind,
            message=_message(r.kind, r.detail),
            detail=json.dumps(r.detail, sort_keys=True),
        )
        for r in rows
    ]
