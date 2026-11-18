#!/bin/sh
# Avvio del container "api": migrazioni, dati di esempio, server applicativo.
# set -e: se un comando fallisce lo script si ferma e il container non parte
# con uno schema del database non aggiornato.
set -e

echo "Migrazioni del database (alembic upgrade head)..."
alembic upgrade head

# Carica i dati fittizi solo se SEED_DEMO_DATA=true e il database è vuoto
python -m app.seed --if-enabled

# exec sostituisce la shell con Uvicorn: i segnali di Docker (SIGTERM su
# "docker compose down") arrivano direttamente al server, che si chiude in modo pulito.
# --proxy-headers: Uvicorn legge X-Forwarded-For/Proto impostati da nginx.
# --workers: numero di processi (API_WORKERS nel .env), uno per core disponibile.
exec uvicorn app.main:app \
    --host 0.0.0.0 --port 8000 \
    --workers "${API_WORKERS:-1}" \
    --proxy-headers --forwarded-allow-ips='*'
