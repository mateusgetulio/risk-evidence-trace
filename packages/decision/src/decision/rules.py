from __future__ import annotations

from datetime import timedelta

from decision.models import Source

RULE_SET_VERSION = "v1"

FRESHNESS: dict[Source, timedelta] = {
    Source.APPLICANT: timedelta(days=90),
    Source.EXTERNAL_SCAN: timedelta(days=30),
    Source.POSTURE: timedelta(days=7),
}

SOURCE_RANK: dict[Source, int] = {
    Source.POSTURE: 0,
    Source.EXTERNAL_SCAN: 1,
    Source.APPLICANT: 2,
}

EX_POINTS = 20
RA_POINTS = 15
BK_UNVERIFIED_POINTS = 10
BK_VERIFIED_POINTS = -5
REFER_THRESHOLD = 15

CLAIM_VULN = "critical_exposed_vuln"
CLAIM_MFA = "mfa"
CLAIM_BACKUPS = "backups_tested"
CLAIM_RANSOMWARE = "ransomware_indicator"

RULE_TEXT: dict[str, str] = {
    "EX-01": "A critical internet-exposed vulnerability adds 20 points.",
    "RA-01": "Remote access without multi-factor authentication adds 15 points.",
    "BK-01": "Backups that are missing, not verified or stale add 10 points.",
    "BK-02": "Recent verified backups remove 5 points.",
    "HD-01": "An active ransomware indicator means DECLINE, whatever the points.",
}
