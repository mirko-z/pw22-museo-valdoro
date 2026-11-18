"""Test funzionali delle prenotazioni via API (RF11–RF15, obiettivi O2 e O4).

Una verifica per regola dello scenario UC04 e dell'annullamento. La
correttezza in concorrenza è in test_booking_concurrency.py.
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import BookingStatus, EventStatus, EventType, User, UserRole
from app.services.booking_codes import ALPHABET, CODE_LENGTH
from tests.factories import auth_header, make_booking, make_event, make_user

NOW = datetime.now(UTC)


@pytest.fixture
def visitor(db_session: Session) -> User:
    user = make_user(db_session)
    db_session.commit()
    return user


def book(client: TestClient, user: User, event_id: int, seats: int = 2):  # type: ignore[no-untyped-def]
    return client.post("/api/bookings", json={"event_id": event_id, "seats": seats}, headers=auth_header(user))


# --- Prenotazione (RF11, RF12) --------------------------------------------------------


def test_prenotazione_confermata_con_codice_non_sequenziale(client: TestClient, db_session: Session,
                                                            visitor: User) -> None:
    event = make_event(db_session, capacity=10)
    db_session.commit()
    response = book(client, visitor, event.id, seats=3)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "confirmed" and body["seats"] == 3
    assert len(body["code"]) == CODE_LENGTH and set(body["code"]) <= set(ALPHABET)
    assert body["can_cancel"] is True
    assert client.get(f"/api/events/{event.id}").json()["available_seats"] == 7


def test_massimo_posti_per_prenotazione(client: TestClient, db_session: Session, visitor: User) -> None:
    """La regola dell'evento (O4) prevale: qui 4 posti al massimo."""
    event = make_event(db_session, max_seats_per_booking=4)
    db_session.commit()
    response = book(client, visitor, event.id, seats=5)
    assert response.status_code == 422
    assert response.json()["code"] == "MAX_SEATS_EXCEEDED"
    assert book(client, visitor, event.id, seats=4).status_code == 201


def test_posti_insufficienti(client: TestClient, db_session: Session, visitor: User) -> None:
    event = make_event(db_session, capacity=5)
    make_booking(db_session, make_user(db_session), event, seats=4)
    db_session.commit()
    response = book(client, visitor, event.id, seats=2)
    assert response.status_code == 409
    assert response.json() == {"detail": "Posti insufficienti: ne restano 1.", "code": "SEATS_UNAVAILABLE"}


def test_una_sola_prenotazione_attiva_poi_riprenotazione(client: TestClient, db_session: Session,
                                                         visitor: User) -> None:
    """RF13 / O2: la seconda prenotazione attiva è rifiutata; dopo l'annullamento si riprenota."""
    event = make_event(db_session)
    db_session.commit()
    first = book(client, visitor, event.id).json()
    second = book(client, visitor, event.id)
    assert second.status_code == 409
    assert second.json()["code"] == "ALREADY_BOOKED"

    client.post(f"/api/bookings/{first['code']}/cancel", headers=auth_header(visitor))
    assert book(client, visitor, event.id, seats=4).status_code == 201


@pytest.mark.parametrize("overrides", [
    {"status": EventStatus.CANCELLED},
    {"start_at": NOW - timedelta(minutes=10), "end_at": NOW + timedelta(hours=1)},  # già iniziato
])
def test_evento_non_prenotabile(client: TestClient, db_session: Session, visitor: User,
                                overrides: dict[str, object]) -> None:
    event = make_event(db_session, **overrides)
    db_session.commit()
    assert book(client, visitor, event.id).json()["code"] == "EVENT_NOT_BOOKABLE"


def test_evento_inesistente(client: TestClient, visitor: User) -> None:
    assert book(client, visitor, 999).status_code == 404


def test_solo_i_visitatori_prenotano(client: TestClient, db_session: Session) -> None:
    staff = make_user(db_session, role=UserRole.STAFF)
    event = make_event(db_session)
    db_session.commit()
    assert book(client, staff, event.id).status_code == 403


# --- Annullamento e consultazione (RF14, RF15) --------------------------------------


def test_annullamento_entro_il_termine(client: TestClient, db_session: Session, visitor: User) -> None:
    event = make_event(db_session)  # inizia tra 7 giorni, termine di 24 ore
    db_session.commit()
    code = book(client, visitor, event.id).json()["code"]

    response = client.post(f"/api/bookings/{code.lower()}/cancel", headers=auth_header(visitor))
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert response.json()["cancelled_at"] is not None

    again = client.post(f"/api/bookings/{code}/cancel", headers=auth_header(visitor))
    assert again.status_code == 409  # non idempotente di proposito: il client sa che era già annullata
    assert again.json()["code"] == "ALREADY_CANCELLED"


def test_annullamento_oltre_il_termine(client: TestClient, db_session: Session, visitor: User) -> None:
    """Laboratorio con termine di 72 ore che inizia tra 2 giorni: troppo tardi per annullare."""
    start = NOW + timedelta(days=2)
    event = make_event(db_session, start_at=start, end_at=start + timedelta(hours=2),
                       cancellation_deadline_hours=72)
    booking = make_booking(db_session, visitor, event)
    db_session.commit()
    response = client.post(f"/api/bookings/{booking.code}/cancel", headers=auth_header(visitor))
    assert response.status_code == 409
    assert response.json()["code"] == "DEADLINE_PASSED"


def test_prenotazione_altrui_risponde_404(client: TestClient, db_session: Session, visitor: User) -> None:
    """Non 403: non si rivela che il codice esiste (OWASP A01)."""
    other_booking = make_booking(db_session, make_user(db_session), make_event(db_session))
    db_session.commit()
    response = client.post(f"/api/bookings/{other_booking.code}/cancel", headers=auth_header(visitor))
    assert response.status_code == 404
    db_session.refresh(other_booking)
    assert other_booking.status is BookingStatus.CONFIRMED


def test_le_mie_prenotazioni(client: TestClient, db_session: Session, visitor: User) -> None:
    mine = make_booking(db_session, visitor, make_event(db_session, title="Mia", type=EventType.WORKSHOP))
    make_booking(db_session, make_user(db_session), make_event(db_session, title="Altrui"))
    db_session.commit()
    response = client.get("/api/bookings/me", headers=auth_header(visitor))
    assert [(b["code"], b["event_title"], b["event_type"]) for b in response.json()] == [(mine.code, "Mia", "workshop")]
