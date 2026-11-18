"""Logica di business delle prenotazioni lato visitatore (RF11–RF15)."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import DomainError, NotFound
from app.models import Booking, BookingStatus, Event, EventStatus, Feedback, User
from app.services.booking_strategies import BookingStrategy, LockingBookingStrategy


@dataclass(frozen=True)
class BookingWithEvent:
    booking: Booking
    event: Event
    my_rating: int | None = None  # voto già lasciato dall'utente per l'evento, se c'è

    def cancellation_deadline(self) -> datetime:
        return self.event.start_at - timedelta(hours=self.event.cancellation_deadline_hours)

    def can_cancel(self, now: datetime) -> bool:
        return self.booking.status is BookingStatus.CONFIRMED and now < self.cancellation_deadline()

    def can_leave_feedback(self, now: datetime) -> bool:
        """Stesse condizioni verificate da FeedbackService (RF17), per guidare l'interfaccia."""
        return (self.booking.status is BookingStatus.CONFIRMED and self.event.status is EventStatus.SCHEDULED
                and self.event.end_at < now and self.my_rating is None)


class BookingService:
    """Il service delega la prenotazione a una strategia (di default quella con lock).

    La strategia è un parametro del costruttore (dependency injection):
    l'applicazione usa sempre ``LockingBookingStrategy``; test ed esperimento
    possono passare ``NaiveBookingStrategy`` senza modificare il service.
    """

    def __init__(self, db: Session, strategy: BookingStrategy | None = None) -> None:
        self.db = db
        self.strategy = strategy or LockingBookingStrategy()

    def book(self, user: User, event_id: int, seats: int) -> BookingWithEvent:
        booking = self.strategy.reserve(self.db, user, event_id, seats)
        return BookingWithEvent(booking, self.db.get_one(Event, booking.event_id))

    def list_mine(self, user: User) -> list[BookingWithEvent]:
        rows = self.db.execute(
            select(Booking, Event, Feedback.rating).join(Event, Event.id == Booking.event_id)
            .outerjoin(Feedback, (Feedback.event_id == Booking.event_id) & (Feedback.user_id == Booking.user_id))
            .where(Booking.user_id == user.id)
            .order_by(Event.start_at.desc(), Booking.created_at.desc())
        ).all()
        return [BookingWithEvent(b, e, rating) for b, e, rating in rows]

    def cancel(self, user: User, code: str) -> BookingWithEvent:
        """Annulla la propria prenotazione entro il termine dell'evento (RF14).

        La prenotazione di un altro utente risponde 404 come una inesistente:
        un 403 rivelerebbe che il codice esiste (OWASP A01 – Broken Access Control).
        La riga è bloccata per evitare due annullamenti concorrenti della stessa prenotazione.
        """
        row = self.db.execute(
            select(Booking, Event).join(Event, Event.id == Booking.event_id)
            .where(Booking.code == code.upper(), Booking.user_id == user.id)
            .with_for_update(of=Booking)
        ).first()
        if row is None:
            self.db.rollback()
            raise NotFound("Prenotazione non trovata.")
        item = BookingWithEvent(*row)
        now = datetime.now(UTC)
        if item.booking.status is BookingStatus.CANCELLED:
            self.db.rollback()
            raise DomainError("ALREADY_CANCELLED", "La prenotazione è già annullata.")
        if not item.can_cancel(now):
            self.db.rollback()
            raise DomainError("DEADLINE_PASSED",
                              f"Il termine di annullamento ({item.event.cancellation_deadline_hours} ore "
                              "prima dell'inizio) è scaduto.")
        item.booking.status = BookingStatus.CANCELLED
        item.booking.cancelled_at = now
        self.db.commit()
        return item
