# Architecture

This page explains how the pieces fit and why each decision was made. The README has the short version.

## Components

| Path | What it is |
|---|---|
| `packages/decision` | The decision engine. Pure Python, standard library only, no I/O. |
| `services/api/app` | FastAPI app: GraphQL API, provider adapters, ingestion, the worker and the carrier simulator. |
| `apps/web` | One Next.js page, `/submissions/[id]`. |
| `fixtures/` | Scenario observations, one JSON file per delivery. |

The API and the worker are the same Python package started two ways: `uvicorn app.main:app` and `python -m app.worker`.

## The decision engine

```
decide(observations, as_of, rule_set_version) -> Decision(outcome, total_points, contributions, blockers, superseded)
input_hash(observation_ids, as_of, rule_set_version) -> str
```

The engine is a function of its inputs and nothing else. An architecture test parses every module in `packages/decision` and fails on any import outside a short allowlist of standard library modules, and on calls such as `open`, `eval` or `print`.

How a decision is built:

1. **Known at `as_of`.** Observations with `observed_at` after `as_of` are ignored.
2. **Precedence.** Observations are grouped by subject and claim. In each group the winner is the highest ranked source (posture, then external scan, then applicant), and within a source the newest `observed_at`. Ties break on the observation id, so the result never depends on input order. The losers are kept and reported as superseded by the winner.
3. **Freshness.** Each source has a window: applicant 90 days, external scan 30 days, posture 7 days. A winner older than its window is stale. It creates a needs-review blocker, and it can add risk but never reduce it.
4. **Stale all-clear.** If a stale winner says "no risk" (for example MFA in place) while a lower ranked observation in the same group reports risk, the risk still counts, attributed to that lower observation. Without this, an old all-clear could hide a fresh finding or cancel a DECLINE.
5. **Rules.** EX-01, RA-01 and HD-01 apply per winning observation. Backups produce exactly one contribution: BK-01 when any backups winner is false or stale, or when there is no backups evidence at all, otherwise BK-02.
6. **Missing evidence.** When there is no backups observation, BK-01 still applies. Its contribution has no observation id and is flagged `missing_evidence`, and the UI shows it as its own card.
7. **Outcome.** HD-01 means DECLINE. Otherwise 15 points or more, or any blocker, means REFER. Everything else is QUOTE, including negative totals.

Every contribution carries `rule_id`, `points`, `observation_id` and `reason`, and the points always sum to the total.

The input hash is a SHA-256 over the sorted observation ids, `as_of` in UTC and the rule set version. Callers hash exactly the list they pass to the engine.

## Storage

Postgres tables follow the spec, plus two additions:

- `submissions.clock_origin` and `submissions.clock_offset_days` hold the scenario clock (see below).
- `decision_runs.superseded` stores which observation superseded which, so the page can label cards from a stored run instead of recomputing.

`observations`, `decision_runs` and `audit_events` are append-only. Database triggers reject `UPDATE` and `DELETE` on them. Only the demo reset and the seed command clear them, with `TRUNCATE`, and both refuse to run unless `DEMO_MODE=1`.

Observations are unique on `(source, source_observation_id)`.

## Ingestion and the scenario clock

Each provider has an adapter with the same interface. Each adapter reads that provider's own fixture shape: applicant attestations in days, scan findings in hours, posture checks in minutes. It turns them into the common observation shape.

`deliverFixture` runs in one transaction:

1. It locks the submission.
2. It inserts the new observations with `ON CONFLICT DO NOTHING`.
3. It moves the scenario clock forward if the fixture asks for it.
4. It writes audit events.
5. It enqueues one `recompute_decision` job, but only if something changed.

Delivering the same fixture twice changes nothing.

Each submission has a scenario clock: `clock_origin` (set when it is seeded) plus `clock_offset_days`. Fixture ages are relative to `clock_origin`, and decisions are taken as of the clock. Step 3 of the demo sets the offset to 6 days. Advancing it is idempotent, because the fixture states a target offset, not an increment. This keeps the demo reproducible no matter when it runs.

## Worker and jobs

The worker claims one job at a time with `UPDATE ... WHERE id = (SELECT ... FOR UPDATE SKIP LOCKED LIMIT 1)`.

- It sets `locked_at` and increments `attempts`.
- On success the job is deleted.
- On error it is released with a short delay.
- A lock older than 60 seconds can be reclaimed, so a crashed worker does not strand a job.
- After 5 attempts a job is left in place, no longer claimed and no longer counted as pending.
- Completing or releasing a job checks that this worker still holds the lock, so a worker that lost its lock cannot finish a job someone else reclaimed.

`recompute_decision`:

1. Locks the submission row.
2. Loads all of its observations.
3. Computes the input hash.
4. Stores a new decision run only if the hash differs from the latest run.

Duplicate or out-of-order jobs end up at the same result.

## Carrier hand-off

`sendToCarrier`:

- Refuses anything but a QUOTE.
- Creates the transmission and its `send_to_carrier` job in one transaction, which is the outbox. A test proves that a failing enqueue leaves no transmission behind.
- Uses an idempotency key of `quote-{submission}-run-{decision run}`, so a new decision needs a new send.

The worker posts to `/carrier/quotes` with an `Idempotency-Key` header, using a 2 second timeout.

- On a timeout, a connection error or a 5xx it retries once.
- After two failures the transmission is `failed`, and "Send again" re-queues it with the same key.
- When the transmission is already delivered, "Send again" replays the request. The carrier answers with its stored acknowledgement and marks it `Idempotent-Replay: true`. A replay only writes audit events: if it fails, the delivered transmission stays delivered.

The simulator has two modes: `ok` and `timeout_once`.

- In `timeout_once`, the first new quote is recorded and then the response stalls past the client timeout. This models a lost response.
- The retry therefore finds the stored receipt and gets the original acknowledgement. There is only ever one receipt per key.
- The mode lives in the API process. `CARRIER_MODE` sets the default, and the demo reset re-arms it.

## API

GraphQL at `/graphql`:

- Queries: `submission(id)`, `decisionTrace(submissionId, asOf)`, `timeline(submissionId)`.
- Mutations: `deliverFixture(submissionId, fixture)`, `sendToCarrier(submissionId)`, `resetDemo`.

`decisionTrace` without `asOf` returns the latest stored run. With `asOf`, it runs the engine live and stores nothing. Both the worker and `decisionTrace` hash only the observations known at `as_of`, which is exactly the list the engine decides on.

`submission` also returns the observations with fresh or stale flags and superseded markers, the latest decision, which rows changed since the previous run, the latest transmission and the number of pending jobs. The page uses the pending jobs count to decide when to poll.

Resolvers are async and run database work in a thread pool. `resetDemo` is refused unless `DEMO_MODE=1`.

## UI

One route, three columns and an action bar.

- **Evidence column:** a card per observation with its source, claim, value, age on the scenario clock, a fresh or stale tag and any superseded marker.
- **Decision column:** the outcome badge, the total with a sentence relating it to the 15 point threshold, the contribution rows and the rows that no longer apply.
- **Clicking a row:** it highlights its evidence card and shows the rule text. Rows that changed since the previous run are highlighted.
- **Timeline column:** polls every 1.5 seconds while a job is pending.
- **Guided demo:** adds a step bar whose "Next step" runs that step's real mutation.
- **Developer details:** a collapsed disclosure that shows the last GraphQL operation and response.

## Tests

| Spec test | Where |
|---|---|
| 1. Same inputs give the same decision and hash | `packages/decision/tests/test_decision_properties.py` |
| 2. Points sum to the total | same file, property test |
| 3. Stale evidence never lowers risk | same file: adding a stale observation and advancing time never lower points or outcome |
| 4. Arrival order never changes the decision | same file, Hypothesis shuffles generated observation lists |
| 5. Ingesting twice creates nothing new | `services/api/tests/test_ingestion.py` |
| Carrier retry and idempotency | `services/api/tests/test_carrier.py`, against a real HTTP server in a thread |
| GraphQL | `services/api/tests/test_graphql.py` |
| Architecture | `packages/decision/tests/test_architecture.py` |

The service tests run against a real Postgres. They create and reset a separate `rte_test` database.
