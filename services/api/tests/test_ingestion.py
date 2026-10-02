from __future__ import annotations

from app.ingest import deliver_fixture
from app.seed import seed
from app.worker import run_until_idle
from sqlalchemy import Engine, text


def counts(engine: Engine) -> dict[str, int]:
    with engine.connect() as conn:
        return {
            table: int(conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one())
            for table in ("observations", "jobs", "audit_events", "decision_runs")
        }


def new_submission(engine: Engine, name: str, domain: str) -> int:
    with engine.begin() as conn:
        row = conn.execute(
            text(
                "INSERT INTO submissions (company_name, primary_domain)"
                " VALUES (:n, :d) RETURNING id"
            ),
            {"n": name, "d": domain},
        ).one()
    return int(row.id)


def test_ingesting_the_same_observation_twice_creates_nothing_new(engine: Engine) -> None:
    submission_id = new_submission(engine, "Acme Manufacturing", "acme.test")
    first = deliver_fixture(engine, submission_id, "acme_submission")
    assert len(first.new_observation_ids) == 3
    run_until_idle(engine)
    before = counts(engine)

    second = deliver_fixture(engine, submission_id, "acme_submission")

    assert second.new_observation_ids == []
    assert not second.changed
    assert counts(engine) == before
    assert run_until_idle(engine) == 0
    assert counts(engine) == before


def test_each_new_observation_batch_enqueues_one_recompute(engine: Engine) -> None:
    submission_id = new_submission(engine, "Acme Manufacturing", "acme.test")
    deliver_fixture(engine, submission_id, "acme_submission")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM jobs")).scalar_one() == 1
        assert conn.execute(text("SELECT kind FROM jobs")).scalar_one() == "recompute_decision"


def test_fixture_for_another_company_is_rejected(engine: Engine) -> None:
    import pytest
    from app.ingest import FixtureMismatchError

    harbor = new_submission(engine, "Harbor Dental Group", "harbor.test")
    with pytest.raises(FixtureMismatchError):
        deliver_fixture(engine, harbor, "acme_submission")
    assert counts(engine)["observations"] == 0


def test_unknown_or_path_like_fixture_names_are_rejected(engine: Engine) -> None:
    import pytest
    from app.fixtures import UnknownFixtureError

    submission_id = new_submission(engine, "Acme Manufacturing", "acme.test")
    for bad in ("../acme_submission", "nope", "acme_submission.json", ""):
        with pytest.raises(UnknownFixtureError):
            deliver_fixture(engine, submission_id, bad)


def test_seed_creates_both_submissions_with_a_decision_each(engine: Engine) -> None:
    ids = seed(engine)
    assert set(ids) == {"acme.test", "harbor.test"}
    assert counts(engine)["decision_runs"] == 2
