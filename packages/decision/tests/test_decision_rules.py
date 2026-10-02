from __future__ import annotations

from datetime import timedelta

import pytest
from conftest import AS_OF
from decision import Observation, Outcome, Source, decide


def obs(
    id: int,
    source: Source,
    claim: str,
    value: bool,
    age: timedelta,
    subject: str = "remote_access",
) -> Observation:
    return Observation(id, source, subject, claim, value, AS_OF - age)


FRESH_BACKUPS = obs(100, Source.APPLICANT, "backups_tested", True, timedelta(days=60), "backups")


def test_clean_applicant_gets_a_quote_with_negative_points() -> None:
    decision = decide([FRESH_BACKUPS], AS_OF)
    assert decision.outcome is Outcome.QUOTE
    assert decision.total_points == -5
    assert [c.rule_id for c in decision.contributions] == ["BK-02"]


def test_critical_vulnerability_adds_20_and_refers() -> None:
    vuln = obs(
        2, Source.EXTERNAL_SCAN, "critical_exposed_vuln", True, timedelta(hours=2), "vpn.acme.test"
    )
    decision = decide([FRESH_BACKUPS, vuln], AS_OF)
    assert decision.outcome is Outcome.REFER
    assert decision.total_points == 15
    ex = [c for c in decision.contributions if c.rule_id == "EX-01"]
    assert ex and ex[0].observation_id == 2 and ex[0].points == 20


def test_missing_mfa_adds_15_and_refers_at_the_threshold() -> None:
    no_mfa = obs(2, Source.POSTURE, "mfa", False, timedelta(hours=1))
    decision = decide([no_mfa], AS_OF)
    assert decision.total_points == 25
    assert decision.outcome is Outcome.REFER
    no_mfa_with_backups = decide([no_mfa, FRESH_BACKUPS], AS_OF)
    assert no_mfa_with_backups.total_points == 10
    assert no_mfa_with_backups.outcome is Outcome.QUOTE


def test_threshold_is_15_inclusive() -> None:
    vuln = obs(
        2, Source.EXTERNAL_SCAN, "critical_exposed_vuln", True, timedelta(hours=2), "vpn.acme.test"
    )
    assert decide([FRESH_BACKUPS, vuln], AS_OF).total_points == 15
    assert decide([FRESH_BACKUPS, vuln], AS_OF).outcome is Outcome.REFER
    mfa_off = obs(3, Source.POSTURE, "mfa", False, timedelta(hours=1))
    assert decide([FRESH_BACKUPS, mfa_off], AS_OF).total_points == 10


def test_ransomware_indicator_always_declines() -> None:
    ransomware = obs(
        2, Source.EXTERNAL_SCAN, "ransomware_indicator", True, timedelta(days=1), "acme.test"
    )
    decision = decide([FRESH_BACKUPS, ransomware], AS_OF)
    assert decision.outcome is Outcome.DECLINE
    assert decision.total_points == -5
    assert any(c.rule_id == "HD-01" and c.observation_id == 2 for c in decision.contributions)


def test_missing_backups_add_ten_without_an_observation_and_without_a_blocker() -> None:
    decision = decide([], AS_OF)
    assert [(c.rule_id, c.points, c.observation_id) for c in decision.contributions] == [
        ("BK-01", 10, None)
    ]
    assert decision.blockers == ()
    assert decision.outcome is Outcome.QUOTE


def test_stale_backup_attestation_adds_risk_and_a_blocker() -> None:
    stale = obs(1, Source.APPLICANT, "backups_tested", True, timedelta(days=94), "backups")
    decision = decide([stale], AS_OF)
    assert decision.total_points == 10
    assert [c.rule_id for c in decision.contributions] == ["BK-01"]
    assert [b.observation_id for b in decision.blockers] == [1]
    assert decision.outcome is Outcome.REFER


def test_any_blocker_forces_at_least_refer_even_with_low_points() -> None:
    stale_mfa = obs(2, Source.POSTURE, "mfa", True, timedelta(days=8))
    decision = decide([FRESH_BACKUPS, stale_mfa], AS_OF)
    assert decision.total_points == -5
    assert decision.outcome is Outcome.REFER


@pytest.mark.parametrize(
    ("source", "window_days"),
    [(Source.APPLICANT, 90), (Source.EXTERNAL_SCAN, 30), (Source.POSTURE, 7)],
)
def test_freshness_windows_per_source(source: Source, window_days: int) -> None:
    inside = obs(5, source, "mfa", True, timedelta(days=window_days))
    outside = obs(6, source, "mfa", True, timedelta(days=window_days, seconds=1))
    assert decide([FRESH_BACKUPS, inside], AS_OF).blockers == ()
    assert len(decide([FRESH_BACKUPS, outside], AS_OF).blockers) == 1


def test_precedence_prefers_posture_then_scan_then_applicant() -> None:
    applicant = obs(1, Source.APPLICANT, "mfa", True, timedelta(minutes=5))
    scan = obs(2, Source.EXTERNAL_SCAN, "mfa", False, timedelta(hours=2))
    posture = obs(3, Source.POSTURE, "mfa", True, timedelta(days=3))
    decision = decide([FRESH_BACKUPS, applicant, scan, posture], AS_OF)
    assert {(s.observation_id, s.superseded_by) for s in decision.superseded} == {(1, 3), (2, 3)}
    assert decision.blockers == ()
    assert all(c.rule_id != "RA-01" for c in decision.contributions)
    without_posture = decide([FRESH_BACKUPS, applicant, scan], AS_OF)
    assert {(s.observation_id, s.superseded_by) for s in without_posture.superseded} == {(1, 2)}
    assert any(c.rule_id == "RA-01" for c in without_posture.contributions)


def test_stale_winner_cannot_hide_risk_reported_by_a_lower_source() -> None:
    scan = obs(2, Source.EXTERNAL_SCAN, "mfa", False, timedelta(hours=2))
    posture = obs(3, Source.POSTURE, "mfa", True, timedelta(days=8))
    decision = decide([FRESH_BACKUPS, scan, posture], AS_OF)
    ra = [c for c in decision.contributions if c.rule_id == "RA-01"]
    assert [c.observation_id for c in ra] == [2]
    assert [b.observation_id for b in decision.blockers] == [3]
    assert decision.outcome is Outcome.REFER


def test_stale_all_clear_cannot_cancel_a_decline() -> None:
    ransomware = obs(2, Source.EXTERNAL_SCAN, "ransomware_indicator", True, timedelta(days=1))
    all_clear = obs(3, Source.POSTURE, "ransomware_indicator", False, timedelta(days=10))
    decision = decide([FRESH_BACKUPS, ransomware, all_clear], AS_OF)
    assert decision.outcome is Outcome.DECLINE


def test_only_one_backups_contribution_is_ever_produced() -> None:
    first = obs(1, Source.APPLICANT, "backups_tested", True, timedelta(days=1), "backups")
    second = obs(2, Source.APPLICANT, "backups_tested", True, timedelta(days=1), "offsite_backups")
    decision = decide([first, second], AS_OF)
    assert [c.rule_id for c in decision.contributions] == ["BK-02"]
    assert decision.total_points == -5


def test_newest_observation_wins_within_a_source() -> None:
    old = obs(1, Source.POSTURE, "mfa", False, timedelta(days=3))
    new = obs(2, Source.POSTURE, "mfa", True, timedelta(hours=1))
    decision = decide([FRESH_BACKUPS, old, new], AS_OF)
    assert [(s.observation_id, s.superseded_by) for s in decision.superseded] == [(1, 2)]
    assert all(c.rule_id != "RA-01" for c in decision.contributions)


def test_observations_after_as_of_are_ignored() -> None:
    future = Observation(
        9,
        Source.EXTERNAL_SCAN,
        "vpn.acme.test",
        "critical_exposed_vuln",
        True,
        AS_OF + timedelta(hours=1),
    )
    assert decide([FRESH_BACKUPS, future], AS_OF) == decide([FRESH_BACKUPS], AS_OF)


def test_superseded_stale_observation_adds_no_blocker() -> None:
    applicant = obs(1, Source.APPLICANT, "mfa", True, timedelta(days=94))
    posture = obs(3, Source.POSTURE, "mfa", True, timedelta(minutes=18))
    assert decide([FRESH_BACKUPS, applicant, posture], AS_OF).blockers == ()


def test_unknown_rule_set_version_is_rejected() -> None:
    with pytest.raises(ValueError):
        decide([], AS_OF, "v0")


def test_naive_datetimes_are_rejected() -> None:
    naive = AS_OF.replace(tzinfo=None)
    with pytest.raises(ValueError):
        decide([], naive)


def test_duplicate_ids_are_rejected() -> None:
    with pytest.raises(ValueError):
        decide([FRESH_BACKUPS, FRESH_BACKUPS], AS_OF)
