"""Schemi di input e output degli eventi (RF07–RF10, RF16)."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.models import EventStatus, EventType

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=200)]
# AwareDatetime: data con fuso orario obbligatorio (es. "2026-11-05T10:00:00+01:00").
# Un orario "ingenuo" senza fuso sarebbe ambiguo: si rifiuta con 422.
Moment = AwareDatetime


class EventCreate(BaseModel):
    """Dati per creare un evento. Le due regole sono facoltative: se mancano,
    il service usa i default di configurazione (RF09)."""

    title: Title
    description: Annotated[str, StringConstraints(max_length=5000)] | None = None
    type: EventType
    start_at: Moment
    end_at: Moment
    capacity: int = Field(gt=0, le=10_000)
    price: Decimal = Field(default=Decimal("0"), ge=0, max_digits=8, decimal_places=2)
    max_seats_per_booking: int | None = Field(default=None, gt=0)
    cancellation_deadline_hours: int | None = Field(default=None, ge=0, le=720)

    # model_validator: controllo che coinvolge più campi insieme, eseguito
    # dopo la validazione dei singoli campi (mode="after")
    @model_validator(mode="after")
    def check_coherence(self) -> Self:
        if self.end_at <= self.start_at:
            raise ValueError("La fine deve essere successiva all'inizio.")
        if self.max_seats_per_booking is not None and self.max_seats_per_booking > self.capacity:
            raise ValueError("Il massimo di posti per prenotazione non può superare la capienza.")
        return self


class EventUpdate(BaseModel):
    """Modifica parziale (PATCH): si inviano solo i campi da cambiare.

    La coerenza tra campi (fine dopo inizio, massimo posti entro la capienza)
    si verifica nel service sui valori risultanti, perché qui si conoscono
    solo i campi inviati.
    """

    title: Title | None = None
    description: Annotated[str, StringConstraints(max_length=5000)] | None = None
    type: EventType | None = None
    start_at: Moment | None = None
    end_at: Moment | None = None
    capacity: int | None = Field(default=None, gt=0, le=10_000)
    price: Decimal | None = Field(default=None, ge=0, max_digits=8, decimal_places=2)
    max_seats_per_booking: int | None = Field(default=None, gt=0)
    cancellation_deadline_hours: int | None = Field(default=None, ge=0, le=720)


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    type: EventType
    start_at: datetime
    end_at: datetime
    capacity: int
    price: Decimal
    status: EventStatus
    max_seats_per_booking: int
    cancellation_deadline_hours: int
    # Campi calcolati, non memorizzati
    available_seats: int = Field(description="Capienza meno posti confermati")
    is_ended: bool = Field(description="Vero se l'evento è già concluso (end_at nel passato)")


class Participant(BaseModel):
    """Riga dell'elenco partecipanti visto dallo staff (RF16)."""

    code: str
    full_name: str
    email: str
    seats: int
    created_at: datetime
