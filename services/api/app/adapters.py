from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol

from decision import Source


@dataclass(frozen=True)
class IncomingObservation:
    source: Source
    source_observation_id: str
    subject: str
    claim: str
    value: bool
    observed_at: datetime
    raw: dict[str, Any]


class ProviderAdapter(Protocol):
    source: Source

    def read(
        self, records: list[dict[str, Any]], origin: datetime, primary_domain: str
    ) -> list[IncomingObservation]: ...


class ApplicantAdapter:
    source = Source.APPLICANT

    CONTROLS = {
        "mfa_remote_access": ("remote_access", "mfa"),
        "backups_tested": ("backups", "backups_tested"),
    }

    def read(
        self, records: list[dict[str, Any]], origin: datetime, primary_domain: str
    ) -> list[IncomingObservation]:
        result: list[IncomingObservation] = []
        for record in records:
            subject, claim = self.CONTROLS[record["control"]]
            result.append(
                IncomingObservation(
                    source=self.source,
                    source_observation_id=record["attestation_id"],
                    subject=subject,
                    claim=claim,
                    value=record["answer"] == "yes",
                    observed_at=origin - timedelta(days=record["attested_days_ago"]),
                    raw=record,
                )
            )
        return result


class ExternalScanAdapter:
    source = Source.EXTERNAL_SCAN

    def read(
        self, records: list[dict[str, Any]], origin: datetime, primary_domain: str
    ) -> list[IncomingObservation]:
        result: list[IncomingObservation] = []
        for record in records:
            kind = record["kind"]
            if kind == "critical_vulnerability":
                subject, claim, value = record["host"], "critical_exposed_vuln", record["detected"]
            elif kind == "login_mfa":
                subject, claim, value = "remote_access", "mfa", record["mfa_observed"]
            elif kind == "ransomware_indicator":
                subject, claim, value = primary_domain, "ransomware_indicator", record["detected"]
            else:
                raise ValueError(f"unknown scan finding kind: {kind}")
            result.append(
                IncomingObservation(
                    source=self.source,
                    source_observation_id=record["finding_id"],
                    subject=subject,
                    claim=claim,
                    value=bool(value),
                    observed_at=origin - timedelta(hours=record["seen_hours_ago"]),
                    raw=record,
                )
            )
        return result


class PostureAdapter:
    source = Source.POSTURE

    CONTROLS = {
        "mfa": ("remote_access", "mfa"),
        "backups": ("backups", "backups_tested"),
    }

    def read(
        self, records: list[dict[str, Any]], origin: datetime, primary_domain: str
    ) -> list[IncomingObservation]:
        result: list[IncomingObservation] = []
        for record in records:
            subject, claim = self.CONTROLS[record["control"]]
            result.append(
                IncomingObservation(
                    source=self.source,
                    source_observation_id=record["check_id"],
                    subject=subject,
                    claim=claim,
                    value=record["status"] == "verified",
                    observed_at=origin - timedelta(minutes=record["checked_minutes_ago"]),
                    raw=record,
                )
            )
        return result


ADAPTERS: dict[str, ProviderAdapter] = {
    "applicant": ApplicantAdapter(),
    "external_scan": ExternalScanAdapter(),
    "posture": PostureAdapter(),
}
