"""Strategie di prenotazione (pattern Strategy) – RF11–RF13, RNF01.

Le due strategie eseguono la stessa sequenza "leggi l'evento → controlla
le regole e i posti → inserisci la prenotazione" e differiscono in un solo
punto: come leggono la riga dell'evento.

- ``LockingBookingStrategy`` (usata dall'applicazione): ``SELECT ... FOR UPDATE``.
  La lettura acquisisce un lock esclusivo sulla riga; le altre transazioni che
  prenotano lo stesso evento attendono il COMMIT o il ROLLBACK. La sequenza
  controllo–inserimento diventa una **sezione critica** eseguita da una
  transazione alla volta per evento.
- ``NaiveBookingStrategy`` (solo test ed esperimento): ``SELECT`` semplice.
  Più transazioni possono leggere gli stessi posti disponibili prima che una
  scriva: è la **race condition** che produce overbooking.

Per chi viene da PHP: è il pattern Strategy "classico" (un'interfaccia, più
implementazioni intercambiabili). Qui la classe base astratta implementa
l'algoritmo comune e lascia alle sottoclassi il solo passo che cambia
(variante "template method").
"""

import time
from abc import ABC, abstractmethod
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import DomainError, NotFound
from app.models import Booking, BookingStatus, Event, EventStatus, User
from app.services.booking_codes import generate_booking_code

UNPROCESSABLE = 422
MAX_CODE_ATTEMPTS = 3


class BookingStrategy(ABC):
    """Interfaccia comune: ``reserve()`` prenota ``seats`` posti o solleva un errore di dominio.

    ``critical_section_delay`` (secondi) allarga artificialmente la finestra
    tra il controllo dei posti e l'inserimento. Vale 0 nell'applicazione; il
    test di concorrenza lo usa per rendere la race condition riproducibile
    anche su una macchina veloce (con il lock il ritardo rallenta, ma non rompe).
    """

    name: str = "base"

    def __init__(self, critical_section_delay: float = 0.0) -> None:
        self.critical_section_delay = critical_section_delay

    @abstractmethod
    def _load_event(self, db: Session, event_id: int) -> Event | None:
        """Unico passo che cambia tra le strategie: come si legge la riga dell'evento."""

    def reserve(self, db: Session, user: User, event_id: int, seats: int) -> Booking:
        """Esegue la prenotazione in una transazione (BEGIN implicito alla prima query)."""
        try:
            event = self._load_event(db, event_id)
            now = datetime.now(UTC)
            self._check_rules(db, user, event, seats, now)
            assert event is not None  # garantito da _check_rules

            if self.critical_section_delay:
                time.sleep(self.critical_section_delay)

            booking = self._insert(db, user, event, seats)
        except Exception:
            # Qualsiasi errore annulla la transazione e rilascia l'eventuale lock
            db.rollback()
            raise
        return booking

    # --- passi comuni ------------------------------------------------------------

    def _check_rules(self, db: Session, user: User, event: Event | None, seats: int, now: datetime) -> None:
        """Regole dello scenario UC04 (caso d'uso "Prenotare un evento"), nello stesso ordine."""
        if event is None:
            raise NotFound("Evento non trovato.")
        if event.status is not EventStatus.SCHEDULED or event.start_at <= now:
            raise DomainError("EVENT_NOT_BOOKABLE", "L'evento non è prenotabile (annullato o già iniziato).")
        if seats > event.max_seats_per_booking:
            raise DomainError("MAX_SEATS_EXCEEDED",
                              f"Si possono prenotare al massimo {event.max_seats_per_booking} posti.",
                              UNPROCESSABLE)
        if self._has_active_booking(db, user.id, event.id):
            raise DomainError("ALREADY_BOOKED",
                              "Hai già una prenotazione per questo evento: annullala per cambiarla.")
        available = event.capacity - self._confirmed_seats(db, event.id)
        if seats > available:
            raise DomainError("SEATS_UNAVAILABLE", f"Posti insufficienti: ne restano {max(available, 0)}.")

    def _insert(self, db: Session, user: User, event: Event, seats: int) -> Booking:
        """Inserisce e conferma. Un codice duplicato (evento rarissimo) viene rigenerato;
        una seconda prenotazione attiva dello stesso utente è bloccata dall'indice parziale."""
        for _attempt in range(MAX_CODE_ATTEMPTS):
            booking = Booking(user_id=user.id, event_id=event.id, seats=seats,
                              status=BookingStatus.CONFIRMED, code=generate_booking_code())
            # SAVEPOINT: in caso di codice duplicato si annulla solo l'INSERT,
            # non la transazione (e quindi non il lock sull'evento)
            savepoint = db.begin_nested()
            db.add(booking)
            try:
                savepoint.commit()
            except IntegrityError as exc:
                constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
                if constraint == "uq_bookings_code":
                    continue
                if constraint == "uq_bookings_active":
                    raise DomainError("ALREADY_BOOKED",
                                      "Hai già una prenotazione per questo evento.") from exc
                raise
            db.commit()  # fine della sezione critica: il lock viene rilasciato qui
            return booking
        raise RuntimeError("Impossibile generare un codice di prenotazione univoco.")

    @staticmethod
    def _has_active_booking(db: Session, user_id: int, event_id: int) -> bool:
        return db.scalar(select(func.count()).select_from(Booking).where(
            Booking.user_id == user_id, Booking.event_id == event_id,
            Booking.status == BookingStatus.CONFIRMED)) > 0

    @staticmethod
    def _confirmed_seats(db: Session, event_id: int) -> int:
        return db.scalar(select(func.coalesce(func.sum(Booking.seats), 0)).where(
            Booking.event_id == event_id, Booking.status == BookingStatus.CONFIRMED)) or 0


class LockingBookingStrategy(BookingStrategy):
    """Lock pessimistico sulla riga dell'evento (``SELECT ... FOR UPDATE``)."""

    name = "locking"

    def _load_event(self, db: Session, event_id: int) -> Event | None:
        return db.scalar(select(Event).where(Event.id == event_id).with_for_update())


class NaiveBookingStrategy(BookingStrategy):
    """Leggi–controlla–scrivi senza lock. **Solo per test ed esperimento.**"""

    name = "naive"

    def _load_event(self, db: Session, event_id: int) -> Event | None:
        return db.scalar(select(Event).where(Event.id == event_id))
