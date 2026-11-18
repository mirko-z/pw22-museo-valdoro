"""Funzioni di sicurezza: hash delle password e token JWT."""

from datetime import UTC, datetime, timedelta
from functools import lru_cache

import bcrypt
import jwt

from app.core.config import get_settings

# bcrypt considera solo i primi 72 byte della password: oltre quel limite
# due password diverse con lo stesso prefisso avrebbero lo stesso hash.
# Dalla versione 5.0 la libreria rifiuta le password più lunghe con un
# ValueError; gli schemi Pydantic le respingono prima, con un errore 422.
BCRYPT_MAX_BYTES = 72

# Algoritmo fissato lato server: il decoder accetta solo HS256 e ignora
# l'algoritmo dichiarato nell'intestazione del token (RFC 8725, §3.1),
# così un token con "alg": "none" o con un altro algoritmo viene rifiutato.
JWT_ALGORITHM = "HS256"


# --- Password ------------------------------------------------------------------


def hash_password(password: str) -> str:
    """Restituisce l'hash bcrypt della password (60 caratteri ASCII).

    ``gensalt()`` genera un salt casuale diverso per ogni chiamata, incluso
    nell'hash insieme al fattore di costo: due utenti con la stessa password
    hanno hash diversi. Equivale a ``password_hash($pwd, PASSWORD_BCRYPT)`` in PHP.
    """
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    """Confronta la password con l'hash (come ``password_verify`` in PHP).

    Il confronto avviene in tempo costante, per non rivelare informazioni
    attraverso i tempi di risposta. Una password oltre il limite di bcrypt
    non può corrispondere a nessun hash valido: si restituisce False.
    """
    encoded = password.encode("utf-8")
    if len(encoded) > BCRYPT_MAX_BYTES:
        return False
    return bcrypt.checkpw(encoded, password_hash.encode("ascii"))


@lru_cache
def dummy_password_hash() -> str:
    """Hash di riferimento per i login con email inesistente.

    Verificare la password anche quando l'utente non esiste rende simili i
    tempi di risposta nei due casi: un attaccante non può capire dai tempi
    quali email sono registrate (enumerazione degli utenti).
    """
    return hash_password("password-di-riferimento-non-usata")


# --- JWT -----------------------------------------------------------------------


def create_access_token(user_id: int, role: str, now: datetime | None = None) -> str:
    """Crea un JWT firmato con HMAC-SHA256 e scadenza breve (RFC 7519).

    Claim: ``sub`` (id dell'utente, come stringa), ``role`` (informativo,
    utile al front-end), ``iat`` (emissione) ed ``exp`` (scadenza).
    Il token non contiene dati riservati: il payload è solo codificato in
    Base64URL, non cifrato, e chiunque lo possieda può leggerlo.
    """
    settings = get_settings()
    issued_at = now or datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": issued_at,
        "exp": issued_at + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> int | None:
    """Verifica firma e scadenza; restituisce l'id dell'utente o None se il token non è valido.

    PyJWT controlla da solo ``exp``: un token scaduto solleva un'eccezione,
    come uno con firma errata o malformato. Il ruolo NON viene preso dal
    token ma riletto dal database a ogni richiesta (vedi core/deps.py), così
    un cambio di ruolo ha effetto subito, senza attendere la scadenza.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["exp", "iat", "sub"]},
        )
        return int(payload["sub"])
    except (jwt.InvalidTokenError, ValueError):
        return None
