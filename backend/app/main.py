"""Punto di ingresso dell'applicazione FastAPI."""

from fastapi import FastAPI

from app.core.errors import register_error_handlers
from app.routers import auth, bookings, dashboard, events, feedback, health, users


def create_app() -> FastAPI:
    """Crea e configura l'applicazione.

    Tutte le rotte stanno sotto /api, compresa la documentazione: nginx
    inoltra al back-end solo /api/, il resto è il front-end statico.
    CORS non è configurato di proposito: browser e API hanno la stessa
    origine grazie a nginx, quindi le richieste cross-origin non servono.
    """
    app = FastAPI(
        title="Museo Civico di Valdoro – API",
        version="0.2.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(events.router)
    app.include_router(bookings.router)
    app.include_router(feedback.router)
    app.include_router(dashboard.router)
    return app


app = create_app()
