from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import UTC, datetime

from decision.models import (
    Blocker,
    Contribution,
    Decision,
    Observation,
    Outcome,
    Superseded,
)
from decision.rules import (
    BK_UNVERIFIED_POINTS,
    BK_VERIFIED_POINTS,
    CLAIM_BACKUPS,
    CLAIM_MFA,
    CLAIM_RANSOMWARE,
    CLAIM_VULN,
    EX_POINTS,
    FRESHNESS,
    RA_POINTS,
    REFER_THRESHOLD,
    RULE_SET_VERSION,
    SOURCE_RANK,
)


def input_hash(observation_ids: Iterable[int], as_of: datetime, rule_set_version: str) -> str:
    payload = {
        "observation_ids": sorted(observation_ids),
        "as_of": _utc(as_of).isoformat(),
        "rule_set_version": rule_set_version,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def decide(
    observations: Iterable[Observation],
    as_of: datetime,
    rule_set_version: str = RULE_SET_VERSION,
) -> Decision:
    if rule_set_version != RULE_SET_VERSION:
        raise ValueError(f"unknown rule set version: {rule_set_version}")
    as_of = _utc(as_of)
    known = _known_at(observations, as_of)
    groups = _precedence_groups(known)

    contributions: list[Contribution] = []
    blockers: list[Blocker] = []
    superseded: list[Superseded] = []
    winners: list[Observation] = []

    for ordered in groups:
        winner = ordered[0]
        winners.append(winner)
        superseded.extend(Superseded(loser.id, winner.id) for loser in ordered[1:])
        stale = _is_stale(winner, as_of)
        if stale:
            blockers.append(
                Blocker(
                    kind="stale_evidence",
                    observation_id=winner.id,
                    reason=_stale_reason(winner, as_of),
                )
            )
        contribution = _risk_contribution(winner)
        if contribution is None and stale:
            contribution = _fallback_risk_contribution(winner, ordered[1:])
        if contribution is not None:
            contributions.append(contribution)

    contributions.extend(_backup_contributions(winners, as_of))
    decline = any(c.rule_id == "HD-01" for c in contributions)

    contributions.sort(
        key=lambda c: (c.rule_id, -1 if c.observation_id is None else c.observation_id)
    )
    blockers.sort(key=lambda b: b.observation_id)
    total = sum(c.points for c in contributions)

    if decline:
        outcome = Outcome.DECLINE
    elif total >= REFER_THRESHOLD or blockers:
        outcome = Outcome.REFER
    else:
        outcome = Outcome.QUOTE

    return Decision(
        outcome=outcome,
        total_points=total,
        contributions=tuple(contributions),
        blockers=tuple(blockers),
        superseded=tuple(sorted(superseded, key=lambda s: s.observation_id)),
    )


def _risk_contribution(obs: Observation) -> Contribution | None:
    if obs.claim == CLAIM_VULN and obs.value:
        return Contribution(
            "EX-01", EX_POINTS, obs.id, f"Critical exposed vulnerability on {obs.subject}."
        )
    if obs.claim == CLAIM_MFA and not obs.value:
        return Contribution("RA-01", RA_POINTS, obs.id, f"No MFA observed on {obs.subject}.")
    if obs.claim == CLAIM_RANSOMWARE and obs.value:
        return Contribution("HD-01", 0, obs.id, f"Active ransomware indicator on {obs.subject}.")
    return None


def _fallback_risk_contribution(
    stale_winner: Observation, losers: list[Observation]
) -> Contribution | None:
    for candidate in losers:
        contribution = _risk_contribution(candidate)
        if contribution is not None:
            return Contribution(
                contribution.rule_id,
                contribution.points,
                contribution.observation_id,
                f"{contribution.reason} Kept because #{stale_winner.id} is stale and cannot "
                "reduce risk.",
            )
    return None


def _backup_contributions(winners: list[Observation], as_of: datetime) -> list[Contribution]:
    backups = sorted((o for o in winners if o.claim == CLAIM_BACKUPS), key=lambda o: o.id)
    if not backups:
        return [
            Contribution("BK-01", BK_UNVERIFIED_POINTS, None, "No backups observation received.")
        ]
    for obs in backups:
        if not obs.value:
            return [
                Contribution(
                    "BK-01", BK_UNVERIFIED_POINTS, obs.id, f"Backups not verified on {obs.subject}."
                )
            ]
        if _is_stale(obs, as_of):
            return [
                Contribution(
                    "BK-01",
                    BK_UNVERIFIED_POINTS,
                    obs.id,
                    f"Backup verification on {obs.subject} is stale, so it cannot reduce risk.",
                )
            ]
    first = backups[0]
    return [
        Contribution(
            "BK-02", BK_VERIFIED_POINTS, first.id, f"Recent verified backups on {first.subject}."
        )
    ]


def _known_at(observations: Iterable[Observation], as_of: datetime) -> list[Observation]:
    seen: set[int] = set()
    known: list[Observation] = []
    for obs in observations:
        if obs.id in seen:
            raise ValueError(f"duplicate observation id: {obs.id}")
        seen.add(obs.id)
        observed_at = _utc(obs.observed_at)
        if observed_at <= as_of:
            known.append(obs)
    return known


def _precedence_groups(observations: list[Observation]) -> list[list[Observation]]:
    groups: dict[tuple[str, str], list[Observation]] = {}
    for obs in observations:
        groups.setdefault((obs.subject, obs.claim), []).append(obs)
    return [sorted(group, key=_precedence_key) for group in groups.values()]


def _precedence_key(obs: Observation) -> tuple[int, float, int]:
    return (SOURCE_RANK[obs.source], -_utc(obs.observed_at).timestamp(), -obs.id)


def _is_stale(obs: Observation, as_of: datetime) -> bool:
    return as_of - _utc(obs.observed_at) > FRESHNESS[obs.source]


def _stale_reason(obs: Observation, as_of: datetime) -> str:
    age_days = (as_of - _utc(obs.observed_at)).days
    window_days = FRESHNESS[obs.source].days
    return (
        f"{obs.source.value} observation on {obs.subject} is {age_days} days old, "
        f"past its {window_days} day window. Needs review."
    )


def _utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        raise ValueError("datetimes must be timezone aware")
    return moment.astimezone(UTC)
