"""Test dei dati di esempio: il seed deve rispettare le stesse regole dell'applicazione."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app import seed
from app.core.config import Settings
from app.models import Booking, Event, Feedback, User
from app.seed import COMMENTS, STAFF_ACCOUNTS, TEACHERS, VISITORS, DemoDataSeeder, comment_band
from tests.factories import FAKE_HASH, make_user

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)


@pytest.fixture
def fast_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sostituisce bcrypt con un hash fittizio: 23 hash veri costerebbero ~8 secondi.

    ``monkeypatch`` cambia un attributo solo per la durata del test.
    """
    monkeypatch.setattr(seed, "hash_password", lambda _password: FAKE_HASH)


def scalar(session: Session, sql: str) -> int:
    return session.scalar(text(sql))  # type: ignore[return-value]


@pytest.mark.usefixtures("fast_hash")
def test_seed_popola_il_database_rispettando_le_regole(db_session: Session) -> None:
    assert DemoDataSeeder(db_session, "password-demo", now=NOW).run() is True

    assert db_session.scalar(select(func.count()).select_from(User)) == len(STAFF_ACCOUNTS + TEACHERS + VISITORS)
    assert db_session.scalar(select(func.count()).select_from(Event)) == len(seed.DEMO_EVENTS)
    assert db_session.scalar(select(func.count()).select_from(Booking)) > 0

    # Nessun overbooking: posti confermati <= capienza per ogni evento
    assert scalar(db_session, """
        SELECT count(*) FROM events e
        WHERE (SELECT coalesce(sum(seats), 0) FROM bookings b
               WHERE b.event_id = e.id AND b.status = 'confirmed') > e.capacity
    """) == 0
    # Nessuna prenotazione oltre il massimo per prenotazione dell'evento
    assert scalar(db_session, """
        SELECT count(*) FROM bookings b JOIN events e ON e.id = b.event_id
        WHERE b.seats > e.max_seats_per_booking
    """) == 0
    # Un evento annullato non ha prenotazioni confermate (RF10)
    assert scalar(db_session, """
        SELECT count(*) FROM bookings b JOIN events e ON e.id = b.event_id
        WHERE e.status = 'cancelled' AND b.status = 'confirmed'
    """) == 0
    # Feedback solo con prenotazione confermata, per eventi conclusi e non annullati (RF17)
    assert scalar(db_session, """
        SELECT count(*) FROM feedback f JOIN events e ON e.id = f.event_id
        WHERE e.status = 'cancelled' OR e.end_at > f.created_at
           OR NOT EXISTS (SELECT 1 FROM bookings b
                          WHERE b.user_id = f.user_id AND b.event_id = f.event_id
                            AND b.status = 'confirmed')
    """) == 0
    # Nessuna data nel futuro rispetto al momento del seed
    assert scalar(db_session, f"""
        SELECT count(*) FROM bookings
        WHERE created_at > '{NOW.isoformat()}' OR cancelled_at > '{NOW.isoformat()}'
    """) == 0
    # Casi utili alle dimostrazioni: almeno un evento futuro esaurito e uno senza prenotazioni
    assert scalar(db_session, f"""
        SELECT count(*) FROM events e WHERE e.start_at > '{NOW.isoformat()}' AND e.capacity =
            (SELECT coalesce(sum(seats), 0) FROM bookings b WHERE b.event_id = e.id AND b.status = 'confirmed')
    """) >= 1
    assert scalar(db_session, "SELECT count(*) FROM events e WHERE NOT EXISTS "
                              "(SELECT 1 FROM bookings b WHERE b.event_id = e.id)") >= 1
    # Programmazione di circa sei mesi; laboratori scolastici (mattina) solo nei giorni feriali
    # (EXTRACT(ISODOW): 1 = lunedì … 7 = domenica, nel fuso di Roma)
    assert scalar(db_session, f"""
        SELECT max(start_at) - '{NOW.isoformat()}'::timestamptz >= interval '170 days' FROM events
    """)
    assert scalar(db_session, """
        SELECT count(*) FROM events
        WHERE type = 'workshop' AND (start_at AT TIME ZONE 'Europe/Rome')::time < '12:00'
          AND EXTRACT(ISODOW FROM start_at AT TIME ZONE 'Europe/Rome') >= 6
    """) == 0
    # Dati fittizi: solo domini riservati alla documentazione (RFC 2606)
    assert scalar(db_session, "SELECT count(*) FROM users WHERE email NOT LIKE '%example%'") == 0


@pytest.mark.usefixtures("fast_hash")
def test_commenti_coerenti_con_voto_e_tipo(db_session: Session) -> None:
    """Un commento critico non deve comparire accanto a un 5/5, né uno sulla guida sotto una conferenza."""
    DemoDataSeeder(db_session, "password-demo", now=NOW).run()
    rows = db_session.execute(
        select(Feedback.rating, Feedback.comment, Event.type).join(Event).where(Feedback.comment.is_not(None))
    ).all()
    assert rows, "il seed deve generare almeno un commento"
    for rating, comment, event_type in rows:
        assert comment in COMMENTS[comment_band(rating)][event_type], (rating, event_type, comment)


@pytest.mark.usefixtures("fast_hash")
def test_seed_idempotente(db_session: Session) -> None:
    """Al secondo avvio del container il seed non duplica i dati."""
    make_user(db_session)
    db_session.commit()
    assert DemoDataSeeder(db_session, "password-demo", now=NOW).run() is False
    assert db_session.scalar(select(func.count()).select_from(User)) == 1


def _settings(**overrides: object) -> Settings:
    """Settings con valori espliciti: quelli passati al costruttore prevalgono
    sulle variabili d'ambiente (nel container SEED_DEMO_* sono impostate dal .env)."""
    base = {"postgres_user": "u", "postgres_password": "p", "postgres_db": "d", "jwt_secret": "x" * 32,
            "seed_demo_data": False, "seed_demo_password": ""}
    return Settings(**(base | overrides))  # type: ignore[arg-type]


def test_seed_disattivato_non_fa_nulla(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(seed, "get_settings", lambda: _settings(seed_demo_data=False))
    assert seed.main(["--if-enabled"]) == 0


def test_seed_rifiutato_in_produzione(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(seed, "get_settings", lambda: _settings(
        app_env="production", seed_demo_data=True, seed_demo_password="password-demo"))
    assert seed.main(["--if-enabled"]) == 1


def test_seed_richiede_una_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(seed, "get_settings", lambda: _settings(seed_demo_data=True))
    assert seed.main([]) == 1
