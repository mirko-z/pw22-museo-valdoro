"""Ambiente di esecuzione delle migrazioni Alembic.

Alembic esegue questo file a ogni comando (``alembic upgrade head``, ecc.).
Qui si collega al database indicato da Settings e confronta lo schema con
``Base.metadata``, cioè con i modelli ORM.
"""

from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context
from app.core.config import get_settings
from app.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Metadati dei modelli: servono a "alembic revision --autogenerate" e al test
# che verifica che migrazioni e modelli descrivano lo stesso schema.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Genera lo script SQL senza connettersi (``alembic upgrade head --sql``).

    Utile per leggere il DDL prodotto dalle migrazioni, per esempio nel report.
    """
    context.configure(
        url=get_settings().database_url.render_as_string(hide_password=False),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Applica le migrazioni al database.

    Se il chiamante (per esempio i test) passa già una connessione in
    ``config.attributes["connection"]`` si usa quella; altrimenti se ne apre
    una nuova. NullPool: una sola connessione, chiusa a fine migrazione.
    """
    connection = config.attributes.get("connection")
    if connection is not None:
        _run_with(connection)
        return

    engine = create_engine(get_settings().database_url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        _run_with(connection)


def _run_with(connection) -> None:  # type: ignore[no-untyped-def]
    context.configure(connection=connection, target_metadata=target_metadata)
    # In PostgreSQL anche il DDL è transazionale: se una migrazione fallisce
    # a metà, nessuna modifica resta applicata.
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
