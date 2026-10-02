from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine

SCHEMA_PATH = Path(__file__).with_name("schema.sql")

RESET_TABLES = (
    "audit_events, jobs, carrier_receipts, transmissions, decision_runs, observations, submissions"
)


def make_engine(url: str) -> Engine:
    return create_engine(url, pool_pre_ping=True, future=True)


def init_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        cursor = conn.connection.cursor()
        cursor.execute(SCHEMA_PATH.read_text())
        cursor.close()


def truncate_everything(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.exec_driver_sql(f"TRUNCATE {RESET_TABLES} RESTART IDENTITY")


def dumps(value: Mapping[str, Any] | list[Any]) -> str:
    return json.dumps(value, sort_keys=True, default=str)
