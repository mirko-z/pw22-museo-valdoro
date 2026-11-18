"""Test del feedback: casi ammessi e casi limite (RF17, RF18, obiettivo O5)."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import BookingStatus, Event, EventStatus, User, UserRole
from tests.factories import auth_header, make_booking, make_event, make_user

NOW = datetime.now(UTC)


def past_event(db: Session, **overrides: object) -> Event:
    start = NOW - timedelta(days=3)
    return make_event(db, start_at=start, end_at=start + timedelta(hours=2), **overrides)


def send(client: TestClient, user: User, event_id: int, rating: int = 5):  # type: ignore[no-untyped-def]
    return client.post(f"/api/events/{event_id}/feedback", json={"rating": rating, "comment": " Bella visita "},
                       headers=auth_header(user))


def test_feedback_ammesso_e_visibile_allo_staff(client: TestClient, db_session: Session) -> None:
    visitor, staff = make_user(db_session, full_name="Anna Verdi"), make_user(db_session, role=UserRole.STAFF)
    event = past_event(db_session)
    make_booking(db_session, visitor, event)
    db_session.commit()

    # Prima: l'area visitatore segnala che il feedback si può lasciare
    mine = client.get("/api/bookings/me", headers=auth_header(visitor)).json()[0]
    assert mine["can_leave_feedback"] is True and mine["my_rating"] is None

    response = send(client, visitor, event.id, rating=4)
    assert response.status_code == 201
    assert response.json()["comment"] == "Bella visita"

    listed = client.get(f"/api/events/{event.id}/feedback", headers=auth_header(staff)).json()
    assert [(f["full_name"], f["rating"]) for f in listed] == [("Anna Verdi", 4)]

    # Dopo: voto registrato, nessun secondo feedback
    mine = client.get("/api/bookings/me", headers=auth_header(visitor)).json()[0]
    assert mine["can_leave_feedback"] is False and mine["my_rating"] == 4


def test_evento_non_concluso(client: TestClient, db_session: Session) -> None:
    visitor = make_user(db_session)
    event = make_event(db_session)  # tra 7 giorni
    make_booking(db_session, visitor, event)
    db_session.commit()
    assert send(client, visitor, event.id).json()["code"] == "EVENT_NOT_ENDED"


def test_evento_annullato(client: TestClient, db_session: Session) -> None:
    visitor = make_user(db_session)
    event = past_event(db_session, status=EventStatus.CANCELLED)
    make_booking(db_session, visitor, event, status=BookingStatus.CANCELLED, cancelled_at=NOW - timedelta(days=5))
    db_session.commit()
    assert send(client, visitor, event.id).json()["code"] == "EVENT_CANCELLED"


@pytest.mark.parametrize("with_cancelled_booking", [False, True])
def test_senza_prenotazione_confermata(client: TestClient, db_session: Session,
                                       with_cancelled_booking: bool) -> None:
    visitor = make_user(db_session)
    event = past_event(db_session)
    if with_cancelled_booking:
        make_booking(db_session, visitor, event, status=BookingStatus.CANCELLED, cancelled_at=NOW - timedelta(days=5))
    db_session.commit()
    response = send(client, visitor, event.id)
    assert response.status_code == 403
    assert response.json()["code"] == "NO_CONFIRMED_BOOKING"


def test_un_solo_feedback_per_evento(client: TestClient, db_session: Session) -> None:
    visitor = make_user(db_session)
    event = past_event(db_session)
    make_booking(db_session, visitor, event)
    db_session.commit()
    assert send(client, visitor, event.id).status_code == 201
    assert send(client, visitor, event.id, rating=1).json()["code"] == "FEEDBACK_EXISTS"


@pytest.mark.parametrize("rating", [0, 6])
def test_voto_fuori_intervallo(client: TestClient, db_session: Session, rating: int) -> None:
    visitor = make_user(db_session)
    event = past_event(db_session)
    make_booking(db_session, visitor, event)
    db_session.commit()
    assert send(client, visitor, event.id, rating=rating).status_code == 422
