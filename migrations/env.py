"""Alembic environment: URL from settings, batch mode for SQLite."""

from logging.config import fileConfig
from typing import Any

from alembic import context
from alembic.autogenerate.api import AutogenContext

from aggregate.config import Settings
from aggregate.db import make_engine
from aggregate.models import Base, UTCDateTime

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def database_url() -> str:
    # Tests may set sqlalchemy.url on the Config; otherwise use AGGREGATE_DATABASE_URL.
    return config.get_main_option("sqlalchemy.url") or Settings().database_url


def render_item(type_: str, obj: Any, autogen_context: AutogenContext) -> str | bool:
    # Migrations must not import app code: UTCDateTime is a plain DateTime in the database.
    if type_ == "type" and isinstance(obj, UTCDateTime):
        return "sa.DateTime()"
    return False


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
        render_item=render_item,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = make_engine(database_url())
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            render_item=render_item,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
