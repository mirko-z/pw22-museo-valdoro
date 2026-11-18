// Area visitatore: prenotazioni, annullamento e feedback (UC05, UC06, UC07).
import { api } from '../api.js';
import { renderUserArea, requireRole } from '../auth.js';
import { EVENT_TYPES, dateBlock, el, formatDateTime, formatTime, metaList, showMessage } from '../ui.js';

const list = document.querySelector('[data-bookings]');
const message = document.querySelector('[data-message]');

renderUserArea();
const user = await requireRole((u) => u.role === 'visitor', 'Questa pagina è riservata ai visitatori.');

const isUpcoming = (b) => b.status === 'confirmed' && b.event_status !== 'cancelled' && new Date(b.event_end_at) >= new Date();

async function load() {
  try {
    const bookings = await api.get('/bookings/me');
    if (bookings.length === 0) {
      // Un solo messaggio per lo stato vuoto (niente sezioni vuote sotto)
      message.replaceChildren(el('p', { class: 'message' }, 'Non hai ancora prenotazioni. ',
        el('a', { href: '/pages/eventi.html' }, 'Scopri gli eventi in programma')));
      list.replaceChildren();
      return;
    }
    // Prossime in ordine di data; passate e annullate dalla più recente
    const byStart = (a, b) => new Date(a.event_start_at) - new Date(b.event_start_at);
    const upcoming = bookings.filter(isUpcoming).sort(byStart);
    const others = bookings.filter((b) => !isUpcoming(b)).sort((a, b) => byStart(b, a));
    list.replaceChildren(
      section('Prossime', upcoming, 'Nessuna prenotazione per i prossimi eventi.'),
      others.length ? section('Passate e annullate', others) : '',
    );
  } catch (error) {
    showMessage(message, error.message, 'error');
  }
}

function section(title, items, emptyText) {
  if (items.length === 0 && !emptyText) return '';
  return el('section', { class: 'bookings-section' },
    el('h2', {}, title),
    items.length ? el('ul', { class: 'card-grid' }, items.map(bookingCard)) : el('p', { class: 'muted' }, emptyText));
}

function bookingCard(b) {
  const ended = new Date(b.event_end_at) < new Date();
  let state;
  if (b.event_status === 'cancelled') state = el('span', { class: 'badge badge--cancelled' }, 'Evento annullato dal museo');
  else if (b.status === 'cancelled') state = el('span', { class: 'badge badge--cancelled' }, 'Prenotazione annullata');
  else if (ended) state = el('span', { class: 'badge badge--past' }, 'Evento concluso');
  else state = el('span', { class: 'badge badge--confirmed' }, 'Confermata');

  const active = isUpcoming(b);
  // Stessa impostazione delle schede evento: tipo in alto, titolo del colore del tipo
  return el('li', { class: `card card--${b.event_type}${active || b.can_leave_feedback ? '' : ' card--muted'}` },
    el('div', { class: 'card__head' },
      dateBlock(b.event_start_at),
      el('div', {},
        el('p', { class: 'card__type' }, EVENT_TYPES[b.event_type]),
        el('h3', { class: 'card__title' }, b.event_title))),
    state,
    metaList([
      ['Orario', `${formatTime(b.event_start_at)} – ${formatTime(b.event_end_at)}`],
      ['Posti', String(b.seats)],
      b.can_cancel ? ['Annullabile', `fino a ${formatDateTime(b.cancellation_deadline)}`] : [null, null],
      // Prenotazione ancora attiva ma oltre il termine: si spiega perché manca il pulsante
      active && !b.can_cancel ? ['Annullamento', `non più possibile: termine scaduto ${formatDateTime(b.cancellation_deadline)}`] : [null, null],
      b.my_rating && b.status === 'confirmed' ? ['Il tuo voto', `${b.my_rating} su 5`] : [null, null],
    ]),
    el('div', { class: 'ticket' },
      el('span', { class: 'ticket__label' }, 'Codice'),
      el('strong', { class: 'booking-code' }, b.code)),
    (b.can_cancel || b.can_leave_feedback)
      ? el('div', { class: 'card__actions' },
        b.can_cancel
          ? el('button', { class: 'button button--secondary', type: 'button', onclick: () => cancel(b) }, 'Annulla prenotazione')
          : null,
        b.can_leave_feedback ? feedbackForm(b) : null)
      : null,
  );
}

async function cancel(b) {
  if (!confirm(`Annullare la prenotazione per "${b.event_title}"?`)) return;
  try {
    await api.post(`/bookings/${encodeURIComponent(b.code)}/cancel`);
    showMessage(message, 'Prenotazione annullata.', 'success');
    await load();
  } catch (error) {
    showMessage(message, error.message, 'error');
  }
}

function feedbackForm(b) {
  const id = `fb-${b.code}`;
  const rating = el('select', { id: `${id}-rating`, name: 'rating', required: true },
    el('option', { value: '' }, 'Scegli…'),
    [5, 4, 3, 2, 1].map((n) => el('option', { value: n }, `${n} su 5`)));
  const comment = el('textarea', { id: `${id}-comment`, name: 'comment', maxlength: 1000 });
  return el('form', { class: 'form feedback', onsubmit: (ev) => sendFeedback(ev, b, rating, comment) },
    el('h3', {}, 'Com\'è andata?'),
    el('div', { class: 'field' }, el('label', { for: rating.id }, 'Voto'), rating),
    el('div', { class: 'field' }, el('label', { for: comment.id }, 'Commento (facoltativo)'), comment),
    el('button', { class: 'button', type: 'submit' }, 'Invia feedback'),
  );
}

async function sendFeedback(ev, b, rating, comment) {
  ev.preventDefault();
  try {
    await api.post(`/events/${b.event_id}/feedback`, { rating: Number(rating.value), comment: comment.value || null });
    showMessage(message, 'Grazie per il tuo feedback!', 'success');
    await load();
  } catch (error) {
    showMessage(message, error.message, 'error');
  }
}

if (user) await load();
