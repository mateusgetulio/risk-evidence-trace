from __future__ import annotations

from datetime import datetime

import strawberry
from sqlalchemy import Engine
from starlette.concurrency import run_in_threadpool
from strawberry.types import Info

from app import api_types as t
from app import queries
from app.carrier import state as carrier_state
from app.config import demo_mode
from app.fixtures import UnknownFixtureError
from app.ingest import FixtureMismatchError, deliver_fixture
from app.seed import seed
from app.transmit import SendRefusedError, request_send


def _engine(info: Info) -> Engine:
    engine: Engine = info.context["engine"]
    return engine


@strawberry.type
class Query:
    @strawberry.field
    async def submission(self, info: Info, id: int) -> t.Submission | None:
        return await run_in_threadpool(queries.get_submission, _engine(info), id)

    @strawberry.field
    async def decision_trace(
        self, info: Info, submission_id: int, as_of: datetime | None = None
    ) -> t.Decision | None:
        return await run_in_threadpool(queries.decision_trace, _engine(info), submission_id, as_of)

    @strawberry.field
    async def timeline(self, info: Info, submission_id: int) -> list[t.TimelineEvent]:
        return await run_in_threadpool(queries.timeline, _engine(info), submission_id)


@strawberry.type
class Mutation:
    @strawberry.mutation
    async def deliver_fixture(
        self, info: Info, submission_id: int, fixture: str
    ) -> t.DeliveryResult:
        try:
            result = await run_in_threadpool(deliver_fixture, _engine(info), submission_id, fixture)
        except (UnknownFixtureError, FixtureMismatchError) as exc:
            raise ValueError(str(exc)) from exc
        return t.DeliveryResult(
            new_observations=len(result.new_observation_ids),
            clock_advanced=result.clock_advanced,
        )

    @strawberry.mutation
    async def send_to_carrier(self, info: Info, submission_id: int) -> t.SendResult:
        try:
            result = await run_in_threadpool(request_send, _engine(info), submission_id)
        except SendRefusedError as exc:
            raise ValueError(str(exc)) from exc
        return t.SendResult(
            transmission_id=result.transmission_id,
            state=result.state,
            queued=result.queued,
            replay=result.replay,
        )

    @strawberry.mutation
    async def reset_demo(self, info: Info) -> t.ResetResult:
        if not demo_mode():
            raise ValueError("resetDemo is only available when DEMO_MODE=1")
        ids = await run_in_threadpool(seed, _engine(info))
        carrier_state.reset()
        return t.ResetResult(submission_ids=sorted(ids.values()))


schema = strawberry.Schema(query=Query, mutation=Mutation)
