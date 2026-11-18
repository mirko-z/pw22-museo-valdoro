// Elenco pubblico degli eventi e prenotazione (UC03, UC04).
import { api } from '../api.js';
import { renderUserArea } from '../auth.js';
import {
  EVENT_TYPES, dateBlock, el, formatPrice, formatTime, groupByMonth, metaList, seatsText, showMessage,
} from '../ui.js';

const list = document.querySelector('[data-events]');
const message = document.querySelector('[data-message]');
const filter = document.querySelector('[data-filter]');
const user = await renderUserArea();

async function load() {
  try {
    const type = filter.querySelector('input:checked').value;
    const query = type ? `?type=${encodeURIComponent(type)}` : '';
    const events = await api.get(`/events${query}`);
    if (events.length === 0) showMessage(message, 'Nessun evento in programma per questo filtro.');
    list.replaceChildren(...groupByMonth(events, (e) => e.start_at).map(({ label, items }) =>
      el('section', { class: 'month', 'aria-label': label },
        el('h2', { class: 'month__title' }, label,
          el('span', { class: 'month__count' }, items.length === 1 ? '1 evento' : `${items.length} eventi`)),
        el('ul', { class: 'card-grid' }, items.map(eventCard)))));
    // Arrivo dalla home con #evento-ID: porta la scheda in vista
    if (location.hash) document.getElementById(location.hash.slice(1))?.scrollIntoView();
  } catch (error) {
    showMessage(message, error.message, 'error');
  }
}

// "72 ore" -> "3 giorni": più leggibile per il visitatore
function deadlineText(hours) {
  if (hours === 0) return "fino all'inizio";
  if (hours % 24 === 0) return hours === 24 ? 'fino a 1 giorno prima' : `fino a ${hours / 24} giorni prima`;
  return hours === 1 ? 'fino a 1 ora prima' : `fino a ${hours} ore prima`;
}

function eventCard(e) {
  const soldOut = e.available_seats === 0;
  return el('li', { class: `card card--${e.type}`, id: `evento-${e.id}` },
    el('div', { class: 'card__head' },
      dateBlock(e.start_at),
      el('div', {},
        el('p', { class: 'card__type' }, EVENT_TYPES[e.type]),
        el('h3', { class: 'card__title' }, e.title))),
    e.description ? el('p', { class: 'card__desc' }, e.description) : null,
    metaList([
      ['Orario', `${formatTime(e.start_at)} – ${formatTime(e.end_at)}`],
      ['Prezzo', formatPrice(e.price)],
      ['Annullamento', deadlineText(e.cancellation_deadline_hours)],
      ['Posti', seatsText(e.available_seats, e.capacity)],
    ]),
    el('div', { class: 'card__actions' }, bookingAction(e, soldOut)),
  );
}

function bookingAction(e, soldOut) {
  if (soldOut) return el('p', { class: 'card__note' }, 'Posti esauriti: le prenotazioni sono chiuse.');
  // Limite effettivo: il minore tra il massimo per prenotazione e i posti liberi
  const max = Math.min(e.max_seats_per_booking, e.available_seats);
  const limitText = e.available_seats < e.max_seats_per_booking
    ? `Puoi prenotare fino a ${max} ${max === 1 ? 'posto' : 'posti'}, cioè tutti quelli ancora liberi.`
    : `Fino a ${max} ${max === 1 ? 'posto' : 'posti'} per prenotazione.`;

  if (!user) {
    return el('div', { class: 'card__actions' },
      el('p', { class: 'card__note' }, limitText),
      el('a', { class: 'button button--secondary', href: `/pages/accesso.html?next=${encodeURIComponent(`/pages/eventi.html#evento-${e.id}`)}` },
        'Accedi per prenotare'));
  }
  if (user.role !== 'visitor') return el('p', { class: 'card__note' }, 'Le prenotazioni sono riservate ai visitatori.');

  const input = el('input', { id: `seats-${e.id}`, type: 'number', min: 1, max, value: 1, required: true, inputmode: 'numeric' });
  return el('form', { class: 'book-form', onsubmit: (ev) => book(ev, e, input) },
    el('div', { class: 'field' }, el('label', { for: `seats-${e.id}` }, 'Posti'), input),
    el('button', { class: 'button', type: 'submit' }, 'Prenota'),
    el('p', { class: 'book-form__hint' }, limitText),
  );
}

async function book(ev, e, input) {
  ev.preventDefault();
  const button = ev.submitter;
  button.disabled = true; // evita il doppio invio
  try {
    const booking = await api.post('/bookings', { event_id: e.id, seats: Number(input.value) });
    message.replaceChildren(el('p', { class: 'message message--success' },
      `Prenotazione confermata per "${booking.event_title}". Codice: `,
      el('strong', { class: 'booking-code' }, booking.code), ' – ',
      el('a', { href: '/pages/prenotazioni.html' }, 'vai alle tue prenotazioni')));
    await load();
  } catch (error) {
    showMessage(message, error.message, 'error');
    button.disabled = false;
  }
  message.scrollIntoView({ block: 'nearest' });
}

filter.addEventListener('change', load);
await load();
