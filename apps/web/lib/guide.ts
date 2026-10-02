export const ACME_ID = 1;
export const HARBOR_ID = 2;

export type StepAction =
  | { kind: "reset" }
  | { kind: "fixture"; fixture: string }
  | { kind: "send" };

export type GuideStep = {
  number: number;
  title: string;
  submissionId: number;
  caption: string;
  action: StepAction;
};

export const STEPS: GuideStep[] = [
  {
    number: 1,
    title: "Submission",
    submissionId: ACME_ID,
    caption:
      "Acme Manufacturing applies: the security posture provider verified MFA and backups tested 85 days ago lower the risk, so the decision is QUOTE.",
    action: { kind: "reset" },
  },
  {
    number: 2,
    title: "Late scan",
    submissionId: ACME_ID,
    caption:
      "A late external scan finds a critical vulnerability on vpn.acme.test, the worker recomputes and the decision flips to REFER: click the highlighted row to see the evidence and the rule behind it.",
    action: { kind: "fixture", fixture: "acme_late_scan" },
  },
  {
    number: 3,
    title: "Who do we believe?",
    submissionId: ACME_ID,
    caption:
      "Time moved forward 6 days: the posture provider still wins the MFA disagreement over the scan and the applicant, but the backup attestation is now 91 days old, so it can no longer lower risk and needs review.",
    action: { kind: "fixture", fixture: "acme_time_passes" },
  },
  {
    number: 4,
    title: "Carrier timeout",
    submissionId: HARBOR_ID,
    caption:
      "Harbor Dental Group is a clean QUOTE, so we send it to the carrier partner: the first attempt times out, and the worker schedules one automatic retry with the same idempotency key.",
    action: { kind: "send" },
  },
  {
    number: 5,
    title: "No duplicate",
    submissionId: HARBOR_ID,
    caption:
      "The retry goes out now with the same idempotency key: the carrier had already recorded the first attempt, so it returns its original acknowledgement and the quote exists only once.",
    action: { kind: "send" },
  },
];
