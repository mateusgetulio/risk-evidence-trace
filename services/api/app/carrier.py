from __future__ import annotations

import asyncio
import threading
import uuid
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import Engine, text
from starlette.concurrency import run_in_threadpool

from app.config import carrier_default_mode, carrier_stall_seconds, demo_mode
from app.db import dumps

MODES = ("ok", "timeout_once")


class CarrierState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.mode = carrier_default_mode()
        self._stall_armed = self.mode == "timeout_once"

    def set_mode(self, mode: str) -> None:
        if mode not in MODES:
            raise ValueError(f"unknown carrier mode: {mode}")
        with self._lock:
            self.mode = mode
            self._stall_armed = mode == "timeout_once"

    def reset(self) -> None:
        self.set_mode(carrier_default_mode())

    def consume_stall(self) -> bool:
        with self._lock:
            if self.mode == "timeout_once" and self._stall_armed:
                self._stall_armed = False
                return True
            return False


state = CarrierState()

router = APIRouter(prefix="/carrier")


class QuoteRequest(BaseModel):
    submission_id: int
    decision_run_id: int
    outcome: str
    total_points: int


class ModeRequest(BaseModel):
    mode: str


def _store_receipt(engine: Engine, key: str, body: QuoteRequest) -> tuple[dict[str, Any], bool]:
    acknowledgement = {
        "acknowledgement_id": f"ack-{uuid.uuid4().hex[:12]}",
        "status": "accepted",
        "idempotency_key": key,
        "submission_id": body.submission_id,
        "total_points": body.total_points,
    }
    with engine.begin() as conn:
        inserted = conn.execute(
            text(
                "INSERT INTO carrier_receipts (idempotency_key, acknowledgement) "
                "VALUES (:key, CAST(:ack AS jsonb)) "
                "ON CONFLICT (idempotency_key) DO NOTHING RETURNING idempotency_key"
            ),
            {"key": key, "ack": dumps(acknowledgement)},
        ).first()
        if inserted is not None:
            return acknowledgement, False
        stored = conn.execute(
            text("SELECT acknowledgement FROM carrier_receipts WHERE idempotency_key = :key"),
            {"key": key},
        ).one()
    return dict(stored.acknowledgement), True


@router.post("/quotes")
async def receive_quote(
    body: QuoteRequest,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None),
) -> dict[str, Any]:
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required")
    if body.outcome != "QUOTE":
        raise HTTPException(status_code=422, detail="The carrier only accepts QUOTE decisions")
    engine: Engine = request.app.state.engine
    acknowledgement, replay = await run_in_threadpool(_store_receipt, engine, idempotency_key, body)
    if replay:
        response.headers["Idempotent-Replay"] = "true"
    elif state.consume_stall():
        await asyncio.sleep(carrier_stall_seconds())
    return acknowledgement


@router.get("/receipts")
async def list_receipts(request: Request) -> list[dict[str, Any]]:
    engine: Engine = request.app.state.engine

    def read() -> list[dict[str, Any]]:
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT idempotency_key, acknowledgement FROM carrier_receipts ORDER BY 1")
            ).all()
        return [{"idempotency_key": r.idempotency_key, **r.acknowledgement} for r in rows]

    return await run_in_threadpool(read)


@router.post("/mode")
async def set_mode(body: ModeRequest) -> dict[str, str]:
    if not demo_mode():
        raise HTTPException(status_code=403, detail="The carrier mode can only change in demo mode")
    try:
        state.set_mode(body.mode)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"mode": state.mode}
