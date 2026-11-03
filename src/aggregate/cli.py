"""The `aggregate` command: admin and cron tasks."""

from typing import Annotated

import typer
from alembic import command

from aggregate.db import alembic_config

app = typer.Typer(no_args_is_help=True, help="aggregate: personal finance ledger admin")
db_app = typer.Typer(no_args_is_help=True, help="Database commands")
app.add_typer(db_app, name="db")


@db_app.command("upgrade")
def db_upgrade(
    revision: Annotated[str, typer.Argument(help="Target revision")] = "head",
) -> None:
    """Run Alembic migrations against AGGREGATE_DATABASE_URL."""
    command.upgrade(alembic_config(), revision)
    typer.echo(f"Database upgraded to {revision}.")
