"""Endpoint delle prenotazioni, riservati al ruolo visitor."""

from datetime import UTC, datetime

from fastapi import APIRouter, status

from app.core.deps import DbSession, VisitorUser
from app.schemas.booking import BookingCreate, BookingRead
from app.services.booking_service import BookingService, BookingWithEvent

router = APIRouter(prefix="/api/bookings", tags=["prenotazioni"])


def to_read(item: BookingWithEvent) -> BookingRead:
    b, e = item.booking, item.event
    now = datetime.now(UTC)
    return BookingRead(
        code=b.code, seats=b.seats, status=b.status, created_at=b.created_at, cancelled_at=b.cancelled_at,
        event_id=e.id, event_title=e.title, event_type=e.type, event_start_at=e.start_at, event_end_at=e.end_at,
        event_status=e.status, cancellation_deadline=item.cancellation_deadline(),
        can_cancel=item.can_cancel(now), my_rating=item.my_rating,
        can_leave_feedback=item.can_leave_feedback(now),
    )


@router.post("", response_model=BookingRead, status_code=status.HTTP_201_CREATED,
             summary="Prenota posti per un evento (controllo dei posti sicuro in concorrenza)")
def create_booking(body: BookingCreate, user: VisitorUser, db: DbSession) -> BookingRead:
    return to_read(BookingService(db).book(user, body.event_id, body.seats))


@router.get("/me", response_model=list[BookingRead], summary="Le mie prenotazioni")
def my_bookings(user: VisitorUser, db: DbSession) -> list[BookingRead]:
    return [to_read(item) for item in BookingService(db).list_mine(user)]


@router.post("/{code}/cancel", response_model=BookingRead, summary="Annulla una mia prenotazione")
def cancel_booking(code: str, user: VisitorUser, db: DbSession) -> BookingRead:
    return to_read(BookingService(db).cancel(user, code))
