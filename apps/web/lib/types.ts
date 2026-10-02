export type Observation = {
  id: number;
  source: "applicant" | "external_scan" | "posture";
  sourceObservationId: string;
  subject: string;
  claim: "mfa" | "critical_exposed_vuln" | "backups_tested" | "ransomware_indicator";
  value: boolean;
  observedAt: string;
  ageSeconds: number;
  stale: boolean;
  supersededBy: number | null;
};

export type Contribution = {
  ruleId: string;
  points: number;
  observationId: number | null;
  reason: string;
  missingEvidence: boolean;
  ruleText: string;
  changed: boolean;
};

export type Blocker = { kind: string; observationId: number; reason: string };
export type Superseded = { observationId: number; supersededBy: number };

export type Decision = {
  runId: number | null;
  asOf: string;
  inputHash: string;
  outcome: "QUOTE" | "REFER" | "DECLINE";
  totalPoints: number;
  previousOutcome: string | null;
  previousPoints: number | null;
  contributions: Contribution[];
  removed: Contribution[];
  blockers: Blocker[];
  superseded: Superseded[];
};

export type Submission = {
  id: number;
  companyName: string;
  primaryDomain: string;
  status: string;
  asOf: string;
  pendingJobs: number;
  observations: Observation[];
  decision: Decision | null;
};

export type TimelineEvent = { id: number; at: string; kind: string; message: string };

export type PageData = { submission: Submission | null; timeline: TimelineEvent[] };
