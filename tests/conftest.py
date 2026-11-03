import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from aggregate.config import Settings
from aggregate.db import alembic_config, make_engine
from aggregate.main import create_app


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Real captures never leave the developer's machine, so CI skips them."""
    if not os.environ.get("CI"):
        return
    skip = pytest.mark.skip(reason="private captures run locally only")
    for item in items:
        if "private" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def database_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'test.db'}"


@pytest.fixture
def settings(database_url: str) -> Settings:
    return Settings(database_url=database_url)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def engine(database_url: str) -> Iterator[Engine]:
    """An engine on a database built by the migrations, not by create_all."""
    command.upgrade(alembic_config(database_url), "head")
    engine = make_engine(database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with Session(engine) as session:
        yield session
