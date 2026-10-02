from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text

from app.db import dumps


def record(conn: Connection, submission_id: int, kind: str, detail: dict[str, Any]) -> None:
    conn.execute(
        text(
            "INSERT INTO audit_events (submission_id, kind, detail) "
            "VALUES (:submission_id, :kind, CAST(:detail AS jsonb))"
        ),
        {"submission_id": submission_id, "kind": kind, "detail": dumps(detail)},
    )
