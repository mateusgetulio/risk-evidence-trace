import { STEPS } from "@/lib/guide";

type Props = {
  step: number;
  busy: boolean;
  onNext: () => void;
  onRestart: () => void;
};

export function GuidedBar({ step, busy, onNext, onRestart }: Props) {
  const current = STEPS.find((s) => s.number === step) ?? STEPS[0];
  const last = step >= STEPS.length;
  return (
    <section className="guide" aria-label="Guided demo">
      <ol className="steps">
        {STEPS.map((s) => (
          <li
            key={s.number}
            className={s.number === step ? "current" : s.number < step ? "done" : ""}
            aria-current={s.number === step ? "step" : undefined}
          >
            <span className="step-number">{s.number}</span> {s.title}
          </li>
        ))}
      </ol>
      <div className="guide-body">
        <p className="caption" data-testid="caption">
          {current.caption}
        </p>
        {last ? (
          <button type="button" onClick={onRestart} disabled={busy}>
            Start over
          </button>
        ) : (
          <button type="button" className="primary" onClick={onNext} disabled={busy}>
            Next step
          </button>
        )}
      </div>
    </section>
  );
}
