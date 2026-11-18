"""Test del generatore di codici di prenotazione (RF12)."""

from app.services.booking_codes import ALPHABET, CODE_LENGTH, ENTROPY_BITS, generate_booking_code


def test_formato_del_codice() -> None:
    code = generate_booking_code()
    assert len(code) == CODE_LENGTH
    assert set(code) <= set(ALPHABET)


def test_alfabeto_senza_caratteri_ambigui() -> None:
    assert not set("0O1IL") & set(ALPHABET)


def test_entropia_sufficiente() -> None:
    """Circa 49,5 bit: indovinare un codice valido per tentativi è impraticabile."""
    assert ENTROPY_BITS > 48


def test_codici_non_ripetuti() -> None:
    """Su 10.000 codici nessuna ripetizione (probabilità teorica di collisione ≈ 6 × 10⁻⁸)."""
    codes = [generate_booking_code() for _ in range(10_000)]
    assert len(set(codes)) == len(codes)


def test_tutti_i_simboli_usati_in_ogni_posizione() -> None:
    """Distribuzione uniforme: in ogni posizione compaiono tutti i 31 simboli.

    Con 10.000 codici ogni simbolo è atteso ~320 volte per posizione: un
    generatore sequenziale o difettoso lascerebbe posizioni quasi costanti.
    """
    codes = [generate_booking_code() for _ in range(10_000)]
    for position in range(CODE_LENGTH):
        assert {code[position] for code in codes} == set(ALPHABET)
