# Tradeoffs

What was left out on purpose, and what it would take to add.

## Dead letter and replay

A job that fails 5 times stays in the `jobs` table and is no longer claimed. Nothing alerts on it, and there is no tool to inspect it or run it again. A real version would move it to a dead letter table or queue with the last error, page someone, and offer a replay that keeps the original idempotency key so a replay can never double a business effect.

For carrier sends the same applies one level up. A `failed` transmission waits for a person to press "Send again". With many partners that becomes a queue of failed transmissions with a reason, an owner and a retry policy per partner.

## Backoff and jitter

The carrier send retries once after a fixed delay, and other failed jobs come back after a fixed 2 seconds. Under a real outage that would hammer the partner. The fix is exponential backoff with full jitter, a cap, and a circuit breaker per partner so one slow carrier does not tie up workers meant for others.

## More carrier failure modes

The simulator covers a timeout with the effect recorded, and the tests cover a carrier that is unreachable. Not covered:

- a carrier that rejects the quote with a validation error the underwriter must fix
- a carrier that accepts the quote but sends the real answer later through a callback
- a timeout where the carrier did not record anything
- duplicate callbacks
- a partner that changes its API version

Each needs its own state in `transmissions` and its own line in the timeline.

## A graph store for asset relationships

Subjects are plain strings such as `remote_access` or `vpn.acme.test`. Real exposure data is a graph: domains, hosts, certificates, subsidiaries and shared infrastructure between applicants. Questions like "which other applicants sit behind this exposed VPN appliance" need that graph. Postgres with a relationships table goes a long way before a dedicated graph store is worth it.

## A managed queue

The jobs table with `FOR UPDATE SKIP LOCKED` keeps the job and the data change in one transaction, which is what makes the outbox correct without extra machinery. A managed queue such as SQS removes polling load from the database and brings a dead letter queue. It also needs an outbox relay to keep that same guarantee. It becomes worth it once the queue depth or the number of workers grows.

## Time-travel UI

`as_of` is an argument of the engine and of `decisionTrace`, and it is tested. The page has no control for it, because the core interaction is "new evidence changes the decision", and a date picker would compete with that. A future version could show a run history and let an underwriter open any past run, which the stored input ids and hash already support.

## An LLM explanation layer

An LLM could turn a finished trace into a paragraph for an underwriter or a broker. If added, it sits outside the decision path. It reads a stored decision run and may summarize it, but it never decides, never changes points, and its text is never an input to `decide()`. The trace stays the source of truth, and the summary is labelled as generated.

## Smaller choices worth knowing

- **Scenario clock instead of wall clock.** Decisions are taken as of a per-submission clock so the demo is reproducible. With real time, evidence that crosses a freshness window needs a scheduled re-check, because no new evidence arrives to trigger a recompute.
- **`as_of` filters on `observed_at` only.** A fully bitemporal version would also filter on `received_at`, to answer "what did we know at that time" as well as "what was true at that time".
- **Carrier mode lives in the API process.** Fine for one API process; several processes would need the mode in the database.
- **Precedence ignores freshness.** A stale posture observation still wins over a fresh scan. The stale all-clear rule in [architecture.md](architecture.md) keeps that from hiding risk, and the blocker sends it to review.
- **The demo's submission ids are fixed.** The page links to submissions 1 and 2, which is what the seed creates.
