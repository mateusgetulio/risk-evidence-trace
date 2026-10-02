from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from app.db import init_schema, make_engine, truncate_everything
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url

DEFAULT_TEST_URL = "postgresql+psycopg://rte:rte@localhost:5433/rte_test"


def _ensure_database(url: str) -> None:
    parsed = make_url(url)
    admin = create_engine(parsed.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": parsed.database}
        ).first()
        if exists is None:
            conn.execute(text(f'CREATE DATABASE "{parsed.database}"'))
    admin.dispose()


@pytest.fixture(scope="session")
def database_url() -> str:
    return os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_URL)


@pytest.fixture(scope="session")
def _schema_ready(database_url: str) -> None:
    try:
        _ensure_database(database_url)
    except Exception as exc:
        pytest.exit(
            f"Postgres is not reachable at {database_url}. Run `docker compose up -d --wait db` "
            f"or set TEST_DATABASE_URL. ({exc})",
            returncode=2,
        )
    init_schema(make_engine(database_url))


@pytest.fixture
def engine(database_url: str, _schema_ready: None) -> Iterator[Engine]:
    eng = make_engine(database_url)
    truncate_everything(eng)
    yield eng
    eng.dispose()
