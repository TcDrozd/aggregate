"""The `aggregate` command: admin and cron tasks."""

from pathlib import Path
from typing import Annotated

import typer
from alembic import command
from alembic.config import Config

app = typer.Typer(no_args_is_help=True, help="aggregate: personal finance ledger admin")
db_app = typer.Typer(no_args_is_help=True, help="Database commands")
app.add_typer(db_app, name="db")

# src/aggregate/cli.py -> repository root, where alembic.ini lives. The project is
# installed editable in development and in the Docker image, so this holds in both.
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def alembic_config() -> Config:
    return Config(str(PROJECT_ROOT / "alembic.ini"))


@db_app.command("upgrade")
def db_upgrade(
    revision: Annotated[str, typer.Argument(help="Target revision")] = "head",
) -> None:
    """Run Alembic migrations against AGGREGATE_DATABASE_URL."""
    command.upgrade(alembic_config(), revision)
    typer.echo(f"Database upgraded to {revision}.")
