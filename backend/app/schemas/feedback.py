"""Schemi del feedback (RF17, RF18)."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints


class FeedbackCreate(BaseModel):
    rating: int = Field(ge=1, le=5, description="Voto da 1 a 5")
    comment: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] | None = None


class FeedbackRead(BaseModel):
    """Feedback visto dallo staff: nome del visitatore, non l'email (minimizzazione)."""

    full_name: str
    rating: int
    comment: str | None
    created_at: datetime
