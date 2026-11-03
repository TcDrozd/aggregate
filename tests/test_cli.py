import pytest
from typer.testing import CliRunner

from aggregate.cli import app


def test_db_upgrade_runs_migrations(monkeypatch: pytest.MonkeyPatch, database_url: str) -> None:
    monkeypatch.setenv("AGGREGATE_DATABASE_URL", database_url)

    result = CliRunner().invoke(app, ["db", "upgrade"])

    assert result.exit_code == 0, result.output
    assert "Database upgraded to head." in result.output
