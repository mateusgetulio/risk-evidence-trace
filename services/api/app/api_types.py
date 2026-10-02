from __future__ import annotations

from datetime import datetime

import strawberry


@strawberry.type
class Observation:
    id: int
    source: str
    source_observation_id: str
    subject: str
    claim: str
    value: bool
    observed_at: datetime
    received_at: datetime
    age_seconds: int
    stale: bool
    superseded_by: int | None


@strawberry.type
class Contribution:
    rule_id: str
    points: int
    observation_id: int | None
    reason: str
    missing_evidence: bool
    rule_text: str
    changed: bool


@strawberry.type
class Blocker:
    kind: str
    observation_id: int
    reason: str


@strawberry.type
class Superseded:
    observation_id: int
    superseded_by: int


@strawberry.type
class Decision:
    run_id: int | None
    as_of: datetime
    rule_set_version: str
    input_hash: str
    outcome: str
    total_points: int
    contributions: list[Contribution]
    removed: list[Contribution]
    blockers: list[Blocker]
    superseded: list[Superseded]
    created_at: datetime | None
    previous_outcome: str | None
    previous_points: int | None


@strawberry.type
class Transmission:
    id: int
    state: str
    attempts: int
    idempotency_key: str
    last_error: str | None
    decision_run_id: int
    acknowledgement_id: str | None


@strawberry.type
class SendResult:
    transmission_id: int
    state: str
    queued: bool
    replay: bool


@strawberry.type
class Submission:
    id: int
    company_name: str
    primary_domain: str
    status: str
    as_of: datetime
    pending_jobs: int
    observations: list[Observation]
    decision: Decision | None
    transmission: Transmission | None


@strawberry.type
class TimelineEvent:
    id: int
    at: datetime
    kind: str
    message: str
    detail: str


@strawberry.type
class DeliveryResult:
    new_observations: int
    clock_advanced: bool


@strawberry.type
class ResetResult:
    submission_ids: list[int]
