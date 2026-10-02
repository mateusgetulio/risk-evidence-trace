from __future__ import annotations

import threading
from typing import Any

import pytest
from app import jobs
from app.db import truncate_everything
from app.ingest import deliver_fixture
from app.recompute import recompute_decision
from app.seed import seed
from app.worker import run_once, run_until_idle
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError


def latest_run(engine: Engine, submission_id: int) -> Any:
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT * FROM decision_runs WHERE submission_id = :id ORDER BY id DESC LIMIT 1"),
            {"id": submission_id},
        ).one()


def run_count(engine: Engine, submission_id: int) -> int:
    with engine.connect() as conn:
        return int(
            conn.execute(
                text("SELECT count(*) FROM decision_runs WHERE submission_id = :id"),
                {"id": submission_id},
            ).scalar_one()
        )


def audit_kinds(engine: Engine, submission_id: int) -> list[str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT kind FROM audit_events WHERE submission_id = :id ORDER BY id"),
            {"id": submission_id},
        ).all()
    return [row.kind for row in rows]


def test_seeded_acme_is_a_quote_with_low_points(engine: Engine) -> None:
    acme = seed(engine)["acme.test"]
    run = latest_run(engine, acme)
    assert run.outcome == "QUOTE"
    assert run.total_points == -5
    assert [c["rule_id"] for c in run.contributions] == ["BK-02"]
    assert run.blockers == []


def test_late_scan_flips_quote_to_refer_with_provenance(engine: Engine) -> None:
    acme = seed(engine)["acme.test"]
    deliver_fixture(engine, acme, "acme_late_scan")
    run_until_idle(engine)

    run = latest_run(engine, acme)
    assert run_count(engine, acme) == 2
    assert run.outcome == "REFER"
    assert run.total_points == 15
    ex = next(c for c in run.contributions if c["rule_id"] == "EX-01")
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT source, subject, claim FROM observations WHERE id = :id"),
            {"id": ex["observation_id"]},
        ).one()
    assert (row.source, row.subject, row.claim) == (
        "external_scan",
        "vpn.acme.test",
        "critical_exposed_vuln",
    )
    superseded = {s["observation_id"] for s in run.superseded}
    assert len(superseded) == 2
    kinds = audit_kinds(engine, acme)
    assert kinds[-3:] == ["observation_received", "observation_received", "decision_computed"]
    assert kinds.count("decision_computed") == 2


def test_time_passing_makes_the_backup_attestation_stale(engine: Engine) -> None:
    acme = seed(engine)["acme.test"]
    deliver_fixture(engine, acme, "acme_late_scan")
    run_until_idle(engine)
    deliver_fixture(engine, acme, "acme_time_passes")
    run_until_idle(engine)

    run = latest_run(engine, acme)
    assert run.outcome == "REFER"
    assert run.total_points == 30
    assert sorted(c["rule_id"] for c in run.contributions) == ["BK-01", "EX-01"]
    assert len(run.blockers) == 1
    assert "stale_evidence" in {b["kind"] for b in run.blockers}
    assert "clock_advanced" in audit_kinds(engine, acme)

    again = deliver_fixture(engine, acme, "acme_time_passes")
    assert not again.changed
    assert run_until_idle(engine) == 0


def test_harbor_is_a_clean_quote(engine: Engine) -> None:
    harbor = seed(engine)["harbor.test"]
    run = latest_run(engine, harbor)
    assert (run.outcome, run.total_points, run.blockers) == ("QUOTE", -5, [])


def test_recompute_stores_a_run_only_when_the_input_hash_changes(engine: Engine) -> None:
    acme = seed(engine)["acme.test"]
    assert run_count(engine, acme) == 1
    assert recompute_decision(engine, acme) is None
    assert recompute_decision(engine, acme) is None
    assert run_count(engine, acme) == 1
    assert audit_kinds(engine, acme).count("decision_unchanged") == 2


def test_delivery_order_does_not_change_the_decision(engine: Engine) -> None:
    first = seed(engine)["acme.test"]
    deliver_fixture(engine, first, "acme_late_scan")
    deliver_fixture(engine, first, "acme_time_passes")
    run_until_idle(engine)
    in_order = latest_run(engine, first)

    truncate_everything(engine)
    with engine.begin() as conn:
        row = conn.execute(
            text(
                "INSERT INTO submissions (company_name, primary_domain) "
                "VALUES ('Acme Manufacturing', 'acme.test') RETURNING id"
            )
        ).one()
    other = int(row.id)
    deliver_fixture(engine, other, "acme_time_passes")
    deliver_fixture(engine, other, "acme_late_scan")
    deliver_fixture(engine, other, "acme_submission")
    run_until_idle(engine)
    reordered = latest_run(engine, other)

    assert (reordered.outcome, reordered.total_points) == (in_order.outcome, in_order.total_points)
    assert sorted(c["rule_id"] for c in reordered.contributions) == sorted(
        c["rule_id"] for c in in_order.contributions
    )


@pytest.mark.parametrize("table", ["observations", "decision_runs", "audit_events"])
def test_append_only_tables_reject_update_and_delete(engine: Engine, table: str) -> None:
    seed(engine)
    for statement in (f"UPDATE {table} SET id = id", f"DELETE FROM {table}"):
        with pytest.raises(DBAPIError, match="append-only"), engine.begin() as conn:
            conn.execute(text(statement))


def test_failed_job_is_released_and_retried(engine: Engine) -> None:
    with engine.begin() as conn:
        jobs.enqueue(conn, "boom", {})
    calls: list[int] = []

    def explode(_engine: Engine, _payload: dict[str, Any]) -> None:
        calls.append(1)
        raise RuntimeError("nope")

    assert run_once(engine, {"boom": explode}) is True
    assert run_once(engine, {"boom": explode}) is False
    assert calls == [1]
    with engine.connect() as conn:
        row = conn.execute(text("SELECT attempts, locked_at FROM jobs")).one()
    assert row.attempts == 1 and row.locked_at is None


def test_concurrent_claims_never_hand_out_the_same_job(engine: Engine) -> None:
    total = 40
    with engine.begin() as conn:
        for index in range(total):
            jobs.enqueue(conn, "noop", {"n": index})
    claimed: list[int] = []
    lock = threading.Lock()

    def drain() -> None:
        while (job := jobs.claim(engine)) is not None:
            with lock:
                claimed.append(job.id)

    threads = [threading.Thread(target=drain) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(claimed) == total
    assert len(set(claimed)) == total


def test_claim_skips_a_row_another_transaction_holds(engine: Engine) -> None:
    with engine.begin() as conn:
        first = jobs.enqueue(conn, "noop", {"n": 1})
        second = jobs.enqueue(conn, "noop", {"n": 2})
    claimed: list[int] = []
    with engine.connect() as holder:
        holder.execute(text("BEGIN"))
        holder.execute(text("SELECT id FROM jobs WHERE id = :id FOR UPDATE"), {"id": first})

        def claim_one() -> None:
            job = jobs.claim(engine)
            if job is not None:
                claimed.append(job.id)

        thread = threading.Thread(target=claim_one)
        thread.start()
        thread.join(timeout=3)
        still_waiting = thread.is_alive()
        holder.execute(text("ROLLBACK"))
        thread.join(timeout=3)
    assert not still_waiting
    assert claimed == [second]


def test_a_stale_worker_cannot_complete_or_release_a_reclaimed_job(engine: Engine) -> None:
    with engine.begin() as conn:
        jobs.enqueue(conn, "noop", {})
    stale = jobs.claim(engine)
    assert stale is not None
    with engine.begin() as conn:
        conn.execute(text("UPDATE jobs SET locked_at = now() + interval '1 second'"))
    assert jobs.complete(engine, stale) is False
    assert jobs.release_for_retry(engine, stale) is False
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM jobs")).scalar_one() == 1


def test_a_job_past_its_attempt_limit_no_longer_counts_as_pending(engine: Engine) -> None:
    acme = seed(engine)["acme.test"]
    with engine.begin() as conn:
        jobs.enqueue(conn, "noop", {"submission_id": acme})
        assert jobs.pending_count(conn, acme) == 1
        conn.execute(text("UPDATE jobs SET attempts = :n"), {"n": jobs.MAX_ATTEMPTS})
        assert jobs.pending_count(conn, acme) == 0


def test_seed_command_refuses_outside_demo_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.seed import main

    monkeypatch.delenv("DEMO_MODE", raising=False)
    with pytest.raises(SystemExit, match="DEMO_MODE=1"):
        main()
