from __future__ import annotations

from datetime import timedelta

from conftest import AS_OF, observation_lists
from decision import RULE_SET_VERSION, Observation, Outcome, Source, decide, input_hash
from decision.rules import FRESHNESS
from hypothesis import given, settings
from hypothesis import strategies as st

SEVERITY = {Outcome.QUOTE: 0, Outcome.REFER: 1, Outcome.DECLINE: 2}


@given(observation_lists())
def test_same_inputs_give_same_decision_and_hash(observations: list[Observation]) -> None:
    first = decide(observations, AS_OF, RULE_SET_VERSION)
    second = decide(list(observations), AS_OF, RULE_SET_VERSION)
    ids = [o.id for o in observations]
    assert first == second
    assert input_hash(ids, AS_OF, RULE_SET_VERSION) == input_hash(ids, AS_OF, RULE_SET_VERSION)


def test_hash_changes_when_any_input_changes() -> None:
    base = input_hash([1, 2], AS_OF, RULE_SET_VERSION)
    assert base != input_hash([1, 2, 3], AS_OF, RULE_SET_VERSION)
    assert base != input_hash([1, 2], AS_OF + timedelta(seconds=1), RULE_SET_VERSION)
    assert base != input_hash([1, 2], AS_OF, "v2")
    assert base == input_hash([2, 1], AS_OF, RULE_SET_VERSION)


@given(observation_lists())
def test_contribution_points_sum_to_total(observations: list[Observation]) -> None:
    decision = decide(observations, AS_OF)
    assert sum(c.points for c in decision.contributions) == decision.total_points


@given(observation_lists(), st.integers(min_value=1, max_value=60 * 24 * 120))
def test_advancing_time_never_lowers_risk(
    observations: list[Observation], extra_minutes: int
) -> None:
    now = decide(observations, AS_OF)
    later = decide(observations, AS_OF + timedelta(minutes=extra_minutes))
    assert later.total_points >= now.total_points
    assert SEVERITY[later.outcome] >= SEVERITY[now.outcome]
    assert len(later.blockers) >= len(now.blockers)


@given(
    observation_lists(),
    st.sampled_from(list(Source)),
    st.sampled_from(["mfa", "critical_exposed_vuln", "backups_tested", "ransomware_indicator"]),
    st.booleans(),
    st.integers(min_value=1, max_value=60 * 24 * 30),
)
def test_adding_a_stale_observation_never_lowers_risk(
    observations: list[Observation],
    source: Source,
    claim: str,
    value: bool,
    extra_minutes: int,
) -> None:
    subject = {"mfa": "remote_access", "backups_tested": "backups"}.get(claim, "vpn.acme.test")
    stale = Observation(
        id=1000,
        source=source,
        subject=subject,
        claim=claim,
        value=value,
        observed_at=AS_OF - FRESHNESS[source] - timedelta(minutes=extra_minutes),
    )
    before = decide(observations, AS_OF)
    after = decide([*observations, stale], AS_OF)
    assert after.total_points >= before.total_points
    assert SEVERITY[after.outcome] >= SEVERITY[before.outcome]


@given(observation_lists())
def test_stale_observations_never_carry_negative_points(observations: list[Observation]) -> None:
    decision = decide(observations, AS_OF)
    stale_ids = {b.observation_id for b in decision.blockers}
    for contribution in decision.contributions:
        if contribution.observation_id in stale_ids:
            assert contribution.points >= 0


@settings(max_examples=200)
@given(observation_lists(), st.randoms(use_true_random=False))
def test_arrival_order_never_changes_the_decision(
    observations: list[Observation], rng: object
) -> None:
    expected = decide(observations, AS_OF)
    for _ in range(5):
        shuffled = list(observations)
        rng.shuffle(shuffled)  # type: ignore[attr-defined]
        assert decide(shuffled, AS_OF) == expected
