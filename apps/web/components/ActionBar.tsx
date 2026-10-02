type Props = {
  domain: string;
  busy: boolean;
  onDeliverScan: () => void;
  onReset: () => void;
};

const SCAN_FIXTURE_DOMAINS = new Set(["acme.test"]);

export function ActionBar({ domain, busy, onDeliverScan, onReset }: Props) {
  const scanAvailable = SCAN_FIXTURE_DOMAINS.has(domain);
  return (
    <div className="actions" role="toolbar" aria-label="Actions">
      <button
        type="button"
        className="primary"
        onClick={onDeliverScan}
        disabled={busy || !scanAvailable}
        title={scanAvailable ? undefined : "This applicant has no late scan in the scenario"}
      >
        Deliver external scan
      </button>
      <button type="button" onClick={onReset} disabled={busy}>
        Reset demo
      </button>
    </div>
  );
}
