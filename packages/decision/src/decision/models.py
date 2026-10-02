from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class Source(StrEnum):
    APPLICANT = "applicant"
    EXTERNAL_SCAN = "external_scan"
    POSTURE = "posture"


class Outcome(StrEnum):
    QUOTE = "QUOTE"
    REFER = "REFER"
    DECLINE = "DECLINE"


@dataclass(frozen=True)
class Observation:
    id: int
    source: Source
    subject: str
    claim: str
    value: bool
    observed_at: datetime


@dataclass(frozen=True)
class Contribution:
    rule_id: str
    points: int
    observation_id: int | None
    reason: str


@dataclass(frozen=True)
class Blocker:
    kind: str
    observation_id: int
    reason: str


@dataclass(frozen=True)
class Superseded:
    observation_id: int
    superseded_by: int


@dataclass(frozen=True)
class Decision:
    outcome: Outcome
    total_points: int
    contributions: tuple[Contribution, ...]
    blockers: tuple[Blocker, ...]
    superseded: tuple[Superseded, ...]
