"""Logica di business del feedback (RF17, RF18, obiettivo O5).

La condizione di ammissibilità coinvolge più tabelle e l'ora corrente, quindi
non si esprime con un CHECK: la verifica questo service, nell'ordine
evento → stato → conclusione → prenotazione → unicità.
"""

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import DomainError, NotFound
from app.models import Booking, BookingStatus, Event, EventStatus, Feedback, User


class FeedbackService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def leave(self, user: User, event_id: int, rating: int, comment: str | None) -> Feedback:
        event = self.db.get(Event, event_id)
        if event is None:
            raise NotFound("Evento non trovato.")
        if event.status is EventStatus.CANCELLED:
            raise DomainError("EVENT_CANCELLED", "L'evento è stato annullato.")
        if event.end_at > datetime.now(UTC):
            raise DomainError("EVENT_NOT_ENDED", "Il feedback si può lasciare solo dopo la fine dell'evento.")
        has_booking = self.db.scalar(select(func.count()).select_from(Booking).where(
            Booking.user_id == user.id, Booking.event_id == event_id,
            Booking.status == BookingStatus.CONFIRMED)) > 0
        if not has_booking:
            raise DomainError("NO_CONFIRMED_BOOKING",
                              "Serve una prenotazione confermata per questo evento.", 403)

        feedback = Feedback(user_id=user.id, event_id=event_id, rating=rating, comment=comment or None)
        self.db.add(feedback)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            # Unicità garantita da UNIQUE(user_id, event_id), anche con due invii simultanei
            raise DomainError("FEEDBACK_EXISTS", "Hai già lasciato un feedback per questo evento.") from exc
        return feedback

    def for_event(self, event_id: int) -> Sequence[tuple[Feedback, User]]:
        if self.db.get(Event, event_id) is None:
            raise NotFound("Evento non trovato.")
        return self.db.execute(
            select(Feedback, User).join(User, User.id == Feedback.user_id)
            .where(Feedback.event_id == event_id).order_by(Feedback.created_at.desc())
        ).all()
