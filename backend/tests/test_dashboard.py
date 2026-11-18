"""Test della dashboard su un dataset con valori calcolati a mano (RF19–RF22, obiettivo O6).

Dataset:
| Evento | Tipo | Stato | Capienza | Prenotazioni | Feedback |
|---|---|---|---:|---|---|
| A | visita guidata | concluso | 10 | 4 + 2 posti confermati, 3 annullati | 5 e 4 |
| B | laboratorio | concluso | 20 | 10 posti confermati | nessuno |
| C | conferenza | futuro | 50 | 5 confermati, 1 annullato | – |
| D | visita guidata | annullato dal museo | 10 | 2 annullati d'ufficio | – |

Valori attesi (D escluso dagli aggregati):
- A: riempimento 6/10 = 0,6; annullamento 1/3; voto 4,5; copertura 2/2 = 1
- B: riempimento 10/20 = 0,5; annullamento 0; voto non calcolabile; copertura 0/1 = 0
- Totali: annullamento (1 + 0 + 1)/(3 + 1 + 2) = 1/3; riempimento medio dei conclusi (0,6 + 0,5)/2 = 0,55;
  voto medio 4,5; copertura (2 + 0)/(2 + 1) = 2/3
- Andamento settimanale: tutte le 7 prenotazioni create, 2 delle quali datate alla settimana precedente
"""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import BookingStatus, EventStatus, EventType, Feedback, UserRole
from tests.factories import auth_header, make_booking, make_event, make_user

NOW = datetime.now(UTC)
PAST = {"start_at": NOW - timedelta(days=5), "end_at": NOW - timedelta(days=5) + timedelta(hours=2)}


@pytest.fixture
def staff_headers(db_session: Session) -> dict[str, str]:
    u = [make_user(db_session) for _ in range(5)]
    staff = make_user(db_session, role=UserRole.STAFF)
    cancelled = {"status": BookingStatus.CANCELLED, "cancelled_at": NOW - timedelta(days=6)}

    a = make_event(db_session, title="A", type=EventType.GUIDED_TOUR, capacity=10, **PAST)
    make_booking(db_session, u[0], a, seats=4)
    make_booking(db_session, u[1], a, seats=2)
    make_booking(db_session, u[2], a, seats=3, **cancelled)
    db_session.add_all([Feedback(user=u[0], event=a, rating=5), Feedback(user=u[1], event=a, rating=4)])

    b = make_event(db_session, title="B", type=EventType.WORKSHOP, capacity=20, max_seats_per_booking=10, **PAST)
    make_booking(db_session, u[3], b, seats=10, created_at=NOW - timedelta(days=7))  # settimana precedente

    c = make_event(db_session, title="C", type=EventType.CONFERENCE, capacity=50)
    make_booking(db_session, u[0], c, seats=5, created_at=NOW - timedelta(days=7))  # settimana precedente
    make_booking(db_session, u[1], c, seats=1, **cancelled)

    d = make_event(db_session, title="D", type=EventType.GUIDED_TOUR, capacity=10,
                   status=EventStatus.CANCELLED, **PAST)
    make_booking(db_session, u[4], d, seats=2, **cancelled)
    db_session.commit()
    return auth_header(staff)


def test_indicatori_complessivi(client: TestClient, staff_headers: dict[str, str]) -> None:
    assert client.get("/api/dashboard/overview", headers=staff_headers).json() == {
        "events_upcoming": 1,
        "events_concluded": 2,
        "bookings_total": 6,
        "bookings_cancelled": 2,
        "cancellation_rate": 0.3333,
        "average_fill_rate": 0.55,
        "feedback_count": 2,
        "average_rating": 4.5,
        "feedback_coverage": 0.6667,
    }


def test_indicatori_per_evento(client: TestClient, staff_headers: dict[str, str]) -> None:
    rows = {r["title"]: r for r in client.get("/api/dashboard/events", headers=staff_headers).json()}
    pick = ("fill_rate", "cancellation_rate", "average_rating", "feedback_coverage")
    assert {k: rows["A"][k] for k in pick} == {"fill_rate": 0.6, "cancellation_rate": 0.3333,
                                               "average_rating": 4.5, "feedback_coverage": 1.0}
    assert {k: rows["B"][k] for k in pick} == {"fill_rate": 0.5, "cancellation_rate": 0.0,
                                               "average_rating": None, "feedback_coverage": 0.0}
    assert rows["C"]["feedback_coverage"] is None  # evento non ancora concluso
    assert rows["D"]["status"] == "cancelled"  # visibile nell'elenco, escluso dagli aggregati


def test_indicatori_per_tipo(client: TestClient, staff_headers: dict[str, str]) -> None:
    rows = {r["type"]: r for r in client.get("/api/dashboard/types", headers=staff_headers).json()}
    assert rows["guided_tour"] == {"type": "guided_tour", "events_concluded": 1, "average_fill_rate": 0.6,
                                   "feedback_count": 2, "average_rating": 4.5}
    assert rows["workshop"]["average_rating"] is None
    assert rows["conference"]["events_concluded"] == 0


def test_andamento_settimanale(client: TestClient, staff_headers: dict[str, str]) -> None:
    weeks = client.get("/api/dashboard/weekly", params={"weeks": 3}, headers=staff_headers).json()
    assert len(weeks) == 3
    today = datetime.now(ZoneInfo("Europe/Rome")).date()
    assert weeks[-1]["week_start"] == (today - timedelta(days=today.weekday())).isoformat()  # lunedì
    # Conta tutte le prenotazioni create (anche quelle poi annullate e quelle dell'evento D):
    # misura l'attività di prenotazione, 7 in totale: 2 la settimana scorsa, 5 in quella corrente
    assert [w["bookings"] for w in weeks] == [0, 2, 5]
    assert weeks[1]["seats"] == 15


def test_dashboard_riservata_allo_staff(client: TestClient, db_session: Session) -> None:
    visitor = make_user(db_session)
    db_session.commit()
    assert client.get("/api/dashboard/overview", headers=auth_header(visitor)).status_code == 403
    assert client.get("/api/dashboard/overview").status_code == 401
