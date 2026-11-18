"""Errori di dominio e loro traduzione in risposte HTTP.

I service sollevano un ``DomainError`` con un codice applicativo stabile (esempio ``EMAIL_TAKEN``): non conoscono HTTP, ma dichiarano lo stato suggerito.
Un unico gestore registrato in main.py produce il corpo uniforme ``{"detail": "...", "code": "..."}`` previsto dal contratto delle API.
Il front-end decide in base a ``code``, non al testo del messaggio.
"""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse


class DomainError(Exception):
    """Violazione di una regola di business o di accesso.
    È come lanciare un'eccezione personalizzata in PHP e intercettarla in un unico punto (un error handler) invece di costruire la risposta in ogni rotta.
    """

    def __init__(
        self,
        code: str,
        detail: str,
        status_code: int = status.HTTP_409_CONFLICT,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status_code = status_code
        self.headers = headers


class NotAuthenticated(DomainError):
    """401: token assente, scaduto o non valido."""

    def __init__(self, detail: str = "Autenticazione richiesta.") -> None:
        # WWW-Authenticate è obbligatoria con il 401 (RFC 9110, §15.5.2)
        super().__init__("NOT_AUTHENTICATED", detail, status.HTTP_401_UNAUTHORIZED,
                         headers={"WWW-Authenticate": "Bearer"})


class Forbidden(DomainError):
    """403: utente autenticato ma con ruolo non adeguato."""

    def __init__(self, detail: str = "Operazione non consentita per il tuo ruolo.") -> None:
        super().__init__("FORBIDDEN", detail, status.HTTP_403_FORBIDDEN)


class NotFound(DomainError):
    """404: risorsa inesistente o non visibile all'utente."""

    def __init__(self, detail: str = "Risorsa non trovata.") -> None:
        super().__init__("NOT_FOUND", detail, status.HTTP_404_NOT_FOUND)


async def _domain_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DomainError)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "code": exc.code},
        headers=exc.headers,
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _domain_error_handler)
