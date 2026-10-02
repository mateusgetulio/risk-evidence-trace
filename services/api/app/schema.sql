SELECT pg_advisory_xact_lock(727001);

CREATE TABLE IF NOT EXISTS submissions (
    id serial PRIMARY KEY,
    company_name text NOT NULL,
    primary_domain text NOT NULL UNIQUE,
    status text NOT NULL DEFAULT 'open',
    clock_origin timestamptz NOT NULL DEFAULT now(),
    clock_offset_days integer NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS observations (
    id bigserial PRIMARY KEY,
    submission_id integer NOT NULL REFERENCES submissions (id),
    source text NOT NULL CHECK (source IN ('applicant', 'external_scan', 'posture')),
    source_observation_id text NOT NULL,
    subject text NOT NULL,
    claim text NOT NULL CHECK (
        claim IN ('mfa', 'critical_exposed_vuln', 'backups_tested', 'ransomware_indicator')
    ),
    value boolean NOT NULL,
    observed_at timestamptz NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    raw jsonb NOT NULL,
    UNIQUE (source, source_observation_id)
);
CREATE INDEX IF NOT EXISTS observations_submission_idx ON observations (submission_id, id);

CREATE TABLE IF NOT EXISTS decision_runs (
    id bigserial PRIMARY KEY,
    submission_id integer NOT NULL REFERENCES submissions (id),
    as_of timestamptz NOT NULL,
    rule_set_version text NOT NULL,
    input_observation_ids bigint[] NOT NULL,
    input_hash text NOT NULL,
    outcome text NOT NULL CHECK (outcome IN ('QUOTE', 'REFER', 'DECLINE')),
    total_points integer NOT NULL,
    contributions jsonb NOT NULL,
    blockers jsonb NOT NULL,
    superseded jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS decision_runs_submission_idx ON decision_runs (submission_id, id DESC);

CREATE TABLE IF NOT EXISTS transmissions (
    id bigserial PRIMARY KEY,
    decision_run_id bigint NOT NULL REFERENCES decision_runs (id),
    idempotency_key text NOT NULL UNIQUE,
    state text NOT NULL DEFAULT 'pending' CHECK (state IN ('pending', 'delivered', 'failed')),
    attempts integer NOT NULL DEFAULT 0,
    last_error text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS carrier_receipts (
    idempotency_key text PRIMARY KEY,
    acknowledgement jsonb NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS jobs (
    id bigserial PRIMARY KEY,
    kind text NOT NULL,
    payload jsonb NOT NULL,
    run_at timestamptz NOT NULL DEFAULT now(),
    locked_at timestamptz,
    attempts integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS jobs_claim_idx ON jobs (run_at, id);

CREATE TABLE IF NOT EXISTS audit_events (
    id bigserial PRIMARY KEY,
    submission_id integer NOT NULL REFERENCES submissions (id),
    at timestamptz NOT NULL DEFAULT now(),
    kind text NOT NULL,
    detail jsonb NOT NULL
);
CREATE INDEX IF NOT EXISTS audit_events_submission_idx ON audit_events (submission_id, id DESC);

CREATE OR REPLACE FUNCTION forbid_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'append-only table: %', TG_TABLE_NAME;
END;
$$;

DROP TRIGGER IF EXISTS observations_append_only ON observations;
CREATE TRIGGER observations_append_only BEFORE UPDATE OR DELETE ON observations
    FOR EACH ROW EXECUTE FUNCTION forbid_mutation();

DROP TRIGGER IF EXISTS decision_runs_append_only ON decision_runs;
CREATE TRIGGER decision_runs_append_only BEFORE UPDATE OR DELETE ON decision_runs
    FOR EACH ROW EXECUTE FUNCTION forbid_mutation();

DROP TRIGGER IF EXISTS audit_events_append_only ON audit_events;
CREATE TRIGGER audit_events_append_only BEFORE UPDATE OR DELETE ON audit_events
    FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
