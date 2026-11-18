"""Test di concorrenza: nessun overbooking con richieste simultanee (RNF01, obiettivo O1).

Scenario: un evento da 10 posti con 8 già confermati; 10 visitatori diversi
chiedono 1 posto nello stesso istante. Risultato corretto: 2 prenotazioni
accettate, 8 rifiutate, posti confermati = capienza.

Ogni thread ha la **propria sessione e quindi la propria connessione** a
PostgreSQL, come due richieste HTTP servite da thread diversi del server.
Un ``threading.Barrier`` fa partire tutti i thread insieme.

Lo stesso test gira con entrambe le strategie. Con ``NaiveBookingStrategy``
è marcato ``xfail(strict=True)``: DEVE fallire. Se un giorno passasse, la
suite diventerebbe rossa, perché vorrebbe dire che il test non è più in
grado di rilevare la race condition e quindi non dimostra nulla.
"""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.core.errors import DomainError
from app.models import User
from app.services.booking_strategies import BookingStrategy, LockingBookingStrategy, NaiveBookingStrategy
from tests.factories import make_booking, make_event, make_user

CAPACITY = 10
ALREADY_BOOKED = 8
REQUESTS = 10
# Ritardo tra controllo e inserimento: allarga la finestra critica perché la
# race sia riproducibile su qualsiasi macchina. Verifica dell'11/10/2026:
# anche con DELAY = 0 la strategia naive ha confermato 16–18 posti su 10
# in 5 esecuzioni su 5; il ritardo è solo un margine di sicurezza.
DELAY = 0.05


def run_concurrent_requests(strategy: BookingStrategy, event_id: int, user_ids: list[int]) -> list[str]:
    """Lancia una richiesta per utente, tutte insieme; restituisce l'esito di ciascuna."""
    barrier = threading.Barrier(len(user_ids))

    def attempt(user_id: int) -> str:
        # Ogni thread: propria sessione, propria connessione, propria transazione
        with SessionLocal() as session:
            user = session.get_one(User, user_id)
            barrier.wait()  # partenza simultanea
            try:
                strategy.reserve(session, user, event_id, seats=1)
                return "confirmed"
            except DomainError as exc:
                return exc.code

    with ThreadPoolExecutor(max_workers=len(user_ids)) as pool:
        return list(pool.map(attempt, user_ids))


@pytest.mark.parametrize("strategy_cls", [
    LockingBookingStrategy,
    pytest.param(NaiveBookingStrategy,
                 marks=pytest.mark.xfail(strict=True, reason="race condition attesa: overbooking senza lock")),
])
def test_nessun_overbooking_con_richieste_simultanee(db_session: Session,
                                                     strategy_cls: type[BookingStrategy]) -> None:
    event = make_event(db_session, capacity=CAPACITY)
    make_booking(db_session, make_user(db_session), event, seats=ALREADY_BOOKED)
    user_ids = [make_user(db_session).id for _ in range(REQUESTS)]
    db_session.commit()

    outcomes = run_concurrent_requests(strategy_cls(critical_section_delay=DELAY), event.id, user_ids)

    confirmed_seats = db_session.scalar(text(
        "SELECT sum(seats) FROM bookings WHERE event_id = :id AND status = 'confirmed'"), {"id": event.id})
    assert confirmed_seats <= CAPACITY, f"overbooking: {confirmed_seats} posti confermati su {CAPACITY}"
    assert outcomes.count("confirmed") == CAPACITY - ALREADY_BOOKED
    assert outcomes.count("SEATS_UNAVAILABLE") == REQUESTS - (CAPACITY - ALREADY_BOOKED)
