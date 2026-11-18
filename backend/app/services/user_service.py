"""Logica di business di utenti e autenticazione (RF01, RF02, RF05, RF06)."""

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import DomainError, NotFound
from app.core.security import dummy_password_hash, hash_password, verify_password
from app.models import User, UserRole


class UserService:
    """Registrazione, verifica delle credenziali e gestione dei ruoli.

    Il service riceve la sessione dal chiamante (router, test o script):
    non apre connessioni da solo e non sa nulla di HTTP.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def register(self, email: str, full_name: str, password: str) -> User:
        """Crea un utente con ruolo ``visitor`` (l'unico ottenibile da registrazione)."""
        user = User(email=email, full_name=full_name, password_hash=hash_password(password),
                    role=UserRole.VISITOR)
        self.db.add(user)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            # L'unicità è garantita dall'indice su lower(email): niente SELECT
            # preventiva, che lascerebbe una finestra per una race condition.
            if _constraint(exc) == "uq_users_email_lower":
                raise DomainError("EMAIL_TAKEN", "Esiste già un account con questa email.") from exc
            raise
        return user

    def authenticate(self, email: str, password: str) -> User | None:
        """Restituisce l'utente se le credenziali sono corrette, altrimenti None.

        Il messaggio d'errore del router è lo stesso per email inesistente e
        password sbagliata, e anche i tempi sono simili (hash di riferimento).
        """
        user = self.db.scalar(select(User).where(func.lower(User.email) == email.strip().lower()))
        if user is None:
            verify_password(password, dummy_password_hash())
            return None
        return user if verify_password(password, user.password_hash) else None

    def list_users(self) -> list[User]:
        return list(self.db.scalars(select(User).order_by(User.id)))

    def change_role(self, actor: User, user_id: int, role: UserRole) -> User:
        """Cambia il ruolo di un utente. L'admin non può modificare il proprio,
        così il sistema non resta mai senza amministratori per errore."""
        if actor.id == user_id:
            raise DomainError("SELF_ROLE_CHANGE", "Non puoi modificare il tuo ruolo.")
        user = self.db.get(User, user_id)
        if user is None:
            raise NotFound("Utente non trovato.")
        user.role = role
        self.db.commit()
        return user


def _constraint(exc: IntegrityError) -> str | None:
    """Nome del vincolo violato riportato da PostgreSQL (vedi app/models/base.py)."""
    return getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
