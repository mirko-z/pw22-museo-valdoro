"""Generazione dei codici di prenotazione.

Il codice identifica la prenotazione nelle URL (``/api/bookings/{code}/cancel``)
e viene comunicato al visitatore. Deve essere **non sequenziale**: con un id
progressivo (1001, 1002...) chiunque potrebbe provare i codici vicini al proprio.
"""

import math
import secrets

# 31 simboli: cifre e lettere maiuscole senza quelli che si confondono
# leggendo o dettando il codice (0/O, 1/I/L).
ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
CODE_LENGTH = 10

# Entropia = lunghezza × log2(simboli) ≈ 10 × 4,95 ≈ 49,5 bit:
# circa 8 × 10^14 codici possibili.
ENTROPY_BITS = CODE_LENGTH * math.log2(len(ALPHABET))


def generate_booking_code() -> str:
    """Restituisce un codice casuale di 10 caratteri, es. ``"K7QXM2D9TA"``.

    ``secrets`` usa il generatore crittograficamente sicuro del sistema
    operativo (come ``random_int()`` in PHP), non ``random``, che è prevedibile.
    Una collisione è molto improbabile; se accade, il vincolo UNIQUE su
    ``bookings.code`` la rileva e il service rigenera il codice.
    """
    return "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))
