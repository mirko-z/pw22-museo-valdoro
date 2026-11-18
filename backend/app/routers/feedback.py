"""Endpoint del feedback, annidati sotto l'evento a cui si riferiscono."""

from fastapi import APIRouter, status

from app.core.deps import DbSession, StaffUser, VisitorUser
from app.schemas.feedback import FeedbackCreate, FeedbackRead
from app.services.feedback_service import FeedbackService

router = APIRouter(prefix="/api/events/{event_id}/feedback", tags=["feedback"])


@router.post("", response_model=FeedbackRead, status_code=status.HTTP_201_CREATED,
             summary="Lascia un feedback su un evento concluso")
def leave_feedback(event_id: int, body: FeedbackCreate, user: VisitorUser, db: DbSession) -> FeedbackRead:
    feedback = FeedbackService(db).leave(user, event_id, body.rating, body.comment)
    return FeedbackRead(full_name=user.full_name, rating=feedback.rating, comment=feedback.comment,
                        created_at=feedback.created_at)


@router.get("", response_model=list[FeedbackRead], summary="Feedback di un evento (staff)")
def event_feedback(event_id: int, _staff: StaffUser, db: DbSession) -> list[FeedbackRead]:
    return [FeedbackRead(full_name=u.full_name, rating=f.rating, comment=f.comment, created_at=f.created_at)
            for f, u in FeedbackService(db).for_event(event_id)]
