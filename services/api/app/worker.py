from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from sqlalchemy import Engine

from app import jobs
from app.recompute import recompute_decision
from app.transmit import SEND_JOB, send_to_carrier

log = logging.getLogger("worker")

Handler = Callable[[Engine, dict[str, Any]], None]


def _recompute(engine: Engine, payload: dict[str, Any]) -> None:
    recompute_decision(engine, int(payload["submission_id"]))


HANDLERS: dict[str, Handler] = {"recompute_decision": _recompute, SEND_JOB: send_to_carrier}


def run_once(engine: Engine, handlers: dict[str, Handler] | None = None) -> bool:
    table = HANDLERS if handlers is None else handlers
    job = jobs.claim(engine)
    if job is None:
        return False
    try:
        table[job.kind](engine, job.payload)
    except Exception:
        log.exception("job %s (%s) failed on attempt %s", job.id, job.kind, job.attempts)
        jobs.release_for_retry(engine, job.id)
        return True
    jobs.complete(engine, job.id)
    return True


def run_until_idle(
    engine: Engine, handlers: dict[str, Handler] | None = None, limit: int = 1000
) -> int:
    processed = 0
    while processed < limit and run_once(engine, handlers):
        processed += 1
    return processed


def main() -> None:
    from app.config import database_url
    from app.db import init_schema, make_engine

    logging.basicConfig(level=logging.INFO)
    engine = make_engine(database_url())
    init_schema(engine)
    while True:
        if not run_once(engine):
            time.sleep(0.5)


if __name__ == "__main__":
    main()
