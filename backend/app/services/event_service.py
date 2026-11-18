"""Logica di business degli eventi (RF07–RF10, RF16)."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Select, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import DomainError, NotFound
from app.models import Booking, BookingStatus, Event, EventStatus, EventType, User
from app.schemas.event import EventCreate, EventUpdate

UNPROCESSABLE = 422


def confirmed_seats_subquery():  # type: ignore[no-untyped-def]
    """Sottoquery: posti confermati per evento (event_id, seats).

    I posti disponibili non sono memorizzati: si calcolano sempre come
    capienza − somma dei posti confermati, così non esiste un contatore
    ridondante da tenere allineato.
    """
    return (
        select(Booking.event_id, func.sum(Booking.seats).label("seats"))
        .where(Booking.status == BookingStatus.CONFIRMED)
        .group_by(Booking.event_id)
        .subquery()
    )


@dataclass(frozen=True)
class EventWithSeats:
    """Evento con i dati calcolati che le API restituiscono insieme alle colonne."""

    event: Event
    available_seats: int
    is_ended: bool


class EventService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    # --- lettura -------------------------------------------------------------

    def _with_seats(self) -> Select[tuple[Event, int]]:
        """Eventi con i posti disponibili in una sola query (LEFT JOIN sulla
        sottoquery aggregata), invece di una query per evento (problema N+1)."""
        booked = confirmed_seats_subquery()
        available = (Event.capacity - func.coalesce(booked.c.seats, 0)).label("available")
        return select(Event, available).outerjoin(booked, booked.c.event_id == Event.id)

    def list_upcoming(self, event_type: EventType | None = None) -> list[EventWithSeats]:
        """Eventi programmati non ancora iniziati, compresi gli esauriti (RF07)."""
        now = datetime.now(UTC)
        query = self._with_seats().where(Event.status == EventStatus.SCHEDULED, Event.start_at > now)
        if event_type is not None:
            query = query.where(Event.type == event_type)
        rows = self.db.execute(query.order_by(Event.start_at)).all()
        return [EventWithSeats(e, available, e.end_at < now) for e, available in rows]

    def get(self, event_id: int) -> EventWithSeats:
        row = self.db.execute(self._with_seats().where(Event.id == event_id)).first()
        if row is None:
            raise NotFound("Evento non trovato.")
        event, available = row
        return EventWithSeats(event, available, event.end_at < datetime.now(UTC))

    def participants(self, event_id: int) -> Sequence[tuple[Booking, User]]:
        """Prenotazioni confermate con i dati del visitatore (RF16)."""
        self._get_or_404(event_id)
        query = (
            select(Booking, User)
            .join(User, User.id == Booking.user_id)
            .where(Booking.event_id == event_id, Booking.status == BookingStatus.CONFIRMED)
            .order_by(Booking.created_at)
        )
        return self.db.execute(query).all()

    # --- scrittura -----------------------------------------------------------

    def create(self, data: EventCreate) -> EventWithSeats:
        """Crea l'evento; le regole non indicate prendono i default di Settings (RF09).

        Il default del massimo posti è limitato alla capienza: un evento da 4 posti
        con default 6 avrebbe altrimenti una regola incoerente (e il CHECK la rifiuterebbe).
        """
        if data.start_at <= datetime.now(UTC):
            raise DomainError("INVALID_EVENT", "L'evento deve iniziare nel futuro.", UNPROCESSABLE)
        max_seats = data.max_seats_per_booking or min(self.settings.default_max_seats_per_booking,
                                                      data.capacity)
        deadline = data.cancellation_deadline_hours
        if deadline is None:
            deadline = self.settings.default_cancellation_deadline_hours
        # model_dump(exclude=...) produce un dizionario con i campi del form,
        # che diventano gli argomenti del costruttore del modello ORM (**).
        event = Event(**data.model_dump(exclude={"max_seats_per_booking", "cancellation_deadline_hours"}),
                      max_seats_per_booking=max_seats, cancellation_deadline_hours=deadline)
        self.db.add(event)
        self.db.commit()
        return EventWithSeats(event, event.capacity, False)

    def update(self, event_id: int, data: EventUpdate) -> EventWithSeats:
        """Modifica parziale. La riga dell'evento è bloccata (FOR UPDATE) durante
        il controllo della capienza: una prenotazione concorrente non può inserirsi
        tra la somma dei posti e la riduzione della capienza."""
        event = self._get_for_update(event_id)
        if event.status is EventStatus.CANCELLED:
            raise DomainError("EVENT_CANCELLED", "Un evento annullato non si può modificare.")

        # exclude_unset: solo i campi effettivamente inviati dal client.
        # Un null esplicito vale solo per la descrizione (facoltativa); per gli
        # altri campi, obbligatori, viene ignorato.
        for field, value in data.model_dump(exclude_unset=True).items():
            if value is None and field != "description":
                continue
            setattr(event, field, value)

        if event.end_at <= event.start_at:
            raise self._rollback(DomainError("INVALID_EVENT", "La fine deve essere successiva all'inizio.",
                                             UNPROCESSABLE))
        if event.max_seats_per_booking > event.capacity:
            raise self._rollback(DomainError(
                "INVALID_EVENT", "Il massimo di posti per prenotazione non può superare la capienza.",
                UNPROCESSABLE))
        booked = self._confirmed_seats(event_id)
        if event.capacity < booked:
            raise self._rollback(DomainError(
                "CAPACITY_BELOW_BOOKED",
                f"La capienza non può scendere sotto i {booked} posti già confermati."))
        self.db.commit()
        return EventWithSeats(event, event.capacity - booked, event.end_at < datetime.now(UTC))

    def cancel(self, event_id: int) -> EventWithSeats:
        """Annulla l'evento e, nella stessa transazione, le sue prenotazioni
        confermate (RF10): o cambiano entrambi, o nessuno dei due."""
        event = self._get_for_update(event_id)
        if event.status is EventStatus.CANCELLED:
            raise self._rollback(DomainError("EVENT_CANCELLED", "L'evento è già annullato."))
        now = datetime.now(UTC)
        event.status = EventStatus.CANCELLED
        # Un solo UPDATE su tutte le prenotazioni confermate dell'evento
        self.db.execute(
            update(Booking)
            .where(Booking.event_id == event_id, Booking.status == BookingStatus.CONFIRMED)
            .values(status=BookingStatus.CANCELLED, cancelled_at=now)
        )
        self.db.commit()
        return EventWithSeats(event, event.capacity, event.end_at < now)

    def delete(self, event_id: int) -> None:
        """Elimina solo un evento senza prenotazioni: lo garantisce il database
        con ON DELETE RESTRICT; qui si traduce l'errore in un 409 comprensibile."""
        event = self._get_or_404(event_id)
        self.db.delete(event)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise DomainError("EVENT_HAS_BOOKINGS",
                              "L'evento ha prenotazioni: si può solo annullare.") from exc

    # --- supporto ------------------------------------------------------------

    def _get_or_404(self, event_id: int) -> Event:
        event = self.db.get(Event, event_id)
        if event is None:
            raise NotFound("Evento non trovato.")
        return event

    def _get_for_update(self, event_id: int) -> Event:
        """SELECT ... FOR UPDATE: lock esclusivo sulla riga fino al commit/rollback."""
        event = self.db.scalar(select(Event).where(Event.id == event_id).with_for_update())
        if event is None:
            raise NotFound("Evento non trovato.")
        return event

    def _confirmed_seats(self, event_id: int) -> int:
        return self.db.scalar(
            select(func.coalesce(func.sum(Booking.seats), 0))
            .where(Booking.event_id == event_id, Booking.status == BookingStatus.CONFIRMED)
        ) or 0

    def _rollback(self, error: DomainError) -> DomainError:
        """Annulla la transazione (e rilascia il lock) prima di segnalare l'errore."""
        self.db.rollback()
        return error
