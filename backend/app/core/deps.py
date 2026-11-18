"""Dipendenze FastAPI per autenticazione e autorizzazione.
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import Cookie, Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import Forbidden, NotAuthenticated
from app.core.security import decode_access_token
from app.models import User, UserRole

ACCESS_TOKEN_COOKIE = "access_token"

# Legge l'header "Authorization: Bearer <token>". tokenUrl indica a Swagger
# dove ottenere il token (pulsante "Authorize"). auto_error=False: se l'header
# manca non risponde subito 401, perché il token può arrivare dal cookie.
bearer_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    db: DbSession,
    bearer_token: Annotated[str | None, Depends(bearer_scheme)],
    cookie_token: Annotated[str | None, Cookie(alias=ACCESS_TOKEN_COOKIE)] = None,
) -> User:
    """Utente autenticato, ricavato dal JWT nell'header Bearer o nel cookie HttpOnly.

    Il browser usa il cookie (il JS della pagina non può leggerlo);
    Swagger e i test usano l'header. L'utente viene riletto dal database:
    se nel frattempo è stato eliminato, il token non vale più.
    """
    token = bearer_token or cookie_token
    if not token:
        raise NotAuthenticated()
    user_id = decode_access_token(token)
    if user_id is None:
        raise NotAuthenticated("Sessione scaduta o non valida: accedi di nuovo.")
    user = db.get(User, user_id)
    if user is None:
        raise NotAuthenticated("Sessione scaduta o non valida: accedi di nuovo.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: UserRole) -> Callable[[User], User]:
    """Crea una dipendenza che ammette solo i ruoli indicati (altrimenti 403).
    È una funzione che restituisce una funzione (una "factory"): così si scrive ``Depends(require_roles(UserRole.ADMIN))`` invece di ripetere
    lo stesso controllo in ogni endpoint.
    """

    def checker(user: CurrentUser) -> User:
        if user.role not in roles:
            raise Forbidden()
        return user

    return checker


# Alias pronti per gli endpoint. L'admin è uno staff con in più la gestione utenti.
VisitorUser = Annotated[User, Depends(require_roles(UserRole.VISITOR))]
StaffUser = Annotated[User, Depends(require_roles(UserRole.STAFF, UserRole.ADMIN))]
AdminUser = Annotated[User, Depends(require_roles(UserRole.ADMIN))]
