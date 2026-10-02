import type { Transmission } from "@/lib/types";

type Props = {
  domain: string;
  busy: boolean;
  isQuote: boolean;
  transmission: Transmission | null;
  onDeliverScan: () => void;
  onSend: () => void;
  onReset: () => void;
};

const SCAN_FIXTURE_DOMAINS = new Set(["acme.test"]);

export function ActionBar({
  domain,
  busy,
  isQuote,
  transmission,
  onDeliverScan,
  onSend,
  onReset,
}: Props) {
  const scanAvailable = SCAN_FIXTURE_DOMAINS.has(domain);
  const inFlight = transmission?.state === "pending";
  const canSend = isQuote && !transmission;
  const canSendAgain = transmission !== null && transmission.state !== "pending";
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
      <button
        type="button"
        className="primary"
        onClick={onSend}
        disabled={busy || inFlight || !canSend}
        title={isQuote ? undefined : "Only a QUOTE decision can be sent to the carrier"}
      >
        Send quote to carrier
      </button>
      <button type="button" onClick={onSend} disabled={busy || inFlight || !canSendAgain}>
        Send again
      </button>
      <button type="button" onClick={onReset} disabled={busy}>
        Reset demo
      </button>
    </div>
  );
}
