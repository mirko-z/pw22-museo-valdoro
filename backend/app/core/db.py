"""Connessione al database: engine, fabbrica di sessioni e dipendenza FastAPI."""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

# L'engine gestisce un pool di connessioni riutilizzabili verso PostgreSQL (come le connessioni persistenti di PDO, ma condivise tra i thread).
# pool_pre_ping verifica la connessione prima di usarla: se il database è stato riavviato, la connessione morta viene sostituita invece di dare errore.
# CONNECT_ARGS fissa il fuso della sessione a UTC: le date timestamptz tornano sempre in UTC (RNF12), qualunque sia il fuso configurato nel server PostgreSQL.Prima lo garantiva solo TZ=UTC nel container db di Docker Compose.
CONNECT_ARGS = {"options": "-c timezone=UTC"}

engine = create_engine(get_settings().database_url, pool_pre_ping=True, connect_args=CONNECT_ARGS)

 
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """Fornisce una sessione per la durata di una richiesta HTTP.

    È una *dipendenza* di FastAPI: gli endpoint la dichiarano nei parametri e
    il framework la chiama per loro (dependency injection). Il ``yield``
    consegna la sessione all'endpoint; quando la risposta è pronta l'esecuzione
    riprende dopo il ``yield`` e il blocco ``with`` chiude la sessione,
    restituendo la connessione al pool anche in caso di eccezione.
    """
    with SessionLocal() as session:
        yield session
