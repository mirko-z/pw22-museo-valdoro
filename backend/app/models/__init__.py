"""Modelli ORM.

Importarli tutti qui serve ad Alembic e ai test: ``Base.metadata`` conosce
una tabella solo dopo che la classe corrispondente è stata importata.
"""

from app.models.base import Base
from app.models.booking import Booking
from app.models.enums import BookingStatus, EventStatus, EventType, UserRole
from app.models.event import Event
from app.models.feedback import Feedback
from app.models.user import User

__all__ = [
    "Base",
    "Booking",
    "BookingStatus",
    "Event",
    "EventStatus",
    "EventType",
    "Feedback",
    "User",
    "UserRole",
]
