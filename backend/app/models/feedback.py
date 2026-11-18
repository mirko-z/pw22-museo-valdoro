"""Modello dei feedback lasciati dopo un evento."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, SmallInteger, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.event import Event
    from app.models.user import User


class Feedback(Base):
    """Voto (1–5) e commento di un utente su un evento concluso.

    La condizione "prenotazione confermata per un evento concluso e non
    annullato" coinvolge più tabelle e l'ora corrente: non si può esprimere
    con un CHECK, quindi la verifica il service (coperta da test).
    """

    __tablename__ = "feedback"
    __table_args__ = (
        CheckConstraint("rating BETWEEN 1 AND 5", name="rating_range"),
        CheckConstraint("char_length(comment) <= 1000", name="comment_length"),
        # Un feedback per utente ed evento. L'indice creato da questo vincolo
        # ha user_id come prima colonna: copre anche le ricerche per utente.
        UniqueConstraint("user_id", "event_id"),
        Index("ix_feedback_event_id", "event_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="RESTRICT"))
    rating: Mapped[int] = mapped_column(SmallInteger)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    user: Mapped[User] = relationship(back_populates="feedback")
    event: Mapped[Event] = relationship(back_populates="feedback")

    def __repr__(self) -> str:
        return f"<Feedback user_id={self.user_id} event_id={self.event_id} rating={self.rating}>"
