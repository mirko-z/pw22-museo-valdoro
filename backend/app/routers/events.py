"""Endpoint degli eventi: consultazione pubblica e gestione da parte dello staff."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.config import Settings, get_settings
from app.core.deps import DbSession, StaffUser
from app.models import EventType
from app.schemas.event import EventCreate, EventRead, EventUpdate, Participant
from app.services.event_service import EventService, EventWithSeats

router = APIRouter(prefix="/api/events", tags=["eventi"])


def get_service(db: DbSession, settings: Annotated[Settings, Depends(get_settings)]) -> EventService:
    """Dipendenza: il router riceve il service già costruito con sessione e configurazione."""
    return EventService(db, settings)


Service = Annotated[EventService, Depends(get_service)]


# Campi di EventRead che corrispondono a colonne del modello Event
_COLUMNS = [name for name in EventRead.model_fields if name not in ("available_seats", "is_ended")]


def to_read(item: EventWithSeats) -> EventRead:
    """Colonne dell'evento + campi calcolati dal service."""
    columns = {name: getattr(item.event, name) for name in _COLUMNS}
    return EventRead(**columns, available_seats=item.available_seats, is_ended=item.is_ended)


# --- pubblico ------------------------------------------------------------------


@router.get("", response_model=list[EventRead], summary="Eventi in programma (pubblico)")
def list_events(service: Service,
                type: Annotated[EventType | None, Query(description="Filtra per tipo")] = None) -> list[EventRead]:
    return [to_read(item) for item in service.list_upcoming(type)]


@router.get("/{event_id}", response_model=EventRead, summary="Dettaglio di un evento (pubblico)")
def get_event(event_id: int, service: Service) -> EventRead:
    return to_read(service.get(event_id))


# --- staff ---------------------------------------------------------------------


@router.post("", response_model=EventRead, status_code=status.HTTP_201_CREATED, summary="Crea un evento")
def create_event(body: EventCreate, _staff: StaffUser, service: Service) -> EventRead:
    return to_read(service.create(body))


@router.patch("/{event_id}", response_model=EventRead, summary="Modifica un evento")
def update_event(event_id: int, body: EventUpdate, _staff: StaffUser, service: Service) -> EventRead:
    return to_read(service.update(event_id, body))


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Elimina un evento senza prenotazioni")
def delete_event(event_id: int, _staff: StaffUser, service: Service) -> None:
    service.delete(event_id)


@router.post("/{event_id}/cancel", response_model=EventRead,
             summary="Annulla un evento e le sue prenotazioni confermate")
def cancel_event(event_id: int, _staff: StaffUser, service: Service) -> EventRead:
    return to_read(service.cancel(event_id))


@router.get("/{event_id}/participants", response_model=list[Participant],
            summary="Partecipanti di un evento")
def participants(event_id: int, _staff: StaffUser, service: Service) -> list[Participant]:
    return [
        Participant(code=b.code, full_name=u.full_name, email=u.email, seats=b.seats, created_at=b.created_at)
        for b, u in service.participants(event_id)
    ]
