"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { graphql, recordOperation } from "./api";
import { DELIVER_FIXTURE, PAGE_QUERY, RESET_DEMO, SEND_TO_CARRIER } from "./queries";
import type { PageData } from "./types";

const POLL_MS = 1500;

export function useSubmission(id: number) {
  const [loaded, setLoaded] = useState<{ id: number; page: PageData | null } | null>(null);
  const data = loaded?.id === id ? loaded.page : null;
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const alive = useRef(true);

  const load = useCallback(
    async (background: boolean) => {
      try {
        const result = await graphql<PageData>("Page", PAGE_QUERY, { id });
        if (!alive.current) return;
        if (result.errors?.length) {
          setError(result.errors[0].message);
          return;
        }
        const pending = result.data?.submission?.pendingJobs ?? 0;
        if (!background || pending === 0) recordOperation(result.operation);
        setLoaded({ id, page: result.data });
        setError(null);
      } catch {
        if (alive.current) setError("Could not reach the API. Is it running?");
      }
    },
    [id],
  );

  useEffect(() => {
    alive.current = true;
    const timer = setTimeout(() => void load(false), 0);
    return () => {
      clearTimeout(timer);
      alive.current = false;
    };
  }, [load]);

  const waitingForRetry = data?.submission?.transmission?.nextRetryAt ? 1 : 0;
  const pending = (data?.submission?.pendingJobs ?? 0) + waitingForRetry;
  useEffect(() => {
    if (pending === 0) return;
    const timer = setTimeout(() => void load(true), POLL_MS);
    return () => clearTimeout(timer);
  }, [pending, data, load]);

  const run = useCallback(
    async (name: string, query: string, variables: Record<string, unknown>) => {
      setBusy(true);
      try {
        const result = await graphql(name, query, variables);
        recordOperation(result.operation);
        if (result.errors?.length) setError(result.errors[0].message);
        await load(true);
      } catch {
        setError("Could not reach the API. Is it running?");
      } finally {
        setBusy(false);
      }
    },
    [load],
  );

  const deliverFixture = useCallback(
    (fixture: string) => run("DeliverFixture", DELIVER_FIXTURE, { id, fixture }),
    [id, run],
  );
  const sendToCarrier = useCallback(
    () => run("SendToCarrier", SEND_TO_CARRIER, { id }),
    [id, run],
  );
  const resetDemo = useCallback(() => run("ResetDemo", RESET_DEMO, {}), [run]);

  return { data, error, busy, run, deliverFixture, sendToCarrier, resetDemo };
}
