from __future__ import annotations

from datetime import UTC, datetime, timedelta

from decision import Observation, Source
from hypothesis import strategies as st

AS_OF = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)

CLAIM_SUBJECTS = {
    "mfa": ["remote_access", "vpn.acme.test"],
    "critical_exposed_vuln": ["vpn.acme.test", "mail.acme.test"],
    "backups_tested": ["backups"],
    "ransomware_indicator": ["acme.test"],
}


@st.composite
def observation_lists(draw: st.DrawFn, max_size: int = 12) -> list[Observation]:
    count = draw(st.integers(min_value=0, max_value=max_size))
    observations: list[Observation] = []
    for index in range(count):
        claim = draw(st.sampled_from(sorted(CLAIM_SUBJECTS)))
        subject = draw(st.sampled_from(CLAIM_SUBJECTS[claim]))
        source = draw(st.sampled_from(list(Source)))
        value = draw(st.booleans())
        age_minutes = draw(st.integers(min_value=0, max_value=60 * 24 * 150))
        observations.append(
            Observation(
                id=index + 1,
                source=source,
                subject=subject,
                claim=claim,
                value=value,
                observed_at=AS_OF - timedelta(minutes=age_minutes),
            )
        )
    return observations
