"""Endpoint della dashboard, riservati a staff e admin."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.core.deps import DbSession, StaffUser
from app.schemas.dashboard import EventIndicators, Overview, TypeIndicators, WeeklyBookings
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/overview", response_model=Overview, summary="Indicatori complessivi")
def overview(_staff: StaffUser, db: DbSession) -> Overview:
    return Overview(**DashboardService(db).overview())  # type: ignore[arg-type]


@router.get("/events", response_model=list[EventIndicators], summary="Indicatori per evento")
def events(_staff: StaffUser, db: DbSession) -> list[EventIndicators]:
    return [
        EventIndicators(
            event_id=s.event_id, title=s.title, type=s.type, start_at=s.start_at, status=s.status,
            is_ended=s.is_ended, capacity=s.capacity, bookings_total=s.bookings_total,
            bookings_cancelled=s.bookings_cancelled, confirmed_seats=s.confirmed_seats,
            fill_rate=s.fill_rate, cancellation_rate=s.cancellation_rate, feedback_count=s.feedback_count,
            average_rating=s.average_rating, feedback_coverage=s.feedback_coverage,
        )
        for s in DashboardService(db).event_stats()
    ]


@router.get("/types", response_model=list[TypeIndicators], summary="Indicatori per tipo di evento")
def types(_staff: StaffUser, db: DbSession) -> list[TypeIndicators]:
    return [TypeIndicators(**row) for row in DashboardService(db).by_type()]  # type: ignore[arg-type]


@router.get("/weekly", response_model=list[WeeklyBookings], summary="Prenotazioni per settimana")
def weekly(_staff: StaffUser, db: DbSession,
           weeks: Annotated[int, Query(ge=1, le=52, description="Numero di settimane")] = 12) -> list[WeeklyBookings]:
    return [WeeklyBookings(**row) for row in DashboardService(db).weekly(weeks)]  # type: ignore[arg-type]
