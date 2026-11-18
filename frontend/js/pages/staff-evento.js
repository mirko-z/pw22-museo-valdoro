// Partecipanti e feedback di un evento (UC10).
import { api } from '../api.js';
import { isStaff, renderUserArea, requireRole } from '../auth.js';
import { EVENT_TYPES, el, formatDateTime, formatShortDate, showMessage } from '../ui.js';

renderUserArea();
const user = await requireRole(isStaff, 'Questa pagina è riservata allo staff del museo.');
const id = Number(new URLSearchParams(location.search).get('id'));

async function load() {
  const [event, participants, feedback] = await Promise.all([
    api.get(`/events/${id}`), api.get(`/events/${id}/participants`), api.get(`/events/${id}/feedback`),
  ]);
  const seats = participants.reduce((sum, p) => sum + p.seats, 0);
  document.title = `${event.title} – Area staff`;
  document.querySelector('[data-title]').textContent = event.title;
  document.querySelector('[data-summary]').textContent =
    `${EVENT_TYPES[event.type]} · ${formatDateTime(event.start_at)} · ${seats}/${event.capacity} posti confermati`
    + (event.status === 'cancelled' ? ' · evento annullato' : '');

  const tbody = document.querySelector('[data-participants]');
  tbody.replaceChildren(...participants.map((p) => el('tr', {},
    el('td', {}, p.full_name), el('td', {}, p.email),
    el('td', { class: 'text-end' }, p.seats), el('td', {}, el('code', {}, p.code)))));
  if (participants.length === 0) tbody.replaceChildren(el('tr', {}, el('td', { colspan: 4, class: 'text-body-secondary' }, 'Nessun partecipante confermato.')));

  const list = document.querySelector('[data-feedback]');
  list.replaceChildren(...feedback.map((f) => el('li', { class: 'list-group-item' },
    el('div', { class: 'd-flex justify-content-between' },
      el('strong', {}, `${f.rating}/5`), el('span', { class: 'small text-body-secondary' }, `${f.full_name} · ${formatShortDate(f.created_at)}`)),
    f.comment ? el('p', { class: 'mb-0 small' }, f.comment) : null)));
  if (feedback.length === 0) list.replaceChildren(el('li', { class: 'list-group-item text-body-secondary' }, 'Nessun feedback.'));
}

if (user) {
  try {
    await load();
  } catch (error) {
    showMessage(document.querySelector('[data-message]'), error.message, 'error');
  }
}
