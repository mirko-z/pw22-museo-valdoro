// Utilità per il DOM e la formattazione.
// el() crea elementi impostando il testo con textContent: i dati che arrivano
// dall'API (titoli, nomi, commenti) non vengono mai interpretati come HTML.
// È l'equivalente sicuro di $('<p>').text(valore) in jQuery.

export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key === 'dataset') Object.assign(node.dataset, value);
    else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? '' : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

// Messaggio di esito in un contenitore con role="status" (letto dagli screen reader)
export function showMessage(container, text, type = 'info') {
  container.replaceChildren(text ? el('p', { class: `message message--${type}` }, text) : '');
}

// --- Formattazione (date in ora di Roma, come richiede RNF12) ----------------

const TZ = 'Europe/Rome';
const dateTime = new Intl.DateTimeFormat('it-IT', {
  timeZone: TZ, weekday: 'short', day: 'numeric', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit',
});
const timeOnly = new Intl.DateTimeFormat('it-IT', { timeZone: TZ, hour: '2-digit', minute: '2-digit' });
const shortDate = new Intl.DateTimeFormat('it-IT', { timeZone: TZ, day: '2-digit', month: '2-digit' });
const euro = new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR' });

export const formatDateTime = (iso) => dateTime.format(new Date(iso));
export const formatTime = (iso) => timeOnly.format(new Date(iso));
export const formatShortDate = (iso) => shortDate.format(new Date(iso));
export const formatPrice = (value) => (Number(value) === 0 ? 'Gratuito' : euro.format(Number(value)));
export const formatPercent = (ratio) => (ratio === null ? '–' : `${Math.round(ratio * 100)}%`);
export const formatRating = (value) => (value === null ? '–' : value.toFixed(1).replace('.', ','));

export const EVENT_TYPES = { guided_tour: 'Visita guidata', workshop: 'Laboratorio', conference: 'Conferenza' };

// Conversione tra ISO (UTC) e il valore di <input type="datetime-local">,
// che è un orario locale senza fuso: si assume il fuso del browser (Italia).
export function toLocalInput(iso) {
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
export const fromLocalInput = (value) => new Date(value).toISOString();

// --- Componenti della parte pubblica (schede evento e prenotazione) ----------

const dayParts = new Intl.DateTimeFormat('it-IT', { timeZone: TZ, weekday: 'short', day: 'numeric', month: 'short' });
const monthYear = new Intl.DateTimeFormat('it-IT', { timeZone: TZ, month: 'long', year: 'numeric' });
const longDate = new Intl.DateTimeFormat('it-IT', { timeZone: TZ, weekday: 'long', day: 'numeric', month: 'long' });

export const formatLongDate = (iso) => longDate.format(new Date(iso));

// Blocco data "a calendario": giorno della settimana, giorno, mese
export function dateBlock(iso) {
  const parts = Object.fromEntries(dayParts.formatToParts(new Date(iso)).map((p) => [p.type, p.value]));
  return el('div', { class: 'date-block', 'aria-hidden': 'true' },
    el('span', { class: 'date-block__weekday' }, parts.weekday.replace('.', '')),
    el('span', { class: 'date-block__day' }, parts.day),
    el('span', { class: 'date-block__month' }, parts.month.replace('.', '')));
}

// Raggruppa una lista già ordinata per data in [{label: "ottobre 2026", items}]
export function groupByMonth(items, dateOf) {
  const groups = [];
  for (const item of items) {
    const label = monthYear.format(new Date(dateOf(item)));
    if (groups.at(-1)?.label !== label) groups.push({ label, items: [] });
    groups.at(-1).items.push(item);
  }
  return groups;
}

// Posti disponibili, solo testo: "Esaurito", "Ultimi N posti" (≤ 20% della capienza), "N su M"
export function seatsText(available, capacity) {
  if (available === 0) return el('span', { class: 'seats-none' }, 'Esaurito');
  if (available / capacity <= 0.2) return el('span', { class: 'seats-few' }, `Ultimi ${available} posti`);
  return el('span', {}, `${available} liberi su ${capacity}`);
}

// Lista <dl> di coppie etichetta–valore (valori null saltati)
export function metaList(pairs) {
  return el('dl', { class: 'card__meta' },
    pairs.filter(([, v]) => v !== null && v !== undefined).flatMap(([k, v]) => [el('dt', {}, k), el('dd', {}, v)]));
}
