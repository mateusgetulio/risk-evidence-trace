import type { Observation } from "./types";

export const SOURCE_LABEL: Record<Observation["source"], string> = {
  applicant: "Applicant",
  external_scan: "External scan provider",
  posture: "Security posture provider",
};

export const FRESHNESS_DAYS: Record<Observation["source"], number> = {
  applicant: 90,
  external_scan: 30,
  posture: 7,
};

export const CLAIM_TITLE: Record<Observation["claim"], string> = {
  mfa: "MFA on remote access",
  critical_exposed_vuln: "Critical exposed vulnerability",
  backups_tested: "Backups tested",
  ransomware_indicator: "Ransomware indicator",
};

export const VALUE_TEXT: Record<Observation["claim"], { yes: string; no: string }> = {
  mfa: { yes: "MFA in place", no: "No MFA observed" },
  critical_exposed_vuln: { yes: "Found", no: "None found" },
  backups_tested: { yes: "Yes", no: "No" },
  ransomware_indicator: { yes: "Active", no: "None" },
};

export function formatAge(seconds: number): string {
  const minutes = Math.round(seconds / 60);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.round(hours / 24);
  return `${days} days ago`;
}

export function signed(points: number): string {
  return points > 0 ? `+${points}` : `${points}`;
}

export function contributionKey(ruleId: string, observationId: number | null): string {
  return `${ruleId}:${observationId ?? "missing"}`;
}

export const REFER_THRESHOLD = 15;

export function describeTotal(
  outcome: "QUOTE" | "REFER" | "DECLINE",
  total: number,
  blockerCount: number,
): string {
  if (outcome === "DECLINE") return "Decline rule HD-01 applies whatever the points are.";
  if (total >= REFER_THRESHOLD) {
    return `At or above the ${REFER_THRESHOLD} point refer threshold.`;
  }
  const base = `Below the ${REFER_THRESHOLD} point refer threshold`;
  if (blockerCount > 0) return `${base}, but a review blocker forces REFER.`;
  if (total < 0) return `${base}. Negative points mean verified evidence lowered the risk.`;
  return `${base}.`;
}
