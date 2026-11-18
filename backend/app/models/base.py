"""Classe base dei modelli ORM e convenzioni comuni."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, MetaData
from sqlalchemy.orm import DeclarativeBase

# Convenzione per i nomi di vincoli e indici. Senza, PostgreSQL genera nomi
# automatici diversi da un'installazione all'altra; con nomi stabili la
# migrazione è ripetibile e un errore di integrità dice quale vincolo è violato
# (es. "ck_events_end_after_start"), cosa che il service usa per tradurlo
# in un errore di dominio.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base di tutti i modelli.

    Ogni classe che eredita da ``Base`` corrisponde a una tabella. A differenza
    di un array associativo restituito da PDO, una riga diventa un oggetto con
    attributi tipizzati (``Mapped[int]``, ``Mapped[str]``...): l'editor e il
    type checker sanno quali campi esistono e di che tipo sono.
    """

    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    # Ogni attributo annotato come ``datetime`` diventa una colonna
    # ``timestamptz``: istanti assoluti, memorizzati in UTC (RNF12).
    type_annotation_map = {datetime: DateTime(timezone=True)}


def str_enum(enum_cls: type[StrEnum], length: int) -> Enum:
    """Colonna ``varchar(length)`` con vincolo CHECK sui valori dell'enumerazione.

    ``native_enum=False`` evita il tipo ENUM di PostgreSQL, che è scomodo da
    modificare con le migrazioni: si usa un ``varchar`` con un CHECK, come
    previsto dal modello logico. In Python la colonna restituisce il membro
    dell'enumerazione (es. ``UserRole.STAFF``) invece di una stringa libera.
    """
    return Enum(
        enum_cls,
        native_enum=False,
        create_constraint=True,
        length=length,
        name=enum_cls.__name__.lower(),
        # Nel database si salva il valore ("staff"), non il nome del membro ("STAFF")
        values_callable=lambda members: [m.value for m in members],
        validate_strings=True,
    )
