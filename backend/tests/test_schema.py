"""Test dello schema del database: migrazioni, vincoli e indici (RNF02, RF13).

Questi test scrivono direttamente con l'ORM, senza passare dai service:
verificano che le regole di integrità siano garantite dal DBMS anche se il
codice applicativo avesse un errore (difesa in profondità).
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from app.core.db import engine
from app.models import Base, BookingStatus, Event, Feedback
from tests.factories import make_booking, make_event, make_user


def violated_constraint(exc: pytest.ExceptionInfo[IntegrityError]) -> str:
    """Nome del vincolo violato, come lo riporta PostgreSQL.

    psycopg espone i dettagli dell'errore del server in ``diag``: è ciò che
    permetterà ai service di tradurre una violazione in un errore di dominio.
    """
    return exc.value.orig.diag.constraint_name  # type: ignore[union-attr]


# --- Migrazioni ----------------------------------------------------------------


def test_migrazioni_allineate_ai_modelli() -> None:
    """Lo schema creato da Alembic coincide con quello descritto dai modelli ORM.

    Se si modifica un modello senza scrivere la migrazione (o viceversa),
    compare_metadata restituisce le differenze e il test fallisce.
    """
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []


def test_vincoli_check_presenti() -> None:
    """Tutti i CHECK del modello logico esistono con il nome previsto."""
    expected = {
        "ck_users_userrole",
        "ck_events_eventtype",
        "ck_events_eventstatus",
        "ck_events_end_after_start",
        "ck_events_capacity_positive",
        "ck_events_price_non_negative",
        "ck_events_max_seats_valid",
        "ck_events_deadline_non_negative",
        "ck_bookings_bookingstatus",
        "ck_bookings_seats_positive",
        "ck_bookings_cancelled_at_consistent",
        "ck_feedback_rating_range",
        "ck_feedback_comment_length",
    }
    with engine.connect() as conn:
        found = set(conn.scalars(text(
            "SELECT conname FROM pg_constraint "
            "WHERE contype = 'c' AND connamespace = 'public'::regnamespace"
        )))
    assert found == expected


def test_indici_previsti() -> None:
    """Indici sulle chiavi esterne, su lower(email) e indice parziale sulle prenotazioni attive."""
    with engine.connect() as conn:
        indexes = dict(conn.execute(text(
            "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'public'"
        )).all())
    for name in ("ix_bookings_event_id", "ix_bookings_user_id", "ix_feedback_event_id", "ix_events_start_at"):
        assert name in indexes
    assert "lower((email)::text)" in indexes["uq_users_email_lower"]
    assert "UNIQUE" in indexes["uq_bookings_active"]
    assert "WHERE ((status)::text = 'confirmed'::text)" in indexes["uq_bookings_active"]


# --- users -----------------------------------------------------------------------


def test_email_univoca_senza_distinzione_tra_maiuscole(db_session: Session) -> None:
    make_user(db_session, email="mario.rossi@example.com")
    with pytest.raises(IntegrityError) as exc:
        make_user(db_session, email="Mario.Rossi@Example.COM")
    assert violated_constraint(exc) == "uq_users_email_lower"


def test_ruolo_non_ammesso_rifiutato_dal_database(db_session: Session) -> None:
    """Il CHECK sul ruolo vale anche per chi scrive SQL senza passare dall'ORM."""
    with pytest.raises(IntegrityError) as exc:
        db_session.execute(text(
            "INSERT INTO users (email, password_hash, full_name, role) "
            "VALUES ('x@example.com', 'h', 'X', 'guest')"
        ))
    assert violated_constraint(exc) == "ck_users_userrole"


def test_ruolo_non_ammesso_rifiutato_dall_orm(db_session: Session) -> None:
    """Primo livello di difesa: l'enumerazione Python rifiuta il valore prima del database."""
    with pytest.raises(StatementError):
        make_user(db_session, role="guest")


def test_ruolo_di_default_visitor(db_session: Session) -> None:
    db_session.execute(text(
        "INSERT INTO users (email, password_hash, full_name) VALUES ('v@example.com', 'h', 'V')"
    ))
    assert db_session.scalar(text("SELECT role FROM users")) == "visitor"


# --- events ----------------------------------------------------------------------

START = datetime(2026, 12, 5, 9, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"start_at": START, "end_at": START}, "ck_events_end_after_start"),
        ({"start_at": START, "end_at": START - timedelta(hours=1)}, "ck_events_end_after_start"),
        ({"capacity": 0, "max_seats_per_booking": 0}, "ck_events_capacity_positive"),
        ({"price": Decimal("-1.00")}, "ck_events_price_non_negative"),
        ({"capacity": 10, "max_seats_per_booking": 11}, "ck_events_max_seats_valid"),
        ({"max_seats_per_booking": 0}, "ck_events_max_seats_valid"),
        ({"cancellation_deadline_hours": -1}, "ck_events_deadline_non_negative"),
    ],
)
def test_vincoli_evento(db_session: Session, overrides: dict[str, Any], constraint: str) -> None:
    """Ogni CHECK su events rifiuta i valori non validi (parametrize = un caso per riga)."""
    with pytest.raises(IntegrityError) as exc:
        make_event(db_session, **overrides)
    assert violated_constraint(exc) == constraint


def test_evento_programmato_di_default(db_session: Session) -> None:
    event = make_event(db_session)
    db_session.refresh(event)
    assert event.status == "scheduled"
    assert event.created_at is not None


def test_date_salvate_come_istanti_assoluti(db_session: Session) -> None:
    """timestamptz: un orario di Roma viene riletto come lo stesso istante, in UTC (RNF12)."""
    rome_start = datetime(2026, 12, 5, 10, 0, tzinfo=ZoneInfo("Europe/Rome"))
    event = make_event(db_session, start_at=rome_start, end_at=rome_start + timedelta(hours=1))
    db_session.commit()
    db_session.expire_all()

    reloaded = db_session.get(Event, event.id)
    assert reloaded is not None
    assert reloaded.start_at == rome_start  # stesso istante
    assert reloaded.start_at.utcoffset() == timedelta(0)  # restituito in UTC
    assert reloaded.start_at.hour == 9  # 10:00 a Roma (CET, UTC+1) = 09:00 UTC


# --- bookings --------------------------------------------------------------------


def test_una_sola_prenotazione_attiva_per_utente_ed_evento(db_session: Session) -> None:
    """RF13: l'indice univoco parziale rifiuta una seconda prenotazione confermata."""
    user, event = make_user(db_session), make_event(db_session)
    make_booking(db_session, user, event)
    with pytest.raises(IntegrityError) as exc:
        make_booking(db_session, user, event)
    assert violated_constraint(exc) == "uq_bookings_active"


def test_riprenotazione_dopo_annullamento_consentita(db_session: Session) -> None:
    """L'indice è parziale: le prenotazioni annullate non contano."""
    user, event = make_user(db_session), make_event(db_session)
    now = datetime.now(UTC)
    make_booking(db_session, user, event, status=BookingStatus.CANCELLED, cancelled_at=now)
    make_booking(db_session, user, event, status=BookingStatus.CANCELLED, cancelled_at=now)
    make_booking(db_session, user, event)  # nuova prenotazione attiva
    db_session.commit()


def test_utenti_diversi_stesso_evento(db_session: Session) -> None:
    event = make_event(db_session)
    make_booking(db_session, make_user(db_session), event)
    make_booking(db_session, make_user(db_session), event)
    db_session.commit()


@pytest.mark.parametrize("seats", [0, -2])
def test_posti_positivi(db_session: Session, seats: int) -> None:
    with pytest.raises(IntegrityError) as exc:
        make_booking(db_session, make_user(db_session), make_event(db_session), seats=seats)
    assert violated_constraint(exc) == "ck_bookings_seats_positive"


@pytest.mark.parametrize(
    ("status", "cancelled_at"),
    [
        (BookingStatus.CANCELLED, None),  # annullata senza data
        (BookingStatus.CONFIRMED, datetime(2026, 10, 1, tzinfo=UTC)),  # confermata con data di annullamento
    ],
)
def test_coerenza_stato_e_data_annullamento(
    db_session: Session, status: BookingStatus, cancelled_at: datetime | None
) -> None:
    with pytest.raises(IntegrityError) as exc:
        make_booking(db_session, make_user(db_session), make_event(db_session),
                     status=status, cancelled_at=cancelled_at)
    assert violated_constraint(exc) == "ck_bookings_cancelled_at_consistent"


def test_codice_prenotazione_univoco(db_session: Session) -> None:
    event = make_event(db_session)
    make_booking(db_session, make_user(db_session), event, code="ABCDEFGH23")
    with pytest.raises(IntegrityError) as exc:
        make_booking(db_session, make_user(db_session), event, code="ABCDEFGH23")
    assert violated_constraint(exc) == "uq_bookings_code"


def test_evento_con_prenotazioni_non_eliminabile(db_session: Session) -> None:
    """ON DELETE RESTRICT: lo storico delle prenotazioni non si perde."""
    event = make_event(db_session)
    make_booking(db_session, make_user(db_session), event)
    db_session.commit()
    with pytest.raises(IntegrityError) as exc:
        db_session.execute(text("DELETE FROM events WHERE id = :id"), {"id": event.id})
    assert violated_constraint(exc) == "fk_bookings_event_id_events"


def test_evento_senza_prenotazioni_eliminabile(db_session: Session) -> None:
    event = make_event(db_session)
    db_session.commit()
    db_session.execute(text("DELETE FROM events WHERE id = :id"), {"id": event.id})
    db_session.commit()
    # Si interroga il database: session.get() restituirebbe l'oggetto ancora
    # presente nella identity map della sessione (expire_on_commit=False)
    assert db_session.scalar(text("SELECT count(*) FROM events")) == 0


# --- feedback --------------------------------------------------------------------


@pytest.mark.parametrize("rating", [0, 6])
def test_voto_tra_1_e_5(db_session: Session, rating: int) -> None:
    user, event = make_user(db_session), make_event(db_session)
    db_session.add(Feedback(user=user, event=event, rating=rating))
    with pytest.raises(IntegrityError) as exc:
        db_session.flush()
    assert violated_constraint(exc) == "ck_feedback_rating_range"


def test_commento_massimo_1000_caratteri(db_session: Session) -> None:
    user, event = make_user(db_session), make_event(db_session)
    db_session.add(Feedback(user=user, event=event, rating=4, comment="è" * 1000))
    db_session.flush()  # 1000 caratteri (non byte): ammesso

    other = make_user(db_session)
    db_session.add(Feedback(user=other, event=event, rating=4, comment="x" * 1001))
    with pytest.raises(IntegrityError) as exc:
        db_session.flush()
    assert violated_constraint(exc) == "ck_feedback_comment_length"


def test_un_feedback_per_utente_ed_evento(db_session: Session) -> None:
    user, event = make_user(db_session), make_event(db_session)
    db_session.add(Feedback(user=user, event=event, rating=5))
    db_session.flush()
    db_session.add(Feedback(user=user, event=event, rating=3))
    with pytest.raises(IntegrityError) as exc:
        db_session.flush()
    assert violated_constraint(exc) == "uq_feedback_user_id_event_id"
