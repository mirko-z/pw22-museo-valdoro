"""Test dell'hashing delle password (RNF03)."""

import pytest

from app.core.security import BCRYPT_MAX_BYTES, hash_password, verify_password


def test_hash_bcrypt_di_60_caratteri() -> None:
    password_hash = hash_password("Valdoro-2026")
    assert len(password_hash) == 60
    assert password_hash.startswith("$2b$12$")  # algoritmo 2b, fattore di costo 12
    assert "Valdoro-2026" not in password_hash


def test_salt_diverso_a_ogni_hash() -> None:
    """Stessa password, hash diversi: il salt casuale impedisce gli attacchi con tabelle precalcolate."""
    assert hash_password("stessa-password") != hash_password("stessa-password")


def test_verifica_password() -> None:
    password_hash = hash_password("Valdoro-2026")
    assert verify_password("Valdoro-2026", password_hash)
    assert not verify_password("valdoro-2026", password_hash)
    assert not verify_password("", password_hash)


def test_password_con_caratteri_non_ascii() -> None:
    """Le password sono codificate in UTF-8: accenti e simboli funzionano."""
    password_hash = hash_password("città-perché-€")
    assert verify_password("città-perché-€", password_hash)


def test_limite_di_72_byte() -> None:
    """Oltre 72 byte bcrypt 5 rifiuta l'hash; la verifica restituisce False.

    Il limite è in byte, non in caratteri: "€" occupa 3 byte in UTF-8.
    Lo schema Pydantic della registrazione respingerà prima queste password (422).
    """
    at_limit = "€" * 24  # 72 byte
    assert len(at_limit.encode()) == BCRYPT_MAX_BYTES
    assert verify_password(at_limit, hash_password(at_limit))

    too_long = at_limit + "a"
    with pytest.raises(ValueError):
        hash_password(too_long)
    assert not verify_password(too_long, hash_password(at_limit))
