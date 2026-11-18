"""Test dell'endpoint di salute (RNF09).

Il TestClient di FastAPI invia richieste HTTP all'applicazione in memoria,
senza avviare un server: è come chiamare le rotte con curl, ma dentro pytest.
"""

from collections.abc import Iterator
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.core.db import get_db
from app.main import app


def test_health_ok_quando_il_database_risponde() -> None:
    """Con il database raggiungibile l'endpoint risponde 200."""
    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_503_quando_il_database_non_risponde() -> None:
    """Se la query fallisce l'endpoint risponde 503, senza far cadere l'API.

    La dipendenza get_db viene sostituita con una sessione finta che solleva
    l'errore di connessione: è il vantaggio della dependency injection.
    """
    broken_session = MagicMock()
    broken_session.execute.side_effect = OperationalError("SELECT 1", {}, Exception("down"))

    def override_get_db() -> Iterator[MagicMock]:
        yield broken_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            response = client.get("/api/health")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": "unreachable"}


def test_documentazione_sotto_api() -> None:
    """Swagger e lo schema OpenAPI sono serviti sotto /api, come prevede nginx."""
    with TestClient(app) as client:
        assert client.get("/api/openapi.json").status_code == 200
        assert client.get("/api/docs").status_code == 200
        assert client.get("/docs").status_code == 404
