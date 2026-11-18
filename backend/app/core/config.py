"""Configurazione dell'applicazione, letta dalle variabili d'ambiente.

Equivalente di un file config.php, ma tipizzato e validato: se una variabile manca o ha un tipo sbagliato, l'applicazione non parte e l'errore dice quale.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    """Parametri di esecuzione.

    Ogni attributo corrisponde a una variabile d'ambiente con lo stesso nome in maiuscolo (es. ``postgres_user`` <- ``POSTGRES_USER``). Le annotazioni
    di tipo (``: int``, ``: str``) non sono solo documentazione: Pydantic le usa per convertire e validare i valori, che nell'ambiente sono sempre testo.
    """

    # Legge anche un file .env nella cartella corrente, se presente
    # (utile fuori da Docker); le variabili d'ambiente hanno la precedenza.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["development", "production", "test"] = "development"

    # Database
    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # Autenticazione (usata nel modulo di sicurezza)
    jwt_secret: str = Field(min_length=32)
    jwt_expire_minutes: int = Field(default=60, gt=0)

    # Regole di prenotazione di default (sovrascrivibili per singolo evento)
    default_max_seats_per_booking: int = Field(default=6, gt=0)
    default_cancellation_deadline_hours: int = Field(default=24, ge=0)

    # Dati di esempio fittizi (app/seed.py), caricati all'avvio se il database
    # è vuoto. La password è comune a tutti gli account dimostrativi.
    seed_demo_data: bool = False
    seed_demo_password: str = Field(default="", max_length=72)

    @property
    def database_url(self) -> URL:
        """URL di connessione per SQLAlchemy con il driver psycopg 3.

        ``URL.create`` gestisce l'escape dei caratteri speciali nella password, cosa che una semplice concatenazione di stringhe non farebbe.
        """
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )

    @property
    def cookie_secure(self) -> bool:
        """Flag ``Secure`` del cookie: attivo solo in produzione (HTTPS)."""
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    """Restituisce sempre la stessa istanza di Settings.

    ``@lru_cache`` è un decoratore: avvolge la funzione e ne memorizza il risultato, quindi l'ambiente viene letto e validato una sola volta (simile a una variabile ``static`` in una funzione PHP).
    """
    return Settings()  # type: ignore[call-arg]  # i valori arrivano dall'ambiente
