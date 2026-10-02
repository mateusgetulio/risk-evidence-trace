import { contributionKey, signed } from "@/lib/labels";
import type { Contribution, Decision } from "@/lib/types";
import { DeveloperDetails } from "./DeveloperDetails";

type Props = {
  decision: Decision | null;
  selectedKey: string | null;
  onSelect: (key: string | null) => void;
};

function ContributionRow({
  c,
  selected,
  onSelect,
}: {
  c: Contribution;
  selected: boolean;
  onSelect: () => void;
}) {
  const classes = ["row", selected ? "selected" : "", c.changed ? "changed" : ""].join(" ");
  return (
    <li>
      <button
        type="button"
        className={classes}
        aria-pressed={selected}
        onClick={onSelect}
        data-testid={`contribution-${c.ruleId}`}
      >
        <span className="rule-id">{c.ruleId}</span>
        <span className="reason">
          {c.reason}
          {c.changed ? <span className="tag tag-changed">Changed</span> : null}
        </span>
        <span className="points">{signed(c.points)}</span>
        <span className="evidence-ref">
          {c.observationId === null ? "Missing evidence" : `Evidence #${c.observationId}`}
        </span>
      </button>
    </li>
  );
}

export function DecisionColumn({ decision, selectedKey, onSelect }: Props) {
  if (!decision) {
    return (
      <section className="column" aria-labelledby="decision-heading">
        <h2 id="decision-heading">Decision</h2>
        <p className="muted">No decision yet. The worker is still computing it.</p>
      </section>
    );
  }
  const selected = decision.contributions.find(
    (c) => contributionKey(c.ruleId, c.observationId) === selectedKey,
  );
  const flipped = decision.previousOutcome !== null && decision.previousOutcome !== decision.outcome;
  return (
    <section className="column" aria-labelledby="decision-heading">
      <h2 id="decision-heading">Decision</h2>
      <div className="outcome-block">
        <span className={`badge badge-${decision.outcome.toLowerCase()}`} data-testid="outcome">
          {decision.outcome}
        </span>
        <span className="total" data-testid="total-points">
          {decision.totalPoints} points
        </span>
      </div>
      {flipped ? (
        <p className="flip" data-testid="flip">
          Changed from {decision.previousOutcome} ({decision.previousPoints} points)
        </p>
      ) : null}

      <ul className="rows">
        {decision.contributions.map((c) => {
          const key = contributionKey(c.ruleId, c.observationId);
          return (
            <ContributionRow
              key={key}
              c={c}
              selected={key === selectedKey}
              onSelect={() => onSelect(key === selectedKey ? null : key)}
            />
          );
        })}
      </ul>

      {selected ? (
        <div className="rule-panel" data-testid="rule-panel">
          <div className="rule-panel-title">Rule {selected.ruleId}</div>
          <p>{selected.ruleText}</p>
          <p className="muted">
            {selected.observationId === null
              ? "This rule applied because no evidence was received."
              : `Caused by evidence #${selected.observationId}, highlighted on the left.`}
          </p>
        </div>
      ) : (
        <p className="muted hint">Click a row to see the evidence and the rule behind it.</p>
      )}

      {decision.removed.length > 0 ? (
        <div className="removed">
          <h3>No longer applies</h3>
          <ul>
            {decision.removed.map((c) => (
              <li key={contributionKey(c.ruleId, c.observationId)}>
                <span className="rule-id">{c.ruleId}</span> {c.reason}{" "}
                <s>{signed(c.points)}</s>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {decision.blockers.length > 0 ? (
        <div className="blockers">
          <h3>Needs review</h3>
          <ul>
            {decision.blockers.map((b) => (
              <li key={`${b.kind}-${b.observationId}`}>
                Evidence #{b.observationId}: {b.reason}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <DeveloperDetails />
    </section>
  );
}
