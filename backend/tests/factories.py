"""Funzioni di supporto per creare dati validi nei test.

Ogni funzione accetta gli attributi da modificare (``**overrides``): un test
indica solo ciò che gli interessa, il resto ha valori validi di default.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from itertools import count
from typing import Any

from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models import Booking, Event, EventType, User, UserRole
from app.services.booking_codes import generate_booking_code

_seq = count(1)

# Hash bcrypt fittizio ma di forma valida (60 caratteri): calcolarne uno vero
# costa ~0,2 s e qui non serve, perché nessun test di schema fa login.
FAKE_HASH = "$2b$12$" + "a" * 53


def make_user(session: Session, **overrides: Any) -> User:
    n = next(_seq)
    data: dict[str, Any] = {
        "email": f"utente{n}@example.com",
        "full_name": f"Utente {n}",
        "password_hash": FAKE_HASH,
        "role": UserRole.VISITOR,
    }
    data.update(overrides)
    user = User(**data)
    session.add(user)
    session.flush()
    return user


def make_event(session: Session, **overrides: Any) -> Event:
    start = datetime.now(UTC) + timedelta(days=7)
    data: dict[str, Any] = {
        "title": "Visita guidata di prova",
        "type": EventType.GUIDED_TOUR,
        "start_at": start,
        "end_at": start + timedelta(hours=1, minutes=30),
        "capacity": 20,
        "price": Decimal("8.00"),
        "max_seats_per_booking": 6,
        "cancellation_deadline_hours": 24,
    }
    data.update(overrides)
    # Default coerente con il CHECK max_seats_per_booking <= capacity
    if "max_seats_per_booking" not in overrides:
        data["max_seats_per_booking"] = min(6, data["capacity"])
    event = Event(**data)
    session.add(event)
    session.flush()
    return event


def make_booking(session: Session, user: User, event: Event, **overrides: Any) -> Booking:
    data: dict[str, Any] = {"user": user, "event": event, "seats": 2, "code": generate_booking_code()}
    data.update(overrides)
    booking = Booking(**data)
    session.add(booking)
    session.flush()
    return booking


def auth_header(user: User) -> dict[str, str]:
    """Intestazione Authorization con un JWT valido per l'utente (come fa Swagger)."""
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role.value)}"}

