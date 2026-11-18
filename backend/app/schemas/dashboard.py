"""Schemi della dashboard. I tassi sono frazioni tra 0 e 1 (il front-end li mostra in %);
``None`` significa "non calcolabile" (denominatore zero)."""

from datetime import date, datetime

from pydantic import BaseModel

from app.models import EventStatus, EventType


class Overview(BaseModel):
    events_upcoming: int
    events_concluded: int
    bookings_total: int
    bookings_cancelled: int
    cancellation_rate: float | None  # K5
    average_fill_rate: float | None  # K6 medio sugli eventi conclusi
    feedback_count: int
    average_rating: float | None  # K8
    feedback_coverage: float | None  # K7


class EventIndicators(BaseModel):
    event_id: int
    title: str
    type: EventType
    start_at: datetime
    status: EventStatus
    is_ended: bool
    capacity: int
    bookings_total: int
    bookings_cancelled: int
    confirmed_seats: int
    fill_rate: float | None
    cancellation_rate: float | None
    feedback_count: int
    average_rating: float | None
    feedback_coverage: float | None


class TypeIndicators(BaseModel):
    type: EventType
    events_concluded: int
    average_fill_rate: float | None
    feedback_count: int
    average_rating: float | None


class WeeklyBookings(BaseModel):
    week_start: date
    bookings: int
    seats: int
