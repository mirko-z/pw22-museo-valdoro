# Immagine del back-end FastAPI
# Versione esatta (Python 3.12.15 su Debian 13 "trixie"): stessa immagine anche a distanza di mesi
FROM python:3.12.15-slim-trixie

# Niente file .pyc nel container; log scritti subito (senza buffer) sull'output di Docker
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Prima le sole dipendenze: Docker riusa questo livello in cache finché
# requirements*.txt non cambiano, e le build successive sono più rapide.
COPY requirements.txt requirements-dev.txt ./
# Nel prototipo si installano anche le dipendenze di test, così i test girano
# nello stesso container dell'applicazione (docker compose run --rm api pytest).
ARG INSTALL_DEV=true
RUN if [ "$INSTALL_DEV" = "true" ]; then \
        pip install --no-cache-dir -r requirements-dev.txt; \
    else \
        pip install --no-cache-dir -r requirements.txt; \
    fi

COPY . .

# Il processo non gira come root (principio del minimo privilegio)
RUN useradd --create-home --uid 1000 app
USER app

EXPOSE 8000

# Migrazioni, seed e Uvicorn (vedi start.sh). Lo script si lancia con "sh"
# esplicito, così non serve il permesso di esecuzione (che si perde facilmente
# copiando il repository da Windows o da un archivio zip).
CMD ["sh", "start.sh"]
