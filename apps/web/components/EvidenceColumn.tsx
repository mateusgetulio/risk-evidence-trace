import { CLAIM_TITLE, FRESHNESS_DAYS, SOURCE_LABEL, VALUE_TEXT, formatAge } from "@/lib/labels";
import type { Decision, Observation } from "@/lib/types";

type Props = {
  observations: Observation[];
  decision: Decision | null;
  selectedObservationId: number | null;
  missingSelected: boolean;
};

function ObservationCard({ obs, selected }: { obs: Observation; selected: boolean }) {
  const superseded = obs.supersededBy !== null;
  const classes = ["card", selected ? "selected" : "", superseded ? "superseded" : ""].join(" ");
  return (
    <li className={classes} id={`observation-${obs.id}`} data-testid={`observation-${obs.id}`}>
      <div className="card-top">
        <span className="source">{SOURCE_LABEL[obs.source]}</span>
        <span className="id">#{obs.id}</span>
      </div>
      <div className="card-title">{CLAIM_TITLE[obs.claim]}</div>
      <div className="card-value">
        {obs.value ? VALUE_TEXT[obs.claim].yes : VALUE_TEXT[obs.claim].no}
        <span className="subject"> on {obs.subject.replace("_", " ")}</span>
      </div>
      <div className="card-meta">
        <span>Observed {formatAge(obs.ageSeconds)}</span>
        {obs.stale ? (
          <span className="tag tag-stale">Stale after {FRESHNESS_DAYS[obs.source]} days</span>
        ) : (
          <span className="tag tag-fresh">Fresh</span>
        )}
        {superseded ? <span className="tag tag-superseded">Superseded by #{obs.supersededBy}</span> : null}
      </div>
    </li>
  );
}

export function EvidenceColumn({ observations, decision, selectedObservationId, missingSelected }: Props) {
  const missing = decision?.contributions.filter((c) => c.missingEvidence) ?? [];
  return (
    <section className="column" aria-labelledby="evidence-heading">
      <h2 id="evidence-heading">Evidence</h2>
      <ul className="cards">
        {observations.map((obs) => (
          <ObservationCard key={obs.id} obs={obs} selected={selectedObservationId === obs.id} />
        ))}
        {missing.map((c) => (
          <li
            key={c.ruleId}
            className={`card missing ${missingSelected ? "selected" : ""}`}
            data-testid="missing-evidence"
          >
            <div className="card-top">
              <span className="source">Missing evidence</span>
            </div>
            <div className="card-title">Backups tested</div>
            <div className="card-value">{c.reason}</div>
          </li>
        ))}
      </ul>
    </section>
  );
}
