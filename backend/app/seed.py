"""Dati di esempio fittizi per dimostrazioni, screenshot e dashboard.

Uso:
    python -m app.seed               # carica i dati se il database è vuoto
    python -m app.seed --if-enabled  # come sopra, solo se SEED_DEMO_DATA=true (avvio del container)

Tutti i dati sono inventati. Le email usano i domini riservati ``example.com``
ed ``.example`` (RFC 2606), che non appartengono a nessuno: nessun dato
personale reale entra nel database (minimizzazione, art. 5 GDPR).

Le date sono relative al momento dell'esecuzione: ci sono sempre eventi
conclusi (con feedback, per la dashboard) ed eventi futuri prenotabili, su una
programmazione di circa sei mesi. Ogni evento è fissato su una settimana e un
giorno della settimana, non su un numero di giorni: i laboratori scolastici
cadono sempre in un giorno feriale e le visite per famiglie nel fine settimana,
qualunque sia il giorno in cui si avvia il progetto. Per lo stesso motivo i
titoli non citano stagioni o festività.
I dati sono inseriti direttamente con l'ORM, non tramite i service: servono
a popolare il database, non a esercitare la logica di prenotazione (che è
coperta dai test). I vincoli del database restano comunque attivi.
"""

from __future__ import annotations

import argparse
import random
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models import Booking, BookingStatus, Event, EventStatus, EventType, Feedback, User, UserRole
from app.services.booking_codes import generate_booking_code

ROME = ZoneInfo("Europe/Rome")

STAFF_ACCOUNTS = [
    ("admin@museovaldoro.example", "Laura Bertoni", UserRole.ADMIN),
    ("staff@museovaldoro.example", "Giulia Rinaldi", UserRole.STAFF),
]

# Insegnanti: prenotano i laboratori per un'intera classe
TEACHERS = ["Paola Ferrante", "Stefano Galli", "Chiara Moretti", "Roberto Fontana"]

VISITORS = [
    "Marco Bianchi",
    "Elena Russo",
    "Luca Romano",
    "Sara Colombo",
    "Andrea Ricci",
    "Francesca Marino",
    "Davide Greco",
    "Martina Bruno",
    "Simone Conti",
    "Giorgia Costa",
    "Matteo Giordano",
    "Alessia Rizzo",
    "Federico Lombardi",
    "Valentina Mancini",
    "Lorenzo Barbieri",
    "Ilaria Santoro",
    "Nicola Testa",
]

# Commenti coerenti con il voto (fascia) e con il tipo di evento:
# positivo per 4–5, misto per 3, negativo per 1–2.
COMMENTS: dict[str, dict[EventType, list[str]]] = {
    "positivo": {
        EventType.GUIDED_TOUR: [
            "Guida molto preparata, spiegazioni chiare.",
            "Esperienza bellissima, torneremo.",
            "Consigliatissima per le famiglie.",
        ],
        EventType.WORKSHOP: [
            "I ragazzi si sono divertiti e hanno imparato molto.",
            "Laboratorio ben organizzato, materiali curati.",
            "Operatori pazienti e coinvolgenti.",
        ],
        EventType.CONFERENCE: [
            "Relatore coinvolgente, argomento trattato con chiarezza.",
            "Ottima organizzazione, prenotazione semplicissima.",
            "Incontro interessante, spazio per le domande.",
        ],
    },
    "misto": {
        EventType.GUIDED_TOUR: [
            "Interessante, ma il gruppo era un po' numeroso.",
            "Durata giusta, sala un po' fredda.",
        ],
        EventType.WORKSHOP: [
            "Attività carina, ma i tempi erano un po' stretti.",
            "Buona idea, materiali da migliorare.",
        ],
        EventType.CONFERENCE: [
            "Relatore coinvolgente, peccato per l'audio in fondo alla sala.",
            "Argomento interessante, intervento un po' lungo.",
        ],
    },
    "negativo": {
        EventType.GUIDED_TOUR: [
            "Gruppo troppo numeroso, si sentiva poco.",
            "Visita più breve di quanto indicato.",
        ],
        EventType.WORKSHOP: [
            "Attività poco adatta all'età dei partecipanti.",
            "Inizio in ritardo e poco tempo per completare il lavoro.",
        ],
        EventType.CONFERENCE: [
            "Audio scarso, dal fondo della sala non si sentiva.",
            "Contenuti troppo tecnici per un pubblico generale.",
        ],
    },
}


def comment_band(rating: int) -> str:
    """Fascia del commento in base al voto."""
    if rating >= 4:
        return "positivo"
    return "misto" if rating == 3 else "negativo"


MON, TUE, WED, THU, FRI, SAT, SUN = range(7)

# Il programma della stagione è pubblicato circa 45 giorni prima dell'avvio:
# le prenotazioni degli eventi futuri si distribuiscono su queste settimane.
SEASON_PUBLISHED_DAYS_AGO = 45


@dataclass(frozen=True)
class DemoEvent:
    """Descrizione di un evento di esempio, con data relativa a oggi.

    ``@dataclass`` genera costruttore, confronto e rappresentazione a partire
    dagli attributi annotati: è una classe-contenitore senza codice ripetitivo.
    """

    title: str
    type: EventType
    week: int  # settimane rispetto a oggi (negative = passato)
    weekday: int  # 0 = lunedì … 6 = domenica
    start: time
    duration_minutes: int
    capacity: int
    price: str
    max_seats: int
    deadline_hours: int
    fill: float  # frazione della capienza da prenotare (0 = nessuna prenotazione)
    cancelled: bool = False
    description: str | None = None

    @property
    def for_schools(self) -> bool:
        """Laboratorio per le scuole: prenotato dagli insegnanti per un'intera classe."""
        return self.type is EventType.WORKSHOP and self.max_seats >= 15


DEMO_EVENTS = [
    # --- Eventi conclusi: alimentano feedback e indicatori della dashboard
    DemoEvent("Visita guidata alla collezione permanente", EventType.GUIDED_TOUR, -7, SAT, time(10), 90, 25, "8.00", 6, 24, 0.85,
              description="Percorso tra le sale della collezione civica, dall'età romana all'Ottocento."),
    DemoEvent("Laboratorio: l'affresco (scuola primaria)", EventType.WORKSHOP, -6, WED, time(9, 30), 120, 60, "0.00", 30, 72, 0.9),
    DemoEvent("Conferenza: Valdoro nel Medioevo", EventType.CONFERENCE, -5, THU, time(18), 120, 80, "0.00", 4, 2, 0.4),
    DemoEvent("Visita guidata alla mostra \"Terre e colori\"", EventType.GUIDED_TOUR, -4, SUN, time(16), 90, 20, "10.00", 6, 24, 0.95),
    DemoEvent("Laboratorio: archeologi per un giorno", EventType.WORKSHOP, -3, WED, time(9, 30), 150, 50, "3.00", 30, 72, 0.7),
    DemoEvent("Visita guidata serale", EventType.GUIDED_TOUR, -2, FRI, time(21), 90, 20, "12.00", 6, 24, 0.6, cancelled=True,
              description="Annullata per indisponibilità della guida."),
    DemoEvent("Conferenza: restauro e diagnostica", EventType.CONFERENCE, -1, THU, time(18), 120, 80, "0.00", 4, 2, 0.35),
    # --- Eventi futuri, circa sei mesi di programmazione. Le prenotazioni calano
    # con la distanza: gli eventi vicini sono quasi pieni, quelli lontani quasi vuoti.
    DemoEvent("Visita guidata alla collezione permanente", EventType.GUIDED_TOUR, 0, SAT, time(10), 90, 25, "8.00", 6, 24, 0.5),
    # Posti disponibili (22) sotto il massimo per prenotazione (30): caso mostrato dall'interfaccia
    DemoEvent("Laboratorio: il mosaico", EventType.WORKSHOP, 0, WED, time(9, 30), 120, 50, "3.00", 30, 72, 0.56),
    DemoEvent("Visita guidata alla mostra \"Terre e colori\"", EventType.GUIDED_TOUR, 1, SUN, time(16), 90, 12, "10.00", 6, 24, 1.0,
              description="Gruppo ridotto: posti limitati."),
    DemoEvent("Conferenza: musei e comunità", EventType.CONFERENCE, 1, THU, time(18), 120, 80, "0.00", 4, 2, 0.2),
    DemoEvent("Visita guidata per famiglie", EventType.GUIDED_TOUR, 2, SUN, time(15), 75, 20, "5.00", 6, 24, 0.3),
    DemoEvent("Laboratorio: stampa e incisione", EventType.WORKSHOP, 3, TUE, time(9, 30), 120, 40, "3.00", 30, 72, 0.0),
    DemoEvent("Laboratorio: la ceramica (scuola secondaria)", EventType.WORKSHOP, 4, THU, time(9, 30), 120, 50, "3.00", 30, 72, 0.4),
    DemoEvent("Conferenza: il collezionismo a Valdoro", EventType.CONFERENCE, 5, FRI, time(18), 120, 80, "0.00", 4, 2, 0.15),
    DemoEvent("Visita guidata per famiglie: animali nell'arte", EventType.GUIDED_TOUR, 7, SUN, time(15), 75, 25, "5.00", 6, 24, 0.25),
    DemoEvent("Visita guidata alla collezione permanente", EventType.GUIDED_TOUR, 9, SAT, time(10), 90, 25, "8.00", 6, 24, 0.12),
    DemoEvent("Laboratorio per famiglie: colori naturali", EventType.WORKSHOP, 10, SAT, time(15), 90, 30, "5.00", 6, 24, 0.1,
              description="Per bambini dai 6 ai 10 anni con un adulto."),
    DemoEvent("Conferenza: archeologia del territorio", EventType.CONFERENCE, 13, THU, time(18), 120, 80, "0.00", 4, 2, 0.05),
    DemoEvent("Laboratorio: archeologi per un giorno", EventType.WORKSHOP, 15, WED, time(9, 30), 150, 50, "3.00", 30, 72, 0.3),
    DemoEvent("Visita guidata alla mostra \"Terre e colori\": ultime settimane", EventType.GUIDED_TOUR, 17, SUN, time(16), 90, 20,
              "10.00", 6, 24, 0.05),
    DemoEvent("Conferenza: musei e intelligenza artificiale", EventType.CONFERENCE, 20, THU, time(18), 120, 80, "0.00", 4, 2, 0.0),
    DemoEvent("Laboratorio: il mosaico", EventType.WORKSHOP, 22, TUE, time(9, 30), 120, 50, "3.00", 30, 72, 0.0),
    DemoEvent("Visita guidata alla collezione permanente", EventType.GUIDED_TOUR, 25, SUN, time(10), 90, 25, "8.00", 6, 24, 0.0),
]


class DemoDataSeeder:
    """Popola un database vuoto con utenti, eventi, prenotazioni e feedback."""

    def __init__(self, session: Session, password: str, now: datetime | None = None, seed: int = 2026) -> None:
        self.session = session
        self.password = password
        self.now = now or datetime.now(UTC)
        # Generatore pseudo-casuale con seme fisso: a parità di data i dati sono
        # sempre gli stessi. Va bene per dati dimostrativi, NON per i codici di
        # prenotazione, che usano secrets.
        self.rng = random.Random(seed)

    def is_database_empty(self) -> bool:
        return self.session.scalar(select(func.count()).select_from(User)) == 0

    def run(self) -> bool:
        """Inserisce i dati in un'unica transazione. Restituisce False se il database non è vuoto."""
        if not self.is_database_empty():
            return False
        teachers, visitors = self._create_users()
        for spec in DEMO_EVENTS:
            event = self._create_event(spec)
            candidates = teachers if spec.for_schools else visitors
            self._create_bookings(event, spec, candidates)
            if spec.cancelled:
                self._cancel_event(event)
            elif event.end_at < self.now:
                self._create_feedback(event)
        # Tutto o niente: se un vincolo fallisce, il rollback annulla l'intero seed
        self.session.commit()
        return True

    # --- utenti ------------------------------------------------------------

    def _create_users(self) -> tuple[list[User], list[User]]:
        for email, name, role in STAFF_ACCOUNTS:
            self.session.add(self._user(email, name, role))
        teachers = [self._user(_email(name), name, UserRole.VISITOR) for name in TEACHERS]
        visitors = [self._user(_email(name), name, UserRole.VISITOR) for name in VISITORS]
        self.session.add_all(teachers + visitors)
        return teachers, visitors

    def _user(self, email: str, full_name: str, role: UserRole) -> User:
        # Ogni hash ha un salt diverso, anche se la password è la stessa
        created = self.now - timedelta(days=self.rng.randint(60, 90))
        return User(email=email, full_name=full_name, role=role,
                    password_hash=hash_password(self.password), created_at=created)

    # --- eventi ------------------------------------------------------------

    def _create_event(self, spec: DemoEvent) -> Event:
        day = _event_day(self.now.astimezone(ROME).date(), spec.week, spec.weekday)
        start_at = _rome(day, spec.start)
        # Pubblicato almeno un mese prima; gli eventi della stagione in corso
        # all'uscita del programma, cioè circa 45 giorni prima di oggi
        published = self.now - timedelta(days=SEASON_PUBLISHED_DAYS_AGO + self.rng.randint(0, 3))
        created_at = min(start_at - timedelta(days=30), published)
        event = Event(
            title=spec.title,
            description=spec.description,
            type=spec.type,
            start_at=start_at,
            end_at=start_at + timedelta(minutes=spec.duration_minutes),
            capacity=spec.capacity,
            price=Decimal(spec.price),
            max_seats_per_booking=spec.max_seats,
            cancellation_deadline_hours=spec.deadline_hours,
            created_at=created_at,
        )
        self.session.add(event)
        self.session.flush()  # assegna event.id senza chiudere la transazione
        return event

    def _cancel_event(self, event: Event) -> None:
        """Annulla l'evento due giorni prima e, con esso, le prenotazioni confermate (RF10)."""
        cancelled_at = event.start_at - timedelta(days=2)
        event.status = EventStatus.CANCELLED
        for booking in event.bookings:
            if booking.status is BookingStatus.CONFIRMED:
                booking.status = BookingStatus.CANCELLED
                booking.cancelled_at = cancelled_at

    # --- prenotazioni ------------------------------------------------------

    def _create_bookings(self, event: Event, spec: DemoEvent, candidates: list[User]) -> None:
        remaining = round(event.capacity * spec.fill)
        # Per un evento annullato le prenotazioni devono precedere l'annullamento
        last_moment = min(event.start_at - timedelta(days=2 if spec.cancelled else 0, hours=2), self.now)
        for user in self.rng.sample(candidates, k=len(candidates)):
            if remaining <= 0:
                break
            low = 15 if spec.for_schools else 1  # una classe intera
            seats = min(self.rng.randint(low, event.max_seats_per_booking), remaining)
            created_at = self._between(event.created_at, last_moment)

            # Circa una prenotazione su sei viene annullata entro il termine;
            # a volte l'utente riprenota (l'indice parziale lo consente).
            deadline = event.start_at - timedelta(hours=event.cancellation_deadline_hours)
            cancel_until = min(deadline, last_moment)
            if self.rng.random() < 0.17 and cancel_until > created_at:
                cancelled_at = self._between(created_at, cancel_until)
                self._booking(user, event, seats, created_at, cancelled_at)
                if self.rng.random() > 0.4:
                    continue
                created_at = self._between(cancelled_at, last_moment)
                seats = min(self.rng.randint(low, event.max_seats_per_booking), remaining)

            self._booking(user, event, seats, created_at)
            remaining -= seats

    def _booking(self, user: User, event: Event, seats: int, created_at: datetime,
                 cancelled_at: datetime | None = None) -> None:
        status = BookingStatus.CANCELLED if cancelled_at else BookingStatus.CONFIRMED
        self.session.add(Booking(
            user=user, event=event, seats=seats, status=status, code=generate_booking_code(),
            created_at=created_at, cancelled_at=cancelled_at,
        ))

    # --- feedback ----------------------------------------------------------

    def _create_feedback(self, event: Event) -> None:
        """Feedback da circa due terzi dei partecipanti, dopo la fine dell'evento."""
        for booking in event.bookings:
            if booking.status is not BookingStatus.CONFIRMED or self.rng.random() > 0.65:
                continue
            rating = self.rng.choices([1, 2, 3, 4, 5], weights=[2, 5, 18, 40, 35])[0]
            pool = COMMENTS[comment_band(rating)][event.type]
            comment = self.rng.choice(pool) if self.rng.random() < 0.5 else None
            created_at = min(event.end_at + timedelta(hours=self.rng.randint(1, 72)), self.now)
            self.session.add(Feedback(user=booking.user, event=event, rating=rating,
                                      comment=comment, created_at=created_at))

    def _between(self, start: datetime, end: datetime) -> datetime:
        """Istante casuale tra start ed end (end se l'intervallo è vuoto)."""
        if end <= start:
            return end
        return start + (end - start) * self.rng.random()


def _event_day(today: date, week: int, weekday: int) -> date:
    """Giorno ``weekday`` (0 = lunedì) della settimana ``week`` rispetto a ``today``.

    Nel futuro (week >= 0) il giorno è sempre da domani in poi, così un evento
    "di oggi" non risulta già iniziato; nel passato è sempre almeno 7 giorni fa.
    """
    base = today + timedelta(weeks=week)
    if week >= 0:
        return base + timedelta(days=(weekday - base.weekday() - 1) % 7 + 1)
    return base - timedelta(days=(base.weekday() - weekday) % 7)


def _rome(day: date, at: time) -> datetime:
    """Data e ora locali di Roma -> istante con fuso orario (salvato in UTC)."""
    return datetime.combine(day, at, tzinfo=ROME)


def _email(full_name: str) -> str:
    return full_name.lower().replace(" ", ".") + "@example.com"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Carica i dati di esempio fittizi.")
    parser.add_argument("--if-enabled", action="store_true",
                        help="esegue solo se SEED_DEMO_DATA=true (usato all'avvio del container)")
    args = parser.parse_args(argv)
    settings: Settings = get_settings()

    if args.if_enabled and not settings.seed_demo_data:
        return 0
    if settings.app_env == "production":
        print("Seed: rifiutato in ambiente production.", file=sys.stderr)
        return 1
    if len(settings.seed_demo_password) < 8:
        print("Seed: impostare SEED_DEMO_PASSWORD (almeno 8 caratteri).", file=sys.stderr)
        return 1

    # "with" è un context manager: alla fine del blocco la sessione viene
    # chiusa in ogni caso, anche se si verifica un'eccezione (come un finally).
    with SessionLocal() as session:
        loaded = DemoDataSeeder(session, settings.seed_demo_password).run()
    print("Seed: dati di esempio caricati." if loaded else "Seed: database già popolato, nessuna modifica.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
