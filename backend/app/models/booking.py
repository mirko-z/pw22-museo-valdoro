"""Modello delle prenotazioni."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, str_enum
from app.models.enums import BookingStatus

if TYPE_CHECKING:
    from app.models.event import Event
    from app.models.user import User


class Booking(Base):
    """Prenotazione di N posti per un evento.

    È un'entità con identificatore proprio, non una semplice associazione
    utente–evento: lo stesso utente può annullare e riprenotare, quindi la
    coppia (user_id, event_id) può ripetersi nello storico.
    """

    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint("seats > 0", name="seats_positive"),
        # Coerenza tra stato e data di annullamento: annullata <=> cancelled_at valorizzata
        CheckConstraint(
            "(status = 'cancelled') = (cancelled_at IS NOT NULL)",
            name="cancelled_at_consistent",
        ),
        # Una sola prenotazione ATTIVA per utente ed evento (RF13): indice univoco
        # PARZIALE, che riguarda solo le righe confermate. Le annullate restano libere.
        Index(
            "uq_bookings_active",
            "user_id",
            "event_id",
            unique=True,
            postgresql_where=text("status = 'confirmed'"),
        ),
        # PostgreSQL non indicizza da solo le chiavi esterne
        Index("ix_bookings_event_id", "event_id"),
        Index("ix_bookings_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # ON DELETE RESTRICT: il DBMS rifiuta di eliminare un utente o un evento
    # che ha prenotazioni, così lo storico non si perde.
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="RESTRICT"))
    seats: Mapped[int]
    status: Mapped[BookingStatus] = mapped_column(
        str_enum(BookingStatus, 10),
        default=BookingStatus.CONFIRMED,
        server_default=BookingStatus.CONFIRMED.value,
    )
    # Codice non sequenziale generato con secrets (services/booking_codes.py)
    code: Mapped[str] = mapped_column(String(12), unique=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    cancelled_at: Mapped[datetime | None]

    user: Mapped[User] = relationship(back_populates="bookings")
    event: Mapped[Event] = relationship(back_populates="bookings")

    def __repr__(self) -> str:
        return f"<Booking code={self.code!r} event_id={self.event_id} seats={self.seats} status={self.status}>"
