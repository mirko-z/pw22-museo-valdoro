"""Test degli eventi (RF07–RF10, RF16, obiettivo O4 – regole configurabili)."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import BookingStatus, EventStatus, EventType, UserRole
from tests.factories import auth_header, make_booking, make_event, make_user

NOW = datetime.now(UTC)


@pytest.fixture
def staff(db_session: Session) -> dict[str, str]:
    user = make_user(db_session, role=UserRole.STAFF)
    db_session.commit()
    return auth_header(user)


def new_event(**overrides: Any) -> dict[str, Any]:
    start = NOW + timedelta(days=10)
    data = {"title": "Visita guidata", "type": "guided_tour", "capacity": 20,
            "start_at": start.isoformat(), "end_at": (start + timedelta(hours=2)).isoformat()}
    return data | overrides


# --- Consultazione pubblica (RF07) ------------------------------------------------


def test_elenco_pubblico_solo_eventi_futuri_programmati(client: TestClient, db_session: Session) -> None:
    visitor = make_user(db_session)
    sold_out = make_event(db_session, title="Esaurito", capacity=4, max_seats_per_booking=4,
                          start_at=NOW + timedelta(days=2), end_at=NOW + timedelta(days=2, hours=1))
    make_booking(db_session, visitor, sold_out, seats=4)
    make_event(db_session, title="Più avanti", start_at=NOW + timedelta(days=5),
               end_at=NOW + timedelta(days=5, hours=1))
    make_event(db_session, title="Annullato", status=EventStatus.CANCELLED)
    make_event(db_session, title="Passato", start_at=NOW - timedelta(days=3),
               end_at=NOW - timedelta(days=3) + timedelta(hours=1))
    db_session.commit()

    events = client.get("/api/events").json()  # nessuna autenticazione richiesta
    assert [e["title"] for e in events] == ["Esaurito", "Più avanti"]  # ordinati per data
    assert events[0]["available_seats"] == 0  # gli esauriti restano visibili


def test_filtro_per_tipo(client: TestClient, db_session: Session) -> None:
    make_event(db_session, type=EventType.WORKSHOP, max_seats_per_booking=6)
    make_event(db_session, type=EventType.CONFERENCE)
    db_session.commit()
    events = client.get("/api/events", params={"type": "workshop"}).json()
    assert [e["type"] for e in events] == ["workshop"]


# --- Creazione e regole configurabili (RF08, RF09, O4) ---------------------------


def test_regole_omesse_prendono_i_default(client: TestClient, staff: dict[str, str]) -> None:
    settings = get_settings()
    response = client.post("/api/events", json=new_event(), headers=staff)
    assert response.status_code == 201
    body = response.json()
    assert body["max_seats_per_booking"] == settings.default_max_seats_per_booking
    assert body["cancellation_deadline_hours"] == settings.default_cancellation_deadline_hours
    assert body["available_seats"] == 20


def test_regole_indicate_sovrascrivono_i_default(client: TestClient, staff: dict[str, str]) -> None:
    """Laboratorio scolastico: una classe intera per prenotazione, annullamento con 72 ore di anticipo."""
    response = client.post("/api/events", headers=staff, json=new_event(
        type="workshop", capacity=50, max_seats_per_booking=30, cancellation_deadline_hours=72))
    assert response.json()["max_seats_per_booking"] == 30
    assert response.json()["cancellation_deadline_hours"] == 72


def test_default_limitato_dalla_capienza(client: TestClient, staff: dict[str, str]) -> None:
    response = client.post("/api/events", json=new_event(capacity=3), headers=staff)
    assert response.json()["max_seats_per_booking"] == 3


@pytest.mark.parametrize("overrides", [
    {"end_at": (NOW + timedelta(days=10)).isoformat()},  # fine = inizio
    {"capacity": 10, "max_seats_per_booking": 11},
    {"start_at": "2026-12-01T10:00:00"},  # senza fuso orario
    {"start_at": (NOW - timedelta(days=1)).isoformat(), "end_at": NOW.isoformat()},  # nel passato
])
def test_dati_evento_non_validi(client: TestClient, staff: dict[str, str], overrides: dict[str, Any]) -> None:
    assert client.post("/api/events", json=new_event(**overrides), headers=staff).status_code == 422


def test_solo_lo_staff_gestisce_gli_eventi(client: TestClient, db_session: Session) -> None:
    visitor = make_user(db_session)
    db_session.commit()
    assert client.post("/api/events", json=new_event()).status_code == 401
    assert client.post("/api/events", json=new_event(), headers=auth_header(visitor)).status_code == 403


# --- Modifica (RF08) ---------------------------------------------------------------


def test_modifica_parziale(client: TestClient, db_session: Session, staff: dict[str, str]) -> None:
    event = make_event(db_session)
    db_session.commit()
    response = client.patch(f"/api/events/{event.id}", json={"title": "Nuovo titolo", "capacity": 30},
                            headers=staff)
    assert response.status_code == 200
    assert response.json()["title"] == "Nuovo titolo"
    assert response.json()["available_seats"] == 30


def test_capienza_non_sotto_i_posti_confermati(client: TestClient, db_session: Session,
                                                staff: dict[str, str]) -> None:
    event = make_event(db_session, capacity=20)
    make_booking(db_session, make_user(db_session), event, seats=5)
    make_booking(db_session, make_user(db_session), event, seats=5)
    db_session.commit()
    response = client.patch(f"/api/events/{event.id}", json={"capacity": 8}, headers=staff)
    assert response.status_code == 409
    assert response.json()["code"] == "CAPACITY_BELOW_BOOKED"
    assert client.patch(f"/api/events/{event.id}", json={"capacity": 10}, headers=staff).status_code == 200


# --- Annullamento ed eliminazione (RF08, RF10) -----------------------------------


def test_annullamento_a_cascata_delle_prenotazioni(client: TestClient, db_session: Session,
                                                   staff: dict[str, str]) -> None:
    event = make_event(db_session)
    confirmed = make_booking(db_session, make_user(db_session), event)
    already = make_booking(db_session, make_user(db_session), event, status=BookingStatus.CANCELLED,
                           cancelled_at=NOW - timedelta(days=1))
    db_session.commit()

    response = client.post(f"/api/events/{event.id}/cancel", headers=staff)
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"

    rows = dict(db_session.execute(text("SELECT code, cancelled_at FROM bookings WHERE status = 'cancelled'")).all())
    assert set(rows) == {confirmed.code, already.code}
    assert rows[already.code] < rows[confirmed.code]  # la vecchia data di annullamento non cambia

    # Secondo annullamento e modifiche successive: 409
    assert client.post(f"/api/events/{event.id}/cancel", headers=staff).json()["code"] == "EVENT_CANCELLED"
    assert client.patch(f"/api/events/{event.id}", json={"title": "X" * 5}, headers=staff).status_code == 409


def test_eliminazione_solo_senza_prenotazioni(client: TestClient, db_session: Session,
                                              staff: dict[str, str]) -> None:
    with_booking = make_event(db_session)
    make_booking(db_session, make_user(db_session), with_booking)
    empty = make_event(db_session)
    db_session.commit()

    response = client.delete(f"/api/events/{with_booking.id}", headers=staff)
    assert response.status_code == 409
    assert response.json()["code"] == "EVENT_HAS_BOOKINGS"
    assert client.delete(f"/api/events/{empty.id}", headers=staff).status_code == 204
    assert client.get(f"/api/events/{empty.id}").status_code == 404


# --- Partecipanti (RF16) -----------------------------------------------------------


def test_elenco_partecipanti_solo_confermati(client: TestClient, db_session: Session,
                                             staff: dict[str, str]) -> None:
    event = make_event(db_session)
    anna = make_user(db_session, full_name="Anna Verdi")
    make_booking(db_session, anna, event, seats=3)
    make_booking(db_session, make_user(db_session), event, status=BookingStatus.CANCELLED, cancelled_at=NOW)
    db_session.commit()

    response = client.get(f"/api/events/{event.id}/participants", headers=staff)
    assert response.status_code == 200
    assert [(p["full_name"], p["seats"]) for p in response.json()] == [("Anna Verdi", 3)]
    assert client.get(f"/api/events/{event.id}/participants", headers=auth_header(anna)).status_code == 403
