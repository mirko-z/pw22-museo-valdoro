"""Endpoint di salute, usato dall'healthcheck di Docker (RNF09)."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.health import HealthResponse

router = APIRouter(prefix="/api", tags=["sistema"])


# Il decoratore @router.get registra la funzione come gestore di GET /api/health
# (l'equivalente di una rotta in un router PHP), con lo schema della risposta.
@router.get(
    "/health",
    response_model=HealthResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": HealthResponse}},
    summary="Stato dell'API e del database",
)
def health(db: Annotated[Session, Depends(get_db)]) -> HealthResponse | JSONResponse:
    """Esegue ``SELECT 1``: 200 se il database risponde, 503 altrimenti.

    ``Annotated[Session, Depends(get_db)]`` dice a FastAPI: "questo parametro è
    una Session e ottienila chiamando get_db". Il router non apre connessioni
    da solo e nei test la dipendenza può essere sostituita.
    """
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        body = HealthResponse(status="degraded", database="unreachable")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=body.model_dump(),
        )
    return HealthResponse(status="ok", database="ok")
