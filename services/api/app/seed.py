from __future__ import annotations

from sqlalchemy import Engine, text

from app.db import init_schema, truncate_everything
from app.ingest import deliver_fixture
from app.worker import run_until_idle

SEED_SUBMISSIONS = (
    ("Acme Manufacturing", "acme.test", "acme_submission"),
    ("Harbor Dental Group", "harbor.test", "harbor_submission"),
)


def seed(engine: Engine) -> dict[str, int]:
    init_schema(engine)
    truncate_everything(engine)
    ids: dict[str, int] = {}
    for company, domain, fixture in SEED_SUBMISSIONS:
        with engine.begin() as conn:
            row = conn.execute(
                text(
                    "INSERT INTO submissions (company_name, primary_domain) "
                    "VALUES (:name, :domain) RETURNING id"
                ),
                {"name": company, "domain": domain},
            ).one()
        ids[domain] = int(row.id)
        deliver_fixture(engine, int(row.id), fixture)
    run_until_idle(engine)
    return ids


def main() -> None:
    from app.config import database_url
    from app.db import make_engine

    ids = seed(make_engine(database_url()))
    for domain, submission_id in ids.items():
        print(f"{domain}: /submissions/{submission_id}")


if __name__ == "__main__":
    main()
