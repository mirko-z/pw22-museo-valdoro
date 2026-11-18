# Requisiti e casi d'uso – Museo Civico di Valdoro

Perimetro: ciclo di vita della prenotazione di un evento. I codici (RF, RNF, UC) sono presenti nei commenti del codice, nei test, negli scenari funzionali (`tools/scenari_funzionali.mjs`) e nella matrice di tracciabilità in fondo al documento.

## 1. Attori

| Attore | Descrizione |
|---|---|
| Ospite | Utente non autenticato: consulta gli eventi, si registra |
| Visitatore (`visitor`) | Utente registrato: prenota, annulla, lascia feedback |
| Staff (`staff`) | Operatore del museo: gestisce gli eventi, consulta partecipanti e dashboard |
| Admin (`admin`) | Staff con in più la gestione degli utenti e dei ruoli |

Generalizzazioni: Visitatore → Ospite (eredita la consultazione); Admin → Staff.

## 2. Requisiti funzionali

### Autenticazione e utenti
| Codice | Requisito |
|---|---|
| RF01 | L'ospite si registra con email (univoca), nome e password; il ruolo assegnato è `visitor` |
| RF02 | L'utente accede con email e password e riceve un token JWT a scadenza breve (60 minuti, configurabile con `JWT_EXPIRE_MINUTES`) |
| RF03 | L'utente può uscire (il cookie del token viene eliminato) |
| RF04 | Ogni operazione è autorizzata in base al ruolo; le richieste non autenticate ricevono 401, quelle non autorizzate 403 |
| RF05 | L'admin consulta l'elenco degli utenti |
| RF06 | L'admin modifica il ruolo di un utente |

### Eventi
| Codice | Requisito |
|---|---|
| RF07 | Chiunque consulta gli eventi programmati futuri, compresi quelli esauriti, con il numero di posti disponibili |
| RF08 | Lo staff crea, modifica ed elimina gli eventi (titolo, descrizione, tipo, inizio, fine, capienza, prezzo) |
| RF09 | Per ogni evento lo staff può indicare il massimo di posti per prenotazione e il termine di annullamento; se non li indica valgono i default di configurazione |
| RF10 | Lo staff annulla un evento; le prenotazioni confermate passano automaticamente a `cancelled` |

### Prenotazioni
| Codice | Requisito |
|---|---|
| RF11 | Il visitatore prenota N posti per un evento programmato non ancora iniziato, se N rispetta il massimo per prenotazione e i posti disponibili sono sufficienti |
| RF12 | Ogni prenotazione riceve un codice univoco e non sequenziale |
| RF13 | Ogni utente può avere una sola prenotazione confermata per evento |
| RF14 | Il visitatore annulla la propria prenotazione entro il termine di annullamento dell'evento |
| RF15 | Il visitatore consulta le proprie prenotazioni |
| RF16 | Lo staff consulta l'elenco dei partecipanti di un evento |

### Feedback
| Codice | Requisito |
|---|---|
| RF17 | Il visitatore lascia un feedback (voto 1–5, commento facoltativo) solo per un evento concluso, non annullato, per cui ha una prenotazione confermata; uno per evento |
| RF18 | Lo staff consulta i feedback di un evento |

### Dashboard
| Codice | Requisito |
|---|---|
| RF19 | Prenotazioni per evento e tasso di riempimento (posti confermati / capienza) |
| RF20 | Tasso di annullamento (prenotazioni annullate / totali) |
| RF21 | Voto medio per evento e per tipo di evento, con il numero di feedback ricevuti e la copertura del feedback (feedback / prenotazioni confermate di eventi conclusi) |
| RF22 | Andamento delle prenotazioni per settimana |

Regole di calcolo comuni: gli eventi annullati dal museo sono esclusi dagli aggregati, perché falserebbero K5 e K6; il riempimento medio e la copertura del feedback si calcolano solo sugli eventi conclusi; un rapporto con denominatore zero è "non calcolabile" (`null`), non 0; l'andamento settimanale conta tutte le prenotazioni create, anche quelle poi annullate.

## 3. Requisiti non funzionali

| Codice | Categoria | Requisito |
|---|---|---|
| RNF01 | Correttezza in concorrenza | Nessun overbooking con richieste simultanee: transazione e `SELECT ... FOR UPDATE` sulla riga dell'evento |
| RNF02 | Integrità dei dati | Vincoli nel database: CHECK, chiavi esterne, indice univoco parziale sulle prenotazioni attive |
| RNF03 | Sicurezza | Password con hash bcrypt (massimo 72 byte); JWT firmato con PyJWT, scadenza 60 minuti |
| RNF04 | Sicurezza | Token in cookie `HttpOnly`, `SameSite=Strict`, `Secure` in produzione; header `Bearer` accettato per Swagger e test |
| RNF05 | Sicurezza | Front-end e API sulla stessa origine tramite nginx; CORS disattivato |
| RNF06 | Protezione dei dati | Dati personali minimi (email, nome); nessun dato non necessario alla finalità |
| RNF07 | Prestazioni | Latenza e throughput della prenotazione misurati sotto carico concorrente (esperimento) |
| RNF08 | Manutenibilità | Architettura a livelli router → service → modelli; nessuna logica di business nei router |
| RNF09 | Portabilità | Avvio completo con Docker Compose; configurazione da `.env` |
| RNF10 | Documentazione | API documentate in OpenAPI (Swagger su `/api/docs`) |
| RNF11 | Testabilità | Test automatici su database PostgreSQL separato |
| RNF12 | Localizzazione | Date in `timestamptz` (UTC nel database, sessione impostata a UTC dall'applicazione, Europe/Rome nell'interfaccia); interfaccia in italiano |

## 4. Casi d'uso

Diagramma: `docs/diagrammi/casi-uso.puml`.

| Codice | Caso d'uso | Attore | Requisiti |
|---|---|---|---|
| UC01 | Registrarsi | Ospite | RF01 |
| UC02 | Accedere / uscire | Visitatore, Staff | RF02, RF03 |
| UC03 | Consultare gli eventi | Ospite | RF07 |
| UC04 | Prenotare un evento | Visitatore | RF11, RF12, RF13 |
| UC05 | Annullare una prenotazione | Visitatore | RF14 |
| UC06 | Consultare le proprie prenotazioni | Visitatore | RF15 |
| UC07 | Lasciare un feedback | Visitatore | RF17 |
| UC08 | Gestire gli eventi e le regole | Staff | RF08, RF09 |
| UC09 | Annullare un evento | Staff | RF10 |
| UC10 | Consultare partecipanti e feedback | Staff | RF16, RF18 |
| UC11 | Consultare la dashboard | Staff | RF19–RF22 |
| UC12 | Gestire i ruoli degli utenti | Admin | RF05, RF06 |

### Scenario dettagliato – UC04 Prenotare un evento
È il caso d'uso critico: l'unico in cui più utenti competono per la stessa risorsa. Il diagramma `docs/diagrammi/sequenza-prenotazione.puml` mostra lo stesso scenario con due richieste concorrenti.

- **Attore**: Visitatore autenticato.
- **Precondizioni**: l'evento è `scheduled` e non è ancora iniziato.
- **Flusso principale**:
  1. Il visitatore seleziona l'evento e indica il numero di posti N.
  2. Il sistema apre una transazione e blocca la riga dell'evento.
  3. Il sistema verifica che N non superi il massimo per prenotazione.
  4. Il sistema verifica che il visitatore non abbia già una prenotazione confermata per l'evento.
  5. Il sistema calcola i posti disponibili (capienza − posti confermati) e verifica che siano almeno N.
  6. Il sistema registra la prenotazione `confirmed` con un codice generato casualmente ed esegue il commit.
  7. Il visitatore riceve la conferma con il codice.
- **Flussi alternativi**:
  - 3a. N supera il massimo: rifiuto (422) con il limite consentito.
  - 4a. Prenotazione già presente: rifiuto (409); il visitatore deve annullare e riprenotare.
  - 5a. Posti insufficienti: rifiuto (409) con i posti residui.
  - P1. Evento annullato, già iniziato o inesistente: rifiuto (404 o 409).
  - In tutti i casi di rifiuto la transazione viene annullata (rollback) e il lock rilasciato.
- **Postcondizione**: i posti confermati non superano mai la capienza.

## 5. Matrice di tracciabilità

Ogni obiettivo del progetto è collegato ai requisiti, ai componenti che li realizzano e ai test che li verificano (cartella `backend/tests/`).

| Obiettivo | Requisiti | Componente | Verifica |
|---|---|---|---|
| O1 Nessun overbooking | RF11, RNF01 | `BookingService` + `LockingBookingStrategy` | `test_nessun_overbooking_con_richieste_simultanee` (10 thread; xfail stretto con `NaiveBookingStrategy`); esperimento N = 10/50/100 e scenario K = 100 |
| O2 Nessuna prenotazione duplicata | RF13, RNF02 | Indice univoco parziale `uq_bookings_active` | `test_una_sola_prenotazione_attiva_poi_riprenotazione` (API, 409 `ALREADY_BOOKED`); `test_una_sola_prenotazione_attiva_per_utente_ed_evento` (database) |
| O3 Self-service | RF11, RF14, RF15 | API `/api/bookings` + pagine `eventi.html` e `prenotazioni.html` | Scenari d'uso S04, S06, S07 (`tools/scenari_funzionali.mjs`); `test_annullamento_entro_il_termine`, `test_le_mie_prenotazioni`; latenza p95 misurata nell'esperimento |
| O4 Regole configurabili | RF09, RF11, RF14 | `Settings` + colonne `max_seats_per_booking` e `cancellation_deadline_hours` su `events` | `test_regole_omesse_prendono_i_default`, `test_regole_indicate_sovrascrivono_i_default`, `test_massimo_posti_per_prenotazione`, `test_annullamento_oltre_il_termine` |
| O5 Feedback affidabile | RF17, RF21 | `FeedbackService`, `DashboardService` | `test_feedback.py`: evento non concluso, annullato, senza prenotazione confermata, doppio feedback, voto fuori intervallo; K7 in `test_indicatori_complessivi` e `test_indicatori_per_evento` su dataset calcolato a mano |
| O6 Indicatori automatici | RF19–RF22 | `DashboardService` + pagina `staff/dashboard.html` | `test_dashboard.py`: valori uguali a quelli calcolati a mano (complessivi, per evento, per tipo, settimanali) |
| O7 Sicurezza e dati personali | RF04, RNF03–RNF06 | `core/security.py` + `core/deps.py` | `test_auth.py` (401/403, cookie HttpOnly e SameSite, ruolo riletto dal database), `test_security.py` (hash bcrypt), `test_dashboard_riservata_allo_staff` |
