"""Schemi di input e output per autenticazione e utenti."""

import re
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from app.core.security import BCRYPT_MAX_BYTES
from app.models import UserRole

# Controllo di forma volutamente semplice (qualcosa@dominio.estensione):
# la verifica vera di un indirizzo è l'invio di un'email, fuori perimetro.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalize_email(value: str) -> str:
    value = value.strip().lower()
    if not _EMAIL_RE.match(value):
        raise ValueError("Indirizzo email non valido.")
    return value


def _check_password_bytes(value: str) -> str:
    # Il limite di bcrypt è in byte, non in caratteri: "€" occupa 3 byte in UTF-8
    if len(value.encode("utf-8")) > BCRYPT_MAX_BYTES:
        raise ValueError(f"La password non può superare {BCRYPT_MAX_BYTES} byte.")
    return value


# Annotated + validatori: tipi riutilizzabili che portano con sé le proprie regole
Email = Annotated[str, StringConstraints(max_length=254), AfterValidator(_normalize_email)]
Password = Annotated[str, StringConstraints(min_length=8), AfterValidator(_check_password_bytes)]


class RegisterRequest(BaseModel):
    """Dati di registrazione: solo quelli necessari (minimizzazione, art. 5 GDPR)."""

    email: Email
    full_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)]
    password: Password


class UserRead(BaseModel):
    """Utente restituito dalle API. L'hash della password non esce mai dal back-end."""

    # from_attributes: lo schema si costruisce leggendo gli attributi di un oggetto ORM
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    role: UserRole
    created_at: datetime


class TokenResponse(BaseModel):
    """Risposta del login nel formato OAuth2, quello che Swagger si aspetta."""

    access_token: str
    token_type: str = "bearer"


class RoleUpdate(BaseModel):
    role: UserRole = Field(description="Nuovo ruolo: visitor, staff o admin")
