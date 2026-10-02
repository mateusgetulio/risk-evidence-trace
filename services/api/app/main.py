from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import Engine
from strawberry.fastapi import GraphQLRouter

from app.carrier import router as carrier_router
from app.config import database_url
from app.db import init_schema, make_engine
from app.schema_graphql import schema


def create_app(engine: Engine | None = None) -> FastAPI:
    shared = engine or make_engine(database_url())

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        init_schema(shared)
        yield

    app = FastAPI(title="Risk Evidence Trace", lifespan=lifespan)
    app.state.engine = shared
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_methods=["POST", "GET", "OPTIONS"],
        allow_headers=["*"],
    )

    async def context() -> dict[str, Any]:
        return {"engine": shared}

    app.include_router(carrier_router)
    app.include_router(GraphQLRouter(schema, context_getter=context), prefix="/graphql")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
