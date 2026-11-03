"""Engine setup, including the SQLite pragmas every connection needs."""

from pathlib import Path
from typing import Any

from alembic.config import Config
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url

# src/aggregate/db.py -> repository root, where alembic.ini lives. The project is
# installed editable in development and in the Docker image, so this holds in both.
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def make_engine(url: str) -> Engine:
    """Create an engine; for SQLite, create the file's directory and set pragmas."""
    parsed = make_url(url)
    if parsed.get_backend_name() == "sqlite" and parsed.database not in (None, "", ":memory:"):
        Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url)
    if engine.dialect.name == "sqlite":
        event.listen(engine, "connect", _sqlite_pragmas)
    return engine


def _sqlite_pragmas(dbapi_connection: Any, _connection_record: Any) -> None:
    # SQLite leaves foreign keys off by default; WAL lets readers run during a write.
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


def alembic_config(database_url: str | None = None) -> Config:
    """Alembic config for this project; database_url overrides AGGREGATE_DATABASE_URL."""
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    if database_url is not None:
        config.set_main_option("sqlalchemy.url", database_url)
    return config
