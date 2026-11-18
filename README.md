# Museo Civico di Valdoro – Piattaforma di prenotazione

Project work PW22 – Corso di laurea in Informatica per le Aziende Digitali (L-31), Università Telematica Pegaso.

*Prevenire l'overbooking: progettazione di una piattaforma web per un museo e analisi sperimentale del controllo della concorrenza*

Prototipo di piattaforma web che digitalizza il ciclo di vita della prenotazione di un evento in un museo. Contiene: pubblicazione dell'evento, prenotazione sicura in concorrenza, annullamento, feedback, indicatori per la direzione.

## Architettura
| Servizio | Tecnologia | Ruolo |
|---|---|---|
| `web` | nginx 1.30.6 | Front-end statico (HTML, CSS, JavaScript) e reverse proxy verso `/api/` |
| `api` | Python 3.12.15, FastAPI, SQLAlchemy 2, Pydantic 2 | API REST e logica di business |
| `db` | PostgreSQL 16.15 | Dati persistenti, transazioni, vincoli, lock di riga |

## Avvio
Requisiti: Docker con Docker Compose.

```bash
cp .env.example .env        # modificare POSTGRES_PASSWORD e JWT_SECRET
docker compose up --build
```

- Applicazione: http://localhost:8080
- Documentazione delle API (Swagger): http://localhost:8080/api/docs
- Stato del servizio: http://localhost:8080/api/health

All'avvio il container `api` applica le migrazioni (`alembic upgrade head`) e, se il database è vuoto e `SEED_DEMO_DATA=true`, carica i dati di esempio fittizi.

Per fermare: `docker compose down`. I dati restano nel volume `pgdata`; `docker compose down -v` li elimina.

### Pagine
| Pagina | Percorso | Ruolo |
|---|---|---|
| Home | `/` | pubblico |
| Eventi e prenotazione | `/pages/eventi.html` | pubblico (prenotazione: visitor) |
| Accesso e registrazione | `/pages/accesso.html` | pubblico |
| Le mie prenotazioni (annullamento, feedback) | `/pages/prenotazioni.html` | visitor |
| Dashboard | `/pages/staff/dashboard.html` | staff, admin |
| Gestione eventi | `/pages/staff/eventi.html` | staff, admin |
| Partecipanti e feedback | `/pages/staff/evento.html?id=…` | staff, admin |

La gestione degli utenti (solo admin) è disponibile da Swagger: `/api/docs`.

### Account dimostrativi
Tutti con la password indicata in `SEED_DEMO_PASSWORD` (`.env`). Dati inventati, domini riservati `example.com` / `.example` (RFC 2606).

| Ruolo | Email |
|---|---|
| admin | `admin@museovaldoro.example` |
| staff | `staff@museovaldoro.example` |
| visitor (insegnante) | `paola.ferrante@example.com` |
| visitor | `marco.bianchi@example.com` |

Il seed crea 24 eventi con date relative al giorno di avvio. 7 daranno conclusi (con prenotazioni e feedback, uno annullato dal museo) e 17 futuri distribuiti su circa sei mesi. le prenotazioni calano con la distanza (uno esaurito, uno con meno posti liberi del massimo per prenotazione, alcuni sono senza prenotazioni). Ogni evento cade su un giorno della settimana fisso: laboratori scolastici al mattino nei giorni feriali, conferenze la sera, visite e attività per famiglie nel fine settimana.

## Database e migrazioni
Lo schema è definito dai modelli contenuti in `backend/app/models/` e creato dalle migrazioni in `backend/alembic/versions/`.

```bash
docker compose exec api alembic current              # versione applicata
docker compose exec api alembic upgrade head --sql   # DDL generato, senza eseguirlo
docker compose exec db psql -U museo -d museo        # console SQL (\d bookings, ecc.)
```

## Test
```bash
docker compose run --rm api pytest
```

I test usano un database PostgreSQL separato (`<POSTGRES_DB>_test`, oppure `TEST_POSTGRES_DB`), creato automaticamente se manca. Lo schema viene ricreato con le migrazioni a ogni esecuzione e le tabelle vengono svuotate dopo ogni test.

## Esperimento sulla concorrenza
Confronta la strategia di prenotazione con lock (`SELECT ... FOR UPDATE`, usata dall'applicazione) con quella senza lock, su un database dedicato (`<POSTGRES_DB>_experiment`). Con lo stack avviato:

```bash
# N = 10, 50, 100 richieste simultanee sugli ultimi 2 posti, 10 ripetizioni (circa 1 minuto)
docker compose run --rm -v "$PWD/docs/risultati:/app/results" api python -m experiments.concurrency --out results
# Scenario di controllo: N = 100, K = 100 (tutte le richieste possono riuscire; misura il costo del lock)
docker compose run --rm -v "$PWD/docs/risultati:/app/results" api python -m experiments.concurrency --n 100 --seats-left 100 --out results/scenario-k100
# Grafico per il report (PNG 300 dpi e SVG)
docker compose run --rm -v "$PWD/docs/risultati:/app/results" api python -m experiments.plot_results --dir results
```

Output in `docs/risultati/`: `esperimento_ripetizioni.csv` (una riga per ripetizione), `esperimento_sintesi.csv` (media e deviazione standard), `esperimento_ambiente.txt`, `esperimento_grafico.png` e `esperimento_grafico.svg`; lo scenario di controllo in `docs/risultati/scenario-k100/`.

## Struttura del repository
```
backend/    applicazione FastAPI (app/), test (tests/), esperimento (experiments/)
frontend/   pagine statiche e configurazione di nginx
docs/       diagrammi UML ed E-R (PlantUML, diagrammi/) e risultati dell'esperimento (risultati/)
tools/      scenari funzionali end-to-end con Playwright
```

## Componenti di terze parti nel front-end
Serviti in locale (per la Content Security Policy):
- Bootstrap 5.3.8, solo CSS, per l'area staff – licenza MIT (`frontend/css/vendor/bootstrap.min.css`)
- Source Serif 4 (Adobe), titoli dell'area pubblica – SIL Open Font License 1.1 (`frontend/css/fonts/`)
- Immagine dell'hero (`frontend/img/hero.jpeg`): image by [1tamara2](https://pixabay.com/users/1tamara2-15516491/) from [Pixabay](https://pixabay.com/) (immagine 8797936) – Pixabay Content License, ricompressa per il web
