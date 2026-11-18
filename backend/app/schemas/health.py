"""Schema della risposta dell'endpoint di salute."""

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Stato dell'API e della connessione al database.

    Le classi Pydantic descrivono la forma dei dati: FastAPI le usa per
    serializzare la risposta in JSON e per documentarla in OpenAPI.
    """

    status: Literal["ok", "degraded"]
    database: Literal["ok", "unreachable"]
