"""App factory and routes. Run with: uvicorn aggregate.main:create_app --factory"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from aggregate import __version__
from aggregate.config import Settings
from aggregate.db import make_engine
from aggregate.schemas import ErrorBody, ErrorDetail, Health


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    engine = make_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        engine.dispose()

    app = FastAPI(title="aggregate", version=__version__, lifespan=lifespan)
    app.state.engine = engine

    @app.get(
        "/healthz",
        response_model=Health,
        responses={503: {"model": ErrorBody}},
        summary="Liveness and database check; no auth, no data",
    )
    def healthz() -> Health | JSONResponse:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except SQLAlchemyError:
            body = ErrorBody(
                error=ErrorDetail(code="database_unavailable", message="Database check failed")
            )
            return JSONResponse(status_code=503, content=body.model_dump())
        return Health(status="ok", database="ok")

    return app
