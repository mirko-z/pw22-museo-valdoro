// Home: i prossimi sei eventi in programma.
import { api } from '../api.js';
import { renderUserArea } from '../auth.js';
import { EVENT_TYPES, dateBlock, el, formatPrice, formatTime, seatsText, showMessage } from '../ui.js';

renderUserArea();

const list = document.querySelector('[data-upcoming]');
const message = document.querySelector('[data-message]');

try {
  const events = (await api.get('/events')).slice(0, 6);
  if (events.length === 0) showMessage(message, 'Al momento non ci sono eventi in programma.');
  list.replaceChildren(...events.map((e) => el('li', { class: `card card--${e.type}` },
    el('div', { class: 'card__head' },
      dateBlock(e.start_at),
      el('div', {},
        el('p', { class: 'card__type' }, EVENT_TYPES[e.type]),
        el('h3', { class: 'card__title' }, e.title))),
    el('p', { class: 'card__note' }, `Ore ${formatTime(e.start_at)} · ${formatPrice(e.price)} · `,
      seatsText(e.available_seats, e.capacity)),
    el('div', { class: 'card__actions' },
      el('a', { class: 'button button--secondary', href: `/pages/eventi.html#evento-${e.id}` }, 'Dettagli e prenotazione')),
  )));
} catch (error) {
  showMessage(message, error.message, 'error');
}
