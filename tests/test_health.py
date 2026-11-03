from pathlib import Path

from fastapi.testclient import TestClient

from aggregate.config import Settings
from aggregate.main import create_app


def test_healthz_reports_ok_without_auth(client: TestClient) -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_healthz_returns_error_envelope_when_database_is_unreachable(tmp_path: Path) -> None:
    # A directory can't be opened as a SQLite database file.
    app = create_app(Settings(database_url=f"sqlite:///{tmp_path}"))

    with TestClient(app) as client:
        response = client.get("/healthz")

    assert response.status_code == 503
    assert response.json() == {
        "error": {"code": "database_unavailable", "message": "Database check failed"}
    }
