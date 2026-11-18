"""Schemi di input e output delle prenotazioni."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.models import BookingStatus, EventStatus, EventType


class BookingCreate(BaseModel):
    event_id: int = Field(gt=0)
    # Il limite per prenotazione dipende dall'evento: lo verifica il service (422)
    seats: int = Field(gt=0, le=1000)


class BookingRead(BaseModel):
    """Prenotazione con i dati essenziali dell'evento, per l'area visitatore."""

    code: str
    seats: int
    status: BookingStatus
    created_at: datetime
    cancelled_at: datetime | None
    event_id: int
    event_title: str
    event_type: EventType
    event_start_at: datetime
    event_end_at: datetime
    event_status: EventStatus
    cancellation_deadline: datetime = Field(description="Ultimo istante utile per annullare")
    can_cancel: bool
    my_rating: int | None = Field(description="Voto già lasciato per l'evento, se presente")
    can_leave_feedback: bool
