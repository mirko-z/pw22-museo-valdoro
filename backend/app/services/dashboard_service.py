"""Indicatori per la direzione (RF19–RF22, KPI K5–K8, obiettivo O6).

Definizioni:
- K5 tasso di annullamento = prenotazioni annullate / prenotazioni totali;
- K6 tasso di riempimento = posti confermati / capienza, per evento;
- K7 copertura del feedback = feedback / prenotazioni confermate di eventi conclusi;
- K8 soddisfazione = voto medio per evento e per tipo di evento.

Scelte di calcolo:
- Gli **eventi annullati dal museo** sono esclusi dagli aggregati: le loro
  prenotazioni sono annullate d'ufficio e falserebbero K5, che misura il
  comportamento dei visitatori, e K6. Restano visibili nell'elenco per evento.
- Il riempimento medio considera solo gli eventi **conclusi**: per quelli
  futuri le prenotazioni sono ancora aperte.
- Un rapporto con denominatore zero vale ``None`` (non calcolabile), non 0.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.orm import Session

from app.models import Booking, BookingStatus, Event, EventStatus, EventType, Feedback

ROME = ZoneInfo("Europe/Rome")


def ratio(numerator: float, denominator: float) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


@dataclass(frozen=True)
class EventStats:
    event_id: int
    title: str
    type: EventType
    start_at: datetime
    status: EventStatus
    is_ended: bool
    capacity: int
    bookings_total: int
    bookings_cancelled: int
    bookings_confirmed: int
    confirmed_seats: int
    feedback_count: int
    rating_sum: int

    @property
    def fill_rate(self) -> float | None:  # K6
        return ratio(self.confirmed_seats, self.capacity)

    @property
    def cancellation_rate(self) -> float | None:  # K5
        return ratio(self.bookings_cancelled, self.bookings_total)

    @property
    def average_rating(self) -> float | None:  # K8
        return ratio(self.rating_sum, self.feedback_count)

    @property
    def feedback_coverage(self) -> float | None:  # K7, solo per eventi conclusi
        return ratio(self.feedback_count, self.bookings_confirmed) if self.counts_as_concluded else None

    @property
    def counts_as_concluded(self) -> bool:
        return self.is_ended and self.status is EventStatus.SCHEDULED


class DashboardService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def event_stats(self) -> list[EventStats]:
        """Una riga per evento con i conteggi di base, in una sola query.

        Le aggregazioni su prenotazioni e feedback sono in due sottoquery
        separate: un doppio JOIN diretto moltiplicherebbe le righe
        (ogni prenotazione per ogni feedback) e falserebbe le somme.
        """
        confirmed = Booking.status == BookingStatus.CONFIRMED
        b = (
            select(
                Booking.event_id,
                func.count().label("total"),
                func.count().filter(Booking.status == BookingStatus.CANCELLED).label("cancelled"),
                func.count().filter(confirmed).label("confirmed"),
                func.coalesce(func.sum(Booking.seats).filter(confirmed), 0).label("seats"),
            ).group_by(Booking.event_id).subquery()
        )
        f = (
            select(Feedback.event_id, func.count().label("n"),
                   cast(func.sum(Feedback.rating), Integer).label("rating_sum"))
            .group_by(Feedback.event_id).subquery()
        )
        rows = self.db.execute(
            select(Event, b.c.total, b.c.cancelled, b.c.confirmed, b.c.seats, f.c.n, f.c.rating_sum)
            .outerjoin(b, b.c.event_id == Event.id)
            .outerjoin(f, f.c.event_id == Event.id)
            .order_by(Event.start_at)
        ).all()
        now = datetime.now(UTC)
        return [
            EventStats(e.id, e.title, e.type, e.start_at, e.status, e.end_at < now, e.capacity,
                       total or 0, cancelled or 0, conf or 0, seats or 0, n or 0, rating_sum or 0)
            for e, total, cancelled, conf, seats, n, rating_sum in rows
        ]

    def overview(self) -> dict[str, float | int | None]:
        stats = [s for s in self.event_stats() if s.status is EventStatus.SCHEDULED]
        concluded = [s for s in stats if s.counts_as_concluded]
        fill_rates = [s.fill_rate for s in concluded if s.fill_rate is not None]
        total = sum(s.bookings_total for s in stats)
        feedback = sum(s.feedback_count for s in stats)
        return {
            "events_upcoming": sum(1 for s in stats if not s.is_ended),
            "events_concluded": len(concluded),
            "bookings_total": total,
            "bookings_cancelled": sum(s.bookings_cancelled for s in stats),
            "cancellation_rate": ratio(sum(s.bookings_cancelled for s in stats), total),
            "average_fill_rate": round(sum(fill_rates) / len(fill_rates), 4) if fill_rates else None,
            "feedback_count": feedback,
            "average_rating": ratio(sum(s.rating_sum for s in stats), feedback),
            "feedback_coverage": ratio(sum(s.feedback_count for s in concluded),
                                       sum(s.bookings_confirmed for s in concluded)),
        }

    def by_type(self) -> list[dict[str, object]]:
        """K6 e K8 per tipo di evento, sugli eventi conclusi e non annullati."""
        groups: dict[EventType, list[EventStats]] = defaultdict(list)
        for s in self.event_stats():
            if s.counts_as_concluded:
                groups[s.type].append(s)
        result = []
        for event_type in EventType:
            items = groups.get(event_type, [])
            fills = [s.fill_rate for s in items if s.fill_rate is not None]
            n = sum(s.feedback_count for s in items)
            result.append({
                "type": event_type,
                "events_concluded": len(items),
                "average_fill_rate": round(sum(fills) / len(fills), 4) if fills else None,
                "feedback_count": n,
                "average_rating": ratio(sum(s.rating_sum for s in items), n),
            })
        return result

    def weekly(self, weeks: int, today: date | None = None) -> list[dict[str, object]]:
        """Prenotazioni create per settimana (da lunedì, ora di Roma), ultime ``weeks`` settimane.

        Le settimane senza prenotazioni compaiono con 0, così il grafico non ha buchi.
        """
        today = today or datetime.now(ROME).date()
        current_monday = today - timedelta(days=today.weekday())
        mondays = [current_monday - timedelta(weeks=i) for i in reversed(range(weeks))]
        week_start = func.date_trunc("week", func.timezone("Europe/Rome", Booking.created_at))
        start = datetime.combine(mondays[0], datetime.min.time(), tzinfo=ROME)
        rows = self.db.execute(
            select(func.date(week_start), func.count(), func.coalesce(func.sum(Booking.seats), 0))
            .where(Booking.created_at >= start)
            .group_by(week_start)
        ).all()
        counts = {week: (n, seats) for week, n, seats in rows}
        return [{"week_start": m, "bookings": counts.get(m, (0, 0))[0], "seats": counts.get(m, (0, 0))[1]}
                for m in mondays]
