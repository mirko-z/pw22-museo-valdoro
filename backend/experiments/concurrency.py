"""Esperimento: overbooking e latenza con e senza lock di riga (obiettivi O1, O3; RNF07).

Ipotesi: con N richieste simultanee sugli ultimi K posti di un evento, la
strategia senza lock (naive) vende più posti della capienza; quella con
``SELECT ... FOR UPDATE`` non vende mai oltre la capienza, al costo di una
latenza maggiore (le transazioni sullo stesso evento attendono il lock).

Metodo:
- database dedicato ``<POSTGRES_DB>_experiment`` (creato e migrato se manca),
  per non alterare i dati dimostrativi;
- per ogni ripetizione: un evento con capienza N + K e N posti già confermati,
  quindi restano esattamente K posti liberi; N visitatori diversi chiedono
  1 posto ciascuno, tutti nello stesso istante (``threading.Barrier``);
- ogni richiesta è un thread con la **propria connessione** (già aperta prima
  della partenza, così il tempo di connessione non entra nella misura);
- nessun ritardo artificiale (``critical_section_delay = 0``): si misura il
  comportamento reale.

Misure per ripetizione: prenotazioni accettate e rifiutate, posti venduti oltre
la capienza, latenza (media, mediana, 95° percentile) e throughput.

Uso, dalla radice del repository (risultati in docs/risultati/):
    docker compose run --rm -v "$PWD/docs/risultati:/app/results" api \\
        python -m experiments.concurrency --out results

Opzioni: --n 10 50 100  --repetitions 10  --seats-left 2  --strategies locking naive  --warmup 1
"""

from __future__ import annotations

import argparse
import csv
import os
import platform
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings

# --- 1. Database dell'esperimento, prima di importare il resto dell'applicazione --
_main = Settings()  # type: ignore[call-arg]
EXPERIMENT_DB = f"{_main.postgres_db}_experiment"
os.environ["POSTGRES_DB"] = EXPERIMENT_DB

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.db import CONNECT_ARGS  # noqa: E402
from app.core.errors import DomainError  # noqa: E402
from app.models import Booking, BookingStatus, Event, EventType, User, UserRole  # noqa: E402
from app.services.booking_codes import generate_booking_code  # noqa: E402
from app.services.booking_strategies import (  # noqa: E402
    BookingStrategy,
    LockingBookingStrategy,
    NaiveBookingStrategy,
)

STRATEGIES: dict[str, type[BookingStrategy]] = {"locking": LockingBookingStrategy, "naive": NaiveBookingStrategy}
FAKE_HASH = "$2b$12$" + "e" * 53  # gli utenti dell'esperimento non fanno login


@dataclass(frozen=True)
class RepetitionResult:
    strategy: str
    n: int
    repetition: int
    seats_left: int
    capacity: int
    accepted: int
    rejected: int
    errors: int
    confirmed_seats: int
    oversold: int
    latency_mean_ms: float
    latency_median_ms: float
    latency_p95_ms: float
    throughput_rps: float


class ConcurrencyExperiment:
    def __init__(self, max_threads: int) -> None:
        settings = get_settings()
        self._prepare_database(settings)
        # Pool dimensionato sul numero di thread: nessuna richiesta deve attendere
        # una connessione libera, altrimenti si misurerebbe il pool e non il lock.
        self.engine = create_engine(settings.database_url, pool_size=max_threads + 2, max_overflow=0,
                                    connect_args=CONNECT_ARGS)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.users: list[int] = []

    @staticmethod
    def _prepare_database(settings: Settings) -> None:
        admin = create_engine(_main.database_url, isolation_level="AUTOCOMMIT")
        with admin.connect() as conn:
            if not conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": EXPERIMENT_DB}):
                conn.execute(text(f'CREATE DATABASE "{EXPERIMENT_DB}"'))
        admin.dispose()
        command.upgrade(Config(str(Path(__file__).resolve().parent.parent / "alembic.ini")), "head")

    def reset(self, n_users: int) -> None:
        """Database vuoto e N visitatori (+1 che occupa i posti iniziali)."""
        with self.Session() as s:
            s.execute(text("TRUNCATE feedback, bookings, events, users RESTART IDENTITY CASCADE"))
            users = [User(email=f"exp{i}@example.com", full_name=f"Visitatore {i}",
                          password_hash=FAKE_HASH, role=UserRole.VISITOR) for i in range(n_users + 1)]
            s.add_all(users)
            s.commit()
            self.users = [u.id for u in users]

    def _new_event(self, n: int, seats_left: int) -> tuple[int, int]:
        """Evento con capienza N + K e N posti già confermati: restano K posti."""
        capacity = n + seats_left
        start = datetime.now(UTC) + timedelta(days=30)
        with self.Session() as s:
            s.execute(text("TRUNCATE bookings RESTART IDENTITY CASCADE"))
            event = Event(title="Esperimento", type=EventType.GUIDED_TOUR, start_at=start,
                          end_at=start + timedelta(hours=1), capacity=capacity, max_seats_per_booking=1,
                          cancellation_deadline_hours=0)
            s.add(event)
            s.flush()
            s.add(Booking(user_id=self.users[0], event_id=event.id, seats=n, code=generate_booking_code(),
                          status=BookingStatus.CONFIRMED))
            s.commit()
            return event.id, capacity

    def run_repetition(self, strategy_name: str, n: int, seats_left: int, repetition: int) -> RepetitionResult:
        event_id, capacity = self._new_event(n, seats_left)
        strategy = STRATEGIES[strategy_name]()
        barrier = threading.Barrier(n)
        user_ids = self.users[1:n + 1]

        def attempt(user_id: int) -> tuple[str, float, float]:
            with self.Session() as session:
                session.connection()  # connessione aperta PRIMA della partenza
                user = session.get_one(User, user_id)
                session.commit()      # chiude la transazione di lettura dell'utente
                barrier.wait()
                started = time.perf_counter()
                try:
                    strategy.reserve(session, user, event_id, seats=1)
                    outcome = "accepted"
                except DomainError:
                    outcome = "rejected"
                except Exception:  # errore inatteso: contato a parte, non nascosto
                    session.rollback()
                    outcome = "error"
                return outcome, started, time.perf_counter()

        with ThreadPoolExecutor(max_workers=n) as pool:
            results = list(pool.map(attempt, user_ids))

        with self.Session() as s:
            confirmed = s.scalar(text("SELECT sum(seats) FROM bookings WHERE event_id = :e AND status = 'confirmed'"),
                                 {"e": event_id}) or 0
        latencies = [(end - start) * 1000 for _, start, end in results]
        elapsed = max(end for _, _, end in results) - min(start for _, start, _ in results)
        return RepetitionResult(
            strategy=strategy_name, n=n, repetition=repetition, seats_left=seats_left, capacity=capacity,
            accepted=sum(o == "accepted" for o, _, _ in results),
            rejected=sum(o == "rejected" for o, _, _ in results),
            errors=sum(o == "error" for o, _, _ in results),
            confirmed_seats=confirmed, oversold=max(0, confirmed - capacity),
            latency_mean_ms=round(statistics.fmean(latencies), 2),
            latency_median_ms=round(statistics.median(latencies), 2),
            latency_p95_ms=round(percentile(latencies, 95), 2),
            throughput_rps=round(n / elapsed, 1),
        )


def percentile(values: list[float], p: int) -> float:
    """Percentile con interpolazione lineare (metodo "inclusive")."""
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=100, method="inclusive")[p - 1]


SUMMARY_FIELDS = ["accepted", "rejected", "oversold", "latency_mean_ms", "latency_median_ms",
                  "latency_p95_ms", "throughput_rps"]


def summarize(results: list[RepetitionResult]) -> list[dict[str, object]]:
    """Media e deviazione standard campionaria per strategia e N."""
    rows = []
    for key in sorted({(r.strategy, r.n) for r in results}):
        group = [r for r in results if (r.strategy, r.n) == key]
        row: dict[str, object] = {"strategy": key[0], "n": key[1], "repetitions": len(group),
                                  "seats_left": group[0].seats_left,
                                  "runs_with_overbooking": sum(r.oversold > 0 for r in group)}
        for field in SUMMARY_FIELDS:
            values = [float(getattr(r, field)) for r in group]
            row[f"{field}_mean"] = round(statistics.fmean(values), 2)
            row[f"{field}_std"] = round(statistics.stdev(values), 2) if len(values) > 1 else 0.0
        rows.append(row)
    return rows


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Esperimento sulla concorrenza delle prenotazioni.")
    parser.add_argument("--n", type=int, nargs="+", default=[10, 50, 100], help="richieste simultanee")
    parser.add_argument("--repetitions", type=int, default=10)
    parser.add_argument("--seats-left", type=int, default=2, help="posti liberi (K)")
    parser.add_argument("--strategies", nargs="+", choices=list(STRATEGIES), default=["locking", "naive"])
    parser.add_argument("--warmup", type=int, default=1,
                        help="ripetizioni iniziali non registrate per configurazione (cache a freddo)")
    parser.add_argument("--out", type=Path, default=Path("results"))
    args = parser.parse_args(argv)

    experiment = ConcurrencyExperiment(max_threads=max(args.n))
    experiment.reset(max(args.n))
    results: list[RepetitionResult] = []
    for n in args.n:
        for strategy in args.strategies:
            # Riscaldamento: la prima esecuzione paga cache e connessioni a freddo
            # (nelle prove: p95 di 454 ms contro ~155 ms delle successive)
            for _ in range(args.warmup):
                experiment.run_repetition(strategy, n, args.seats_left, 0)
            for rep in range(1, args.repetitions + 1):
                r = experiment.run_repetition(strategy, n, args.seats_left, rep)
                results.append(r)
                print(f"{strategy:8} N={n:<4} rip.{rep:<3} accettate={r.accepted:<4} oltre capienza={r.oversold:<4} "
                      f"p95={r.latency_p95_ms:.1f} ms", flush=True)

    args.out.mkdir(parents=True, exist_ok=True)
    write_csv(args.out / "esperimento_ripetizioni.csv", [asdict(r) for r in results])
    write_csv(args.out / "esperimento_sintesi.csv", summarize(results))
    # Contesto di esecuzione: serve per descrivere l'ambiente nel report
    (args.out / "esperimento_ambiente.txt").write_text(
        f"data: {datetime.now(UTC).isoformat(timespec='seconds')}\n"
        f"python: {sys.version.split()[0]}\nsistema: {platform.platform()}\n"
        f"cpu logiche: {os.cpu_count()}\nparametri: {vars(args)}\n", encoding="utf-8")
    print(f"Risultati scritti in {args.out}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
