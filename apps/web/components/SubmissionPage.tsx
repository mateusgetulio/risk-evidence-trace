"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { STEPS, type GuideStep } from "@/lib/guide";
import { DELIVER_FIXTURE, RESET_DEMO, SEND_TO_CARRIER } from "@/lib/queries";
import { contributionKey } from "@/lib/labels";
import { useSubmission } from "@/lib/useSubmission";
import { ActionBar } from "./ActionBar";
import { DecisionColumn } from "./DecisionColumn";
import { GuidedBar } from "./GuidedBar";
import { EvidenceColumn } from "./EvidenceColumn";
import { TimelineColumn } from "./TimelineColumn";

const APPLICANTS = [
  { id: 1, label: "Acme Manufacturing" },
  { id: 2, label: "Harbor Dental Group" },
];

export function SubmissionPage({ id, step }: { id: number; step: number | null }) {
  const { data, error, busy, run, deliverFixture, sendToCarrier, resetDemo } = useSubmission(id);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const router = useRouter();

  const runStep = useCallback(
    async (target: GuideStep) => {
      const action = target.action;
      if (action.kind === "reset") {
        await run("ResetDemo", RESET_DEMO, {});
      } else if (action.kind === "fixture") {
        await run("DeliverFixture", DELIVER_FIXTURE, {
          id: target.submissionId,
          fixture: action.fixture,
        });
      } else {
        await run("SendToCarrier", SEND_TO_CARRIER, { id: target.submissionId });
      }
      setSelectedKey(null);
      router.push(`/submissions/${target.submissionId}?step=${target.number}`);
    },
    [run, router],
  );

  const startGuide = () => void runStep(STEPS[0]);
  const nextStep = () => {
    const next = STEPS.find((s) => s.number === (step ?? 0) + 1);
    if (next) void runStep(next);
  };
  const exitGuide = () => router.push(`/submissions/${id}`);

  const submission = data?.submission ?? null;
  const decision = submission?.decision ?? null;
  const selected = decision?.contributions.find(
    (c) => contributionKey(c.ruleId, c.observationId) === selectedKey,
  );

  useEffect(() => {
    if (selected?.observationId) {
      document
        .getElementById(`observation-${selected.observationId}`)
        ?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }, [selected]);

  return (
    <main className="page">
      <header className="top">
        <div>
          <h1>{submission ? submission.companyName : "Risk Evidence Trace"}</h1>
          {submission ? <p className="muted">{submission.primaryDomain}</p> : null}
        </div>
        <nav aria-label="Applicants" className="switcher">
          {APPLICANTS.map((a) => (
            <Link key={a.id} href={`/submissions/${a.id}`} aria-current={a.id === id ? "page" : undefined}>
              {a.label}
            </Link>
          ))}
        </nav>
        <button
          type="button"
          className="toggle"
          aria-pressed={step !== null}
          onClick={step === null ? startGuide : exitGuide}
          disabled={busy}
        >
          {step === null ? "Guided demo" : "Exit guided demo"}
        </button>
        {submission ? (
          <ActionBar
            domain={submission.primaryDomain}
            busy={busy}
            isQuote={decision?.outcome === "QUOTE"}
            transmission={submission.transmission}
            onSend={() => void sendToCarrier()}
            onDeliverScan={() => void deliverFixture("acme_late_scan")}
            onReset={() => void resetDemo()}
          />
        ) : null}
      </header>

      {step !== null ? (
        <GuidedBar
          step={step}
          busy={busy || (submission?.pendingJobs ?? 0) > 0}
          onNext={nextStep}
          onRestart={startGuide}
        />
      ) : null}

      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}

      {submission ? (
        <div className="columns">
          <EvidenceColumn
            observations={submission.observations}
            decision={decision}
            selectedObservationId={selected?.observationId ?? null}
            missingSelected={selected?.missingEvidence ?? false}
          />
          <DecisionColumn
            decision={decision}
            transmission={submission.transmission}
            selectedKey={selectedKey}
            onSelect={setSelectedKey}
          />
          <TimelineColumn events={data?.timeline ?? []} pending={submission.pendingJobs > 0} />
        </div>
      ) : error ? null : (
        <p className="muted">Loading...</p>
      )}
    </main>
  );
}
