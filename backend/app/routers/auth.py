"""Endpoint di autenticazione: registrazione, login, logout, utente corrente."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from fastapi.security import OAuth2PasswordRequestForm

from app.core.config import get_settings
from app.core.deps import ACCESS_TOKEN_COOKIE, CurrentUser, DbSession
from app.core.errors import NotAuthenticated
from app.core.security import create_access_token
from app.schemas.user import RegisterRequest, TokenResponse, UserRead
from app.services.user_service import UserService

router = APIRouter(prefix="/api/auth", tags=["autenticazione"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED,
             summary="Registra un nuovo visitatore")
def register(body: RegisterRequest, db: DbSession) -> UserRead:
    user = UserService(db).register(body.email, body.full_name, body.password)
    return UserRead.model_validate(user)


@router.post("/login", response_model=TokenResponse, summary="Accede e imposta il cookie del token")
def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    response: Response,
    db: DbSession,
) -> TokenResponse:
    """Form ``username`` (l'email) e ``password``, formato OAuth2 usato da Swagger.

    Il token viene restituito nel corpo (per Swagger e i test) e impostato
    in un cookie:
    - ``HttpOnly``: il JavaScript della pagina non può leggerlo, quindi un
      eventuale XSS non può rubarlo;
    - ``SameSite=Strict``: il browser non lo invia con richieste partite da
      altri siti (mitigazione del CSRF);
    - ``Secure`` in produzione: viaggia solo su HTTPS;
    - ``Path=/api``: inviato solo alle chiamate API, non ai file statici.
    """
    user = UserService(db).authenticate(form.username, form.password)
    if user is None:
        raise NotAuthenticated("Email o password non corretti.")
    settings = get_settings()
    token = create_access_token(user.id, user.role.value)
    response.set_cookie(
        ACCESS_TOKEN_COOKIE,
        token,
        max_age=settings.jwt_expire_minutes * 60,
        path="/api",
        httponly=True,
        samesite="strict",
        secure=settings.cookie_secure,
    )
    return TokenResponse(access_token=token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Esce ed elimina il cookie")
def logout(response: Response) -> None:
    """Elimina il cookie. Non richiede un token valido: uscire deve riuscire
    anche con una sessione già scaduta (operazione idempotente)."""
    response.delete_cookie(ACCESS_TOKEN_COOKIE, path="/api", httponly=True, samesite="strict",
                           secure=get_settings().cookie_secure)


@router.get("/me", response_model=UserRead, summary="Dati dell'utente autenticato")
def me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)
