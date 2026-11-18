"""Valori ammessi per le colonne con dominio chiuso.

``StrEnum`` è un'enumerazione i cui membri sono anche stringhe:
``UserRole.STAFF == "staff"`` è vero, quindi si serializzano in JSON
senza conversioni. È l'equivalente tipizzato di un gruppo di costanti PHP
(``const ROLE_STAFF = 'staff'``), ma il type checker segnala i valori non previsti.
"""

from enum import StrEnum


class UserRole(StrEnum):
    VISITOR = "visitor"
    STAFF = "staff"
    ADMIN = "admin"


class EventType(StrEnum):
    GUIDED_TOUR = "guided_tour"
    WORKSHOP = "workshop"
    CONFERENCE = "conference"


class EventStatus(StrEnum):
    # "Svolto" non è uno stato memorizzato: si ricava da end_at < now()
    SCHEDULED = "scheduled"
    CANCELLED = "cancelled"


class BookingStatus(StrEnum):
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
