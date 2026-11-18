"""Modello degli eventi (visite guidate, laboratori, conferenze)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Index, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, str_enum
from app.models.enums import EventStatus, EventType

if TYPE_CHECKING:
    from app.models.booking import Booking
    from app.models.feedback import Feedback


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        # I nomi brevi diventano "ck_events_<nome>" grazie alla convenzione in base.py
        CheckConstraint("end_at > start_at", name="end_after_start"),
        CheckConstraint("capacity > 0", name="capacity_positive"),
        CheckConstraint("price >= 0", name="price_non_negative"),
        CheckConstraint(
            "max_seats_per_booking > 0 AND max_seats_per_booking <= capacity",
            name="max_seats_valid",
        ),
        CheckConstraint("cancellation_deadline_hours >= 0", name="deadline_non_negative"),
        # Elenco degli eventi futuri ordinati per data
        Index("ix_events_start_at", "start_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    # "str | None" rende la colonna NULL-abile; senza None è NOT NULL
    description: Mapped[str | None] = mapped_column(Text)
    type: Mapped[EventType] = mapped_column(str_enum(EventType, 20))
    start_at: Mapped[datetime]
    end_at: Mapped[datetime]
    capacity: Mapped[int]
    # Decimal e non float: gli importi non devono avere errori di arrotondamento
    price: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=Decimal("0"), server_default="0")
    status: Mapped[EventStatus] = mapped_column(
        str_enum(EventStatus, 10),
        default=EventStatus.SCHEDULED,
        server_default=EventStatus.SCHEDULED.value,
    )
    # Regole di prenotazione: NOT NULL, valorizzate dal service con i default
    # di Settings se lo staff non le indica (ogni evento conserva le sue regole).
    max_seats_per_booking: Mapped[int]
    cancellation_deadline_hours: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    bookings: Mapped[list[Booking]] = relationship(back_populates="event")
    feedback: Mapped[list[Feedback]] = relationship(back_populates="event")

    def __repr__(self) -> str:
        return f"<Event id={self.id} title={self.title!r} start_at={self.start_at}>"
