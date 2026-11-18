// Scenari d'uso eseguiti nel browser (test funzionali end-to-end) con screenshot.
//
// Ogni scenario segue un caso d'uso (UC01–UC12): esegue i passi come farebbe un
// utente, verifica l'esito atteso e salva gli screenshot in docs/screenshot/.
// L'esito di ogni scenario è stampato a console.
//
// Precondizione: stack avviato con un database appena creato, così i dati di
// esempio sono quelli del seed (docker compose down -v && docker compose up -d --build).
// Gli scenari modificano i dati (registrano un utente, prenotano, annullano un evento):
// per ripeterli si ricrea il database.
//
// Esecuzione (facoltativa, richiede Node.js 20+; Playwright si installa a parte):
//   npm install --no-save playwright@1.56.1 && npx playwright install chromium
//   node tools/scenari_funzionali.mjs [http://localhost:8080] [docs/screenshot]

import { chromium } from 'playwright';
import { mkdirSync } from 'node:fs';

const BASE = process.argv[2] || 'http://localhost:8080';
const OUT = process.argv[3] || 'docs/screenshot';
const PASSWORD = 'Valdoro-Demo-2026';          // SEED_DEMO_PASSWORD di .env.example
const STAFF = 'staff@museovaldoro.example';
const ADMIN = 'admin@museovaldoro.example';
const FEEDBACK_CANDIDATES = ['elena.russo@example.com', 'nicola.testa@example.com', 'giorgia.costa@example.com',
  'davide.greco@example.com', 'valentina.mancini@example.com', 'simone.conti@example.com'];
const NEW_USER = { name: 'Mario Rossi', email: `mario.rossi.${Date.now()}@example.com`, password: 'Prova-Valdoro-1' };
const NEW_EVENT = 'Visita guidata ai depositi del museo';

mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch();
const results = [];
let current = null;

// --- Utilità -------------------------------------------------------------------

async function context(viewport = { width: 1280, height: 800 }) {
  // Fuso e lingua come per un visitatore italiano; deviceScaleFactor 1.5 per immagini nitide nel PDF
  const ctx = await browser.newContext({ viewport, deviceScaleFactor: 1.5, timezoneId: 'Europe/Rome', locale: 'it-IT' });
  const page = await ctx.newPage();
  page.jsErrors = [];
  page.on('pageerror', (e) => page.jsErrors.push(e.message));
  page.on('console', (m) => {
    // 4xx attesi (401 di /auth/me per l'ospite, rifiuti verificati dagli scenari) esclusi
    if (m.type() === 'error' && !/status of 4\d\d/.test(m.text())) page.jsErrors.push(m.text());
  });
  page.on('dialog', (d) => d.accept()); // conferme di annullamento
  return [ctx, page];
}

async function scenario(id, uc, title, fn) {
  current = { id, uc, title, checks: [], shots: [] };
  try {
    await fn();
  } catch (error) {
    current.checks.push({ ok: false, text: `eccezione: ${error.message.split('\n')[0]}` });
  }
  current.ok = current.checks.length > 0 && current.checks.every((c) => c.ok);
  results.push(current);
  console.log(`${current.ok ? 'SUPERATO' : 'FALLITO '} ${id} [${uc}] ${title}`);
  for (const c of current.checks) console.log(`   ${c.ok ? '✓' : '✗'} ${c.text}`);
}

function check(ok, text) { current.checks.push({ ok: Boolean(ok), text }); }

async function shot(page, name, options = {}) {
  const path = `${OUT}/${name}.png`;
  await page.waitForTimeout(250);
  await page.screenshot({ path, ...options });
  current.shots.push(path);
}

async function login(page, email, password = PASSWORD) {
  await page.goto(`${BASE}/pages/accesso.html`);
  await page.fill('#login-email', email);
  await page.fill('#login-password', password);
  await page.click('[data-login-form] button[type=submit]');
}

const messageText = async (page) => (await page.locator('[data-message]').textContent()).trim();

// Data e ora locale (Europe/Rome) tra N giorni alle 17:00, nel formato di <input type="datetime-local">
function localInput(days, hour) {
  const d = new Date(Date.now() + days * 864e5);
  const ymd = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Rome' }).format(d);
  return `${ymd}T${String(hour).padStart(2, '0')}:00`;
}

// --- Scenari ---------------------------------------------------------------------

const [guestCtx, guest] = await context();
const [userCtx, user] = await context();

await scenario('S01', 'UC01', 'Registrazione di un nuovo visitatore', async () => {
  await user.goto(`${BASE}/pages/accesso.html`);
  await user.fill('#reg-name', NEW_USER.name);
  await user.fill('#reg-email', NEW_USER.email);
  await user.fill('#reg-password', NEW_USER.password);
  await shot(user, 'S01-registrazione');
  await user.click('[data-register-form] button[type=submit]');
  await user.waitForURL('**/pages/prenotazioni.html');
  await user.waitForSelector('[data-message] .message');
  check(true, 'dopo la registrazione l\'utente è collegato e arriva su "Le mie prenotazioni"');
  check((await messageText(user)).includes('Non hai ancora prenotazioni'), 'elenco vuoto con invito a consultare gli eventi');
  check((await user.locator('[data-user-area]').textContent()).includes(NEW_USER.name), 'nome dell\'utente nell\'intestazione');
});

await scenario('S02', 'UC02', 'Accesso con password errata, uscita e nuovo accesso', async () => {
  await user.click('[data-user-area] button:has-text("Esci")');
  await user.waitForURL(`${BASE}/`);
  check(await user.locator('[data-user-area] a:has-text("Accedi")').count() === 1, 'dopo l\'uscita compare di nuovo "Accedi"');
  await login(user, NEW_USER.email, 'password-sbagliata');
  await user.waitForSelector('[data-login-message] .message--error');
  const text = (await user.locator('[data-login-message]').textContent()).trim();
  check(text === 'Email o password non corretti.', `messaggio generico, senza dire quale dato è errato: "${text}"`);
  await shot(user, 'S02-accesso-errato');
  await login(user, NEW_USER.email, NEW_USER.password);
  await user.waitForURL('**/pages/prenotazioni.html');
  check(true, 'con la password corretta l\'accesso riesce');
});

await scenario('S03', 'UC03', 'Consultazione del programma da parte di un ospite', async () => {
  await guest.goto(`${BASE}/`);
  await guest.waitForSelector('[data-upcoming] .card');
  check(await guest.locator('[data-upcoming] .card').count() === 6, 'la home mostra i prossimi 6 eventi');
  await shot(guest, 'S03-home');
  await guest.goto(`${BASE}/pages/eventi.html`);
  await guest.waitForSelector('[data-events] .card');
  const soldOut = guest.locator('.card', { hasText: 'Esaurito' });
  check(await soldOut.count() >= 1, 'gli eventi esauriti restano visibili con la scritta "Esaurito" (RF07)');
  check(await guest.locator('.card a:has-text("Accedi per prenotare")').count() > 0, 'l\'ospite vede "Accedi per prenotare" invece del modulo');
  await shot(guest, 'S03-eventi');
  await guest.locator('.chip', { hasText: 'Laboratori' }).click();
  await guest.waitForTimeout(500);
  const types = await guest.locator('.card__type').allTextContents();
  check(types.length > 0 && types.every((t) => t === 'Laboratorio'), `filtro per tipo: ${types.length} laboratori, nessun altro tipo`);
});

let bookedCode = null;
let bookedTitle = null;
await scenario('S04', 'UC04', 'Prenotazione di un evento (flusso principale)', async () => {
  await user.goto(`${BASE}/pages/eventi.html`);
  await user.waitForSelector('.card form');
  // quarta scheda prenotabile: evento abbastanza lontano da restare annullabile in S06
  const card = user.locator('.card:has(form)').nth(3);
  bookedTitle = (await card.locator('.card__title').textContent()).trim();
  await card.locator('input').fill('2');
  await card.locator('button[type=submit]').click();
  await user.waitForSelector('[data-message] .message--success');
  bookedCode = (await user.locator('[data-message] .booking-code').textContent()).trim();
  check(/^[A-Z0-9]{10}$/.test(bookedCode), `conferma immediata con codice di prenotazione ${bookedCode} (RF12)`);
  await user.locator('[data-message]').scrollIntoViewIfNeeded();
  await user.evaluate(() => window.scrollBy(0, -120));
  await shot(user, 'S04-prenotazione-confermata');
});

await scenario('S05', 'UC04', 'Prenotazione rifiutata: flussi alternativi 3a, 4a, 5a', async () => {
  // 4a – seconda prenotazione per lo stesso evento
  const same = user.locator('.card', { hasText: bookedTitle }).first();
  await same.locator('button[type=submit]').click();
  await user.waitForSelector('[data-message] .message--error');
  let text = await messageText(user);
  check(text.startsWith('Hai già una prenotazione per questo evento'), `4a, prenotazione duplicata (409): "${text}"`);
  await shot(user, 'S05-prenotazione-duplicata');
  // 3a – più posti del massimo per prenotazione (si toglie il limite dell'interfaccia: decide il server)
  const ruled = user.locator('.card:has(form)', { hasText: 'per prenotazione.' }).nth(1);
  const max = Number((await ruled.locator('.book-form__hint').textContent()).match(/Fino a (\d+)/)[1]);
  await ruled.locator('input').evaluate((i) => i.removeAttribute('max'));
  await ruled.locator('input').fill(String(max + 1));
  await ruled.locator('button[type=submit]').click();
  await user.waitForFunction(() => document.querySelector('[data-message] .message--error')?.textContent.includes('al massimo'));
  text = await messageText(user);
  check(text === `Si possono prenotare al massimo ${max} posti.`, `3a, oltre il massimo per prenotazione (422): "${text}"`);
  // 5a – più posti di quelli liberi
  const few = user.locator('.card:has(form)', { hasText: 'tutti quelli ancora liberi' }).first();
  const free = Number((await few.locator('.book-form__hint').textContent()).match(/fino a (\d+)/)[1]);
  await few.locator('input').evaluate((i) => i.removeAttribute('max'));
  await few.locator('input').fill(String(free + 1));
  await few.locator('button[type=submit]').click();
  await user.waitForFunction(() => document.querySelector('[data-message] .message--error')?.textContent.includes('restano'));
  text = await messageText(user);
  check(text.includes(`ne restano ${free}`), `5a, posti insufficienti (409): "${text}"`);
});

await scenario('S06', 'UC06', 'Consultazione delle proprie prenotazioni', async () => {
  await user.goto(`${BASE}/pages/prenotazioni.html`);
  await user.waitForSelector('.bookings-section');
  const card = user.locator('.card', { hasText: bookedCode });
  check(await card.count() === 1, `la prenotazione ${bookedCode} è tra le "Prossime"`);
  check((await card.textContent()).includes('Confermata'), 'stato "Confermata", con posti, orario e termine di annullamento');
  await shot(user, 'S06-le-mie-prenotazioni');
});

await scenario('S07', 'UC05', 'Annullamento di una prenotazione entro il termine', async () => {
  const card = user.locator('.card', { hasText: bookedCode });
  await card.locator('button:has-text("Annulla prenotazione")').click();
  await user.waitForSelector('[data-message] .message--success');
  check((await messageText(user)) === 'Prenotazione annullata.', 'conferma dell\'annullamento');
  const moved = user.locator('.bookings-section', { hasText: 'Passate e annullate' }).locator('.card', { hasText: bookedCode });
  check((await moved.textContent()).includes('Prenotazione annullata'), 'la prenotazione passa tra "Passate e annullate"');
  await shot(user, 'S07-annullamento');
});

let feedbackEvent = null;
await scenario('S08', 'UC07', 'Feedback su un evento concluso', async () => {
  const [ctx, page] = await context();
  let found = false;
  for (const email of FEEDBACK_CANDIDATES) {
    await login(page, email);
    await page.waitForURL('**/pages/prenotazioni.html');
    await page.waitForSelector('.bookings-section');
    if (await page.locator('form.feedback').count() > 0) { found = true; break; }
    await page.click('[data-user-area] button:has-text("Esci")');
    await page.waitForURL(`${BASE}/`);
  }
  check(found, 'trovato un visitatore con un evento concluso ancora senza feedback');
  const card = page.locator('.card:has(form.feedback)').first();
  feedbackEvent = (await card.locator('.card__title').textContent()).trim();
  await card.locator('select').selectOption('5');
  await card.locator('textarea').fill('Visita molto curata, guida preparata e disponibile.');
  await card.scrollIntoViewIfNeeded();
  await shot(page, 'S08-feedback');
  await card.locator('form.feedback button[type=submit]').click();
  await page.waitForSelector('[data-message] .message--success');
  check((await messageText(page)) === 'Grazie per il tuo feedback!', 'feedback registrato');
  const after = page.locator('.card', { hasText: feedbackEvent }).first();
  check((await after.textContent()).includes('Il tuo voto5 su 5') && await after.locator('form').count() === 0,
    'la scheda mostra il voto e il modulo non compare più (un solo feedback per evento)');
  await ctx.close();
});

await scenario('S09', 'RF04', 'Pagine riservate: ospite e visitatore', async () => {
  const [ctx, page] = await context();
  await page.goto(`${BASE}/pages/prenotazioni.html`);
  await page.waitForURL('**/pages/accesso.html?next=*');
  check(page.url().includes('next=%2Fpages%2Fprenotazioni.html'), 'l\'ospite viene mandato all\'accesso, con ritorno alla pagina richiesta');
  await ctx.close();
  await user.goto(`${BASE}/pages/staff/dashboard.html`);
  await user.waitForSelector('main .message--error');
  const text = (await user.locator('main').textContent()).trim();
  check(text.includes('riservata allo staff'), `il visitatore non vede la dashboard: "${text}"`);
  const status = await user.evaluate(async () => (await fetch('/api/dashboard/overview')).status);
  check(status === 403, `anche chiamando l'API direttamente il server risponde ${status} (autorizzazione nel back-end)`);
  await shot(user, 'S09-accesso-negato');
});

const [staffCtx, staff] = await context();
await scenario('S10', 'UC08', 'Creazione e modifica di un evento con regole proprie', async () => {
  await login(staff, STAFF);
  await staff.waitForURL('**/pages/staff/dashboard.html');
  await staff.goto(`${BASE}/pages/staff/eventi.html`);
  await staff.waitForSelector('[data-events] tr');
  const f = (n) => staff.locator(`[data-event-form] [name=${n}]`);
  await f('title').fill(NEW_EVENT);
  await f('type').selectOption('guided_tour');
  await f('description').fill('Percorso straordinario nei depositi, a gruppi ridotti.');
  await f('start_at').fill(localInput(20, 17));
  await f('end_at').fill(localInput(20, 18));
  await f('capacity').fill('12');
  await f('price').fill('6');
  await f('max_seats_per_booking').fill('2');
  await f('cancellation_deadline_hours').fill('48');
  await staff.locator('[data-event-form]').scrollIntoViewIfNeeded();
  await shot(staff, 'S10-nuovo-evento');
  await staff.click('[data-event-form] button[type=submit]');
  await staff.waitForFunction(() => document.querySelector('[data-message]')?.textContent.includes('salvato'));
  const row = staff.locator('tr', { hasText: NEW_EVENT });
  const day = localInput(20, 17).slice(0, 10).split('-');
  check((await row.textContent()).includes(`${day[2]}/${day[1]} 17:00`), 'evento in elenco con data e ora inserite (17:00, ora di Roma)');
  // modifica: la capienza cambia, l'orario resta lo stesso
  await row.locator('button:has-text("Modifica")').click();
  await staff.waitForFunction(() => document.querySelector('[data-form-title]').textContent.startsWith('Modifica'));
  check((await f('start_at').inputValue()) === localInput(20, 17), 'il modulo di modifica rilegge l\'orario senza spostamenti di fuso');
  await f('capacity').fill('15');
  await staff.click('[data-event-form] button[type=submit]');
  // il messaggio "salvato" della creazione è ancora a schermo: si attende che la riga mostri la nuova capienza
  const updated = await staff.locator('tr', { hasText: NEW_EVENT }).filter({ hasText: '0/15' })
    .waitFor({ timeout: 5000 }).then(() => true, () => false);
  check(updated, 'modifica salvata: capienza 15');
  // le regole valgono sul sito pubblico (RF09)
  await user.goto(`${BASE}/pages/eventi.html`);
  const card = user.locator('.card', { hasText: NEW_EVENT });
  await card.waitFor();
  const text = await card.textContent();
  check(text.includes('Fino a 2 posti per prenotazione') && text.includes('fino a 2 giorni prima'),
    'sul sito pubblico: massimo 2 posti per prenotazione, annullamento fino a 2 giorni prima');
  await card.locator('input').fill('2');
  await card.locator('button[type=submit]').click();
  await user.waitForSelector('[data-message] .message--success');
  check(true, 'il visitatore prenota 2 posti per il nuovo evento');
  await card.scrollIntoViewIfNeeded();
  await shot(user, 'S10-evento-sul-sito');
});

await scenario('S11', 'UC10', 'Partecipanti e feedback di un evento', async () => {
  await staff.goto(`${BASE}/pages/staff/eventi.html`);
  await staff.waitForSelector('[data-events] tr');
  // più eventi possono avere lo stesso titolo (date diverse): si aprono quelli conclusi finché non compare il feedback di S08
  const rows = staff.locator('tr', { hasText: feedbackEvent }).filter({ hasText: 'concluso' });
  const links = await rows.locator('a:has-text("Partecipanti")').evaluateAll((as) => as.map((a) => a.href));
  let seen = false;
  for (const href of links) {
    await staff.goto(href);
    await staff.waitForSelector('[data-participants] tr');
    await staff.waitForLoadState('networkidle');
    if ((await staff.locator('[data-feedback]').textContent()).includes('Visita molto curata')) { seen = true; break; }
  }
  check(await staff.locator('[data-participants] tr td:nth-child(4)').count() > 0, 'elenco dei partecipanti con posti e codice');
  check(seen, 'il feedback lasciato in S08 è visibile allo staff');
  await shot(staff, 'S11-partecipanti-feedback', { fullPage: true });
});

await scenario('S12', 'UC09', 'Annullamento di un evento da parte del museo', async () => {
  await staff.goto(`${BASE}/pages/staff/eventi.html`);
  const row = staff.locator('tr', { hasText: NEW_EVENT });
  await row.locator('button:text-is("Annulla")').click();
  await staff.waitForFunction(() => document.querySelector('[data-message]')?.textContent.includes('annullato'));
  // il messaggio compare prima che l'elenco sia ricaricato: si attende la riga aggiornata
  const cancelled = await staff.locator('tr', { hasText: NEW_EVENT }).filter({ hasText: 'annullato' })
    .waitFor({ timeout: 5000 }).then(() => true, () => false);
  check(cancelled, 'stato dell\'evento: annullato');
  await shot(staff, 'S12-evento-annullato-staff');
  await user.goto(`${BASE}/pages/prenotazioni.html`);
  const card = user.locator('.card', { hasText: NEW_EVENT });
  await card.waitFor();
  check((await card.textContent()).includes('Evento annullato dal museo'), 'il visitatore vede la prenotazione annullata dal museo (RF10)');
  await user.goto(`${BASE}/pages/eventi.html`);
  await user.waitForSelector('[data-events] .card');
  check(await user.locator('.card', { hasText: NEW_EVENT }).count() === 0, 'l\'evento annullato esce dal programma pubblico');
});

await scenario('S13', 'UC11', 'Dashboard degli indicatori', async () => {
  await staff.goto(`${BASE}/pages/staff/dashboard.html`);
  await staff.waitForLoadState('networkidle');
  check(await staff.locator('table tbody tr').count() > 0, 'indicatori complessivi, per evento, per tipo e andamento settimanale');
  await shot(staff, 'S13-dashboard');
});

await scenario('S14', 'UC12', 'Gestione dei ruoli da parte dell\'admin (solo API)', async () => {
  const api = await browser.newContext().then((c) => c.request);
  const token = async (email, password = PASSWORD) =>
    (await (await api.post(`${BASE}/api/auth/login`, { form: { username: email, password } })).json()).access_token;
  const admin = { Authorization: `Bearer ${await token(ADMIN)}` };
  const users = await (await api.get(`${BASE}/api/users`, { headers: admin })).json();
  check(Array.isArray(users) && users.length > 0, `GET /api/users: elenco di ${users.length} utenti`);
  const mario = users.find((u) => u.email === NEW_USER.email);
  const me = users.find((u) => u.email === ADMIN);
  let r = await api.patch(`${BASE}/api/users/${mario.id}/role`, { headers: admin, data: { role: 'staff' } });
  check(r.status() === 200, `PATCH ruolo di ${NEW_USER.name} a staff: ${r.status()}`);
  r = await api.patch(`${BASE}/api/users/${me.id}/role`, { headers: admin, data: { role: 'visitor' } });
  check(r.status() === 409, `l'admin non può cambiare il proprio ruolo: ${r.status()} ${(await r.json()).code}`);
  const visitor = { Authorization: `Bearer ${await token(FEEDBACK_CANDIDATES[1])}` };
  r = await api.get(`${BASE}/api/users`, { headers: visitor });
  check(r.status() === 403, `un visitatore che chiama GET /api/users riceve ${r.status()}`);
  // il cambio di ruolo vale subito, senza un nuovo accesso (ruolo riletto dal database)
  await user.goto(`${BASE}/pages/staff/dashboard.html`);
  await user.waitForLoadState('networkidle');
  check(await user.locator('main .message--error').count() === 0, 'Mario Rossi, ora staff, apre la dashboard senza rifare l\'accesso');
});

await scenario('S15', 'RNF', 'Interfaccia su smartphone', async () => {
  const [ctx, page] = await context({ width: 390, height: 844 });
  await login(page, FEEDBACK_CANDIDATES[1]);
  await page.waitForURL('**/pages/prenotazioni.html');
  for (const [path, name] of [['/pages/eventi.html', 'S15-mobile-eventi'], ['/pages/prenotazioni.html', 'S15-mobile-prenotazioni']]) {
    await page.goto(BASE + path);
    await page.waitForLoadState('networkidle');
    const width = await page.evaluate(() => document.documentElement.scrollWidth);
    check(width <= 390, `${path}: nessuno scorrimento orizzontale (${width} px)`);
    await shot(page, name);
  }
  check(page.jsErrors.length === 0, 'nessun errore JavaScript');
  await ctx.close();
});

// Nessun errore JavaScript o violazione della CSP in tutto il percorso
const jsErrors = [...guest.jsErrors, ...user.jsErrors, ...staff.jsErrors];
console.log(jsErrors.length ? `\nErrori JavaScript:\n${jsErrors.join('\n')}` : '\nNessun errore JavaScript né violazione della CSP.');
const passed = results.filter((r) => r.ok).length;
console.log(`Scenari superati: ${passed}/${results.length}`);
await Promise.all([guestCtx.close(), userCtx.close(), staffCtx.close()]);
await browser.close();
process.exit(passed === results.length && jsErrors.length === 0 ? 0 : 1);
