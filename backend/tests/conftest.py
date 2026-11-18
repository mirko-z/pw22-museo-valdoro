"""Configurazione comune dei test (pytest la carica prima di ogni file di test).

I test girano su un database PostgreSQL **separato** (RNF11): di default il
nome del database principale con suffisso ``_test`` (es. ``museo_test``),
oppure quello indicato in ``TEST_POSTGRES_DB``. Non si usa SQLite: i vincoli,
gli indici parziali e i lock di riga da verificare sono quelli di PostgreSQL.

Le *fixture* di pytest sono funzioni che preparano (e poi smontano) le
risorse di cui un test ha bisogno; il test le riceve dichiarandole come
parametri, con lo stesso principio della dependency injection di FastAPI.
"""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from app.core.config import Settings

# --- 1. Scelta del database di test, PRIMA di importare app.core.db ---------
# app.core.db crea l'engine al momento dell'import leggendo Settings:
# le variabili d'ambiente vanno quindi modificate prima di quell'import.
_main = Settings()  # type: ignore[call-arg]
TEST_DB = os.environ.get("TEST_POSTGRES_DB", f"{_main.postgres_db}_test")
if TEST_DB == _main.postgres_db:
    raise RuntimeError("Il database di test deve essere diverso da quello dell'applicazione.")
os.environ["POSTGRES_DB"] = TEST_DB
os.environ["APP_ENV"] = "test"


def _create_test_database_if_missing() -> None:
    """Crea il database di test collegandosi a quello principale.

    CREATE DATABASE non può stare dentro una transazione: si usa AUTOCOMMIT.
    Nel container l'utente POSTGRES_USER è il proprietario del cluster e ha
    il permesso di creare database.
    """
    admin_engine = create_engine(_main.database_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        exists = conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": TEST_DB})
        if not exists:
            # Il nome non può essere un parametro: si quota come identificatore
            conn.execute(text(f'CREATE DATABASE "{TEST_DB}"'))
    admin_engine.dispose()


_create_test_database_if_missing()

# Solo ora si importa ciò che dipende dalla configurazione del database
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app.core.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402

ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"
TABLES = "feedback, bookings, events, users"


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> None:
    """Una volta per sessione di test: schema ricreato con le migrazioni Alembic.

    ``downgrade base`` e poi ``upgrade head``: si parte sempre da zero e si
    verifica a ogni esecuzione che anche il downgrade funzioni. Lo schema dei
    test è quindi esattamente quello di produzione, non un create_all().
    """
    config = Config(str(ALEMBIC_INI))
    command.downgrade(config, "base")
    command.upgrade(config, "head")


@pytest.fixture(autouse=True)
def clean_tables() -> Iterator[None]:
    """Dopo ogni test svuota le tabelle: ogni test parte da un database vuoto.

    Si usa TRUNCATE invece del rollback di una transazione esterna perché i
    test di concorrenza useranno più connessioni, ciascuna con il proprio commit.
    RESTART IDENTITY riporta gli id a 1.
    """
    yield
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))


@pytest.fixture
def db_session() -> Iterator[Session]:
    """Sessione ORM sul database di test, chiusa a fine test."""
    with SessionLocal() as session:
        yield session


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Client HTTP verso l'app in memoria (router → service → database di test)."""
    with TestClient(app) as test_client:
        yield test_client

