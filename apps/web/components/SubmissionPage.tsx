"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { contributionKey } from "@/lib/labels";
import { useSubmission } from "@/lib/useSubmission";
import { ActionBar } from "./ActionBar";
import { DecisionColumn } from "./DecisionColumn";
import { EvidenceColumn } from "./EvidenceColumn";
import { TimelineColumn } from "./TimelineColumn";

const APPLICANTS = [
  { id: 1, label: "Acme Manufacturing" },
  { id: 2, label: "Harbor Dental Group" },
];

export function SubmissionPage({ id }: { id: number }) {
  const { data, error, busy, deliverFixture, resetDemo } = useSubmission(id);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);

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
        {submission ? (
          <ActionBar
            domain={submission.primaryDomain}
            busy={busy}
            onDeliverScan={() => void deliverFixture("acme_late_scan")}
            onReset={() => void resetDemo()}
          />
        ) : null}
      </header>

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
          <DecisionColumn decision={decision} selectedKey={selectedKey} onSelect={setSelectedKey} />
          <TimelineColumn events={data?.timeline ?? []} pending={submission.pendingJobs > 0} />
        </div>
      ) : error ? null : (
        <p className="muted">Loading...</p>
      )}
    </main>
  );
}
