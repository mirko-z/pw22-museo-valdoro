"""Test di autenticazione e autorizzazione (RF01–RF06, RNF03–RNF04, obiettivo O7).

Una verifica per regola: registrazione, credenziali, cookie, token non
validi, ruoli. Le richieste passano dall'app completa (router → service → DB).
"""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.models import User, UserRole

PASSWORD = "Valdoro-2026"


def create_user(db: Session, email: str, role: UserRole = UserRole.VISITOR) -> User:
    user = User(email=email, full_name="Utente di prova", role=role,
                password_hash=hash_password(PASSWORD))
    db.add(user)
    db.commit()
    return user


def login(client: TestClient, email: str, password: str = PASSWORD):  # type: ignore[no-untyped-def]
    return client.post("/api/auth/login", data={"username": email, "password": password})


def bearer(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role.value)}"}


# --- Registrazione (RF01) ------------------------------------------------------


def test_registrazione_crea_un_visitatore_con_password_hashata(client: TestClient, db_session: Session) -> None:
    response = client.post("/api/auth/register", json={
        "email": "  Mario.Rossi@Example.com ", "full_name": "Mario Rossi", "password": PASSWORD,
        "role": "admin",  # campo ignorato: il ruolo non si sceglie in registrazione
    })
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "mario.rossi@example.com"  # normalizzata
    assert body["role"] == "visitor"
    assert "password" not in str(body)

    stored = db_session.scalar(text("SELECT password_hash FROM users"))
    assert stored.startswith("$2b$") and PASSWORD not in stored


def test_email_gia_registrata(client: TestClient, db_session: Session) -> None:
    create_user(db_session, "mario.rossi@example.com")
    response = client.post("/api/auth/register", json={
        "email": "MARIO.ROSSI@example.com", "full_name": "Mario Rossi", "password": PASSWORD})
    assert response.status_code == 409
    assert response.json()["code"] == "EMAIL_TAKEN"


@pytest.mark.parametrize(("field", "value"), [
    ("email", "non-una-email"),
    ("password", "corta"),
    ("password", "€" * 25),  # 75 byte: oltre il limite di bcrypt
])
def test_dati_di_registrazione_non_validi(client: TestClient, field: str, value: str) -> None:
    data = {"email": "a@example.com", "full_name": "Anna", "password": PASSWORD} | {field: value}
    assert client.post("/api/auth/register", json=data).status_code == 422


# --- Login, cookie e logout (RF02, RF03, RNF04) --------------------------------


def test_login_imposta_cookie_httponly_e_samesite_strict(client: TestClient, db_session: Session) -> None:
    create_user(db_session, "anna@example.com")
    response = login(client, "anna@example.com")
    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"

    cookie = response.headers["set-cookie"].lower()
    assert "access_token=" in cookie
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    assert "path=/api" in cookie
    assert "secure" not in cookie  # solo in production

    # Il TestClient conserva il cookie come un browser: /me funziona senza header
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "anna@example.com"


def test_credenziali_errate_stesso_messaggio(client: TestClient, db_session: Session) -> None:
    """Email inesistente e password sbagliata sono indistinguibili (niente enumerazione)."""
    create_user(db_session, "anna@example.com")
    wrong_password = login(client, "anna@example.com", "password-sbagliata")
    unknown_email = login(client, "nessuno@example.com")
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()
    assert wrong_password.headers["www-authenticate"] == "Bearer"


def test_logout_elimina_il_cookie(client: TestClient, db_session: Session) -> None:
    create_user(db_session, "anna@example.com")
    login(client, "anna@example.com")
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_header_bearer_accettato(client: TestClient, db_session: Session) -> None:
    """Swagger e i test usano l'header Authorization invece del cookie."""
    user = create_user(db_session, "anna@example.com")
    assert client.get("/api/auth/me", headers=bearer(user)).status_code == 200


# --- Token non validi (RF04, RNF03) ----------------------------------------------


def _token(**overrides: object) -> str:
    now = datetime.now(UTC)
    payload = {"sub": "1", "role": "admin", "iat": now, "exp": now + timedelta(minutes=5)} | overrides
    return jwt.encode(payload, get_settings().jwt_secret, algorithm="HS256")


@pytest.mark.parametrize("token", [
    "non-un-jwt",
    _token(exp=datetime.now(UTC) - timedelta(seconds=1)),  # scaduto
    jwt.encode({"sub": "1", "iat": 0, "exp": 9999999999}, "x" * 32, algorithm="HS256"),  # altra chiave
    jwt.encode({"sub": "1", "iat": 0, "exp": 9999999999}, None, algorithm="none"),  # senza firma
])
def test_token_non_valido_rifiutato(client: TestClient, db_session: Session, token: str) -> None:
    create_user(db_session, "admin@example.com", UserRole.ADMIN)  # id 1: esiste davvero
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.json()["code"] == "NOT_AUTHENTICATED"


def test_senza_token_401(client: TestClient) -> None:
    assert client.get("/api/auth/me").status_code == 401


def test_ruolo_riletto_dal_database(client: TestClient, db_session: Session) -> None:
    """Un token emesso quando l'utente era admin non vale più dopo il declassamento."""
    user = create_user(db_session, "ex-admin@example.com", UserRole.ADMIN)
    headers = bearer(user)
    user.role = UserRole.VISITOR
    db_session.commit()
    assert client.get("/api/users", headers=headers).status_code == 403


# --- Gestione utenti riservata all'admin (RF05, RF06) ----------------------------


@pytest.mark.parametrize(("role", "expected"), [
    (UserRole.VISITOR, 403),
    (UserRole.STAFF, 403),
    (UserRole.ADMIN, 200),
])
def test_elenco_utenti_solo_admin(client: TestClient, db_session: Session, role: UserRole, expected: int) -> None:
    user = create_user(db_session, f"{role.value}@example.com", role)
    assert client.get("/api/users", headers=bearer(user)).status_code == expected


def test_admin_cambia_ruolo(client: TestClient, db_session: Session) -> None:
    admin = create_user(db_session, "admin@example.com", UserRole.ADMIN)
    visitor = create_user(db_session, "giulia@example.com")
    response = client.patch(f"/api/users/{visitor.id}/role", json={"role": "staff"}, headers=bearer(admin))
    assert response.status_code == 200
    assert response.json()["role"] == "staff"


def test_admin_non_cambia_il_proprio_ruolo(client: TestClient, db_session: Session) -> None:
    admin = create_user(db_session, "admin@example.com", UserRole.ADMIN)
    response = client.patch(f"/api/users/{admin.id}/role", json={"role": "visitor"}, headers=bearer(admin))
    assert response.status_code == 409
    assert response.json()["code"] == "SELF_ROLE_CHANGE"


def test_cambio_ruolo_utente_inesistente(client: TestClient, db_session: Session) -> None:
    admin = create_user(db_session, "admin@example.com", UserRole.ADMIN)
    response = client.patch("/api/users/999/role", json={"role": "staff"}, headers=bearer(admin))
    assert response.status_code == 404
