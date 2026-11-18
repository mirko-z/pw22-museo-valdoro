"""Modello degli utenti (visitatori, staff, amministratori)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, str_enum
from app.models.enums import UserRole

if TYPE_CHECKING:  # import solo per il type checker, evita import circolari
    from app.models.booking import Booking
    from app.models.feedback import Feedback


class User(Base):
    __tablename__ = "users"

    # Mapped[int] è il tipo Python dell'attributo; mapped_column() descrive
    # la colonna (vincoli, default). Una PK intera diventa "GENERATED ... AS IDENTITY".
    id: Mapped[int] = mapped_column(primary_key=True)
    # 254 caratteri: lunghezza massima pratica di un indirizzo email (RFC 5321)
    email: Mapped[str] = mapped_column(String(254))
    # L'hash bcrypt è sempre lungo 60 caratteri
    password_hash: Mapped[str] = mapped_column(String(60))
    full_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[UserRole] = mapped_column(
        str_enum(UserRole, 10), default=UserRole.VISITOR, server_default=UserRole.VISITOR.value
    )
    # server_default: il valore lo assegna PostgreSQL (now()), non Python
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # Relazioni ORM: user.bookings carica le prenotazioni dell'utente.
    # Non sono colonne: si basano sulle chiavi esterne delle altre tabelle.
    bookings: Mapped[list[Booking]] = relationship(back_populates="user")
    feedback: Mapped[list[Feedback]] = relationship(back_populates="user")

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} role={self.role}>"


# Email univoca senza distinzione tra maiuscole e minuscole: "Mario@Example.com"
# e "mario@example.com" sono lo stesso utente. Serve un indice su espressione,
# perché UNIQUE(email) le considererebbe diverse. È definito dopo la classe
# perché deve riferirsi alla colonna User.email, che prima non esiste ancora.
Index("uq_users_email_lower", func.lower(User.email), unique=True)
