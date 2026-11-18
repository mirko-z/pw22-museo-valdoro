// Gestione degli eventi da parte dello staff (UC08, UC09).
import { api } from '../api.js';
import { isStaff, renderUserArea, requireRole } from '../auth.js';
import { el, formatShortDate, formatTime, fromLocalInput, showMessage, toLocalInput } from '../ui.js';

const tbody = document.querySelector('[data-events]');
const message = document.querySelector('[data-message]');
const form = document.querySelector('[data-event-form]');
const formTitle = document.querySelector('[data-form-title]');

renderUserArea();
const user = await requireRole(isStaff, 'Questa pagina è riservata allo staff del museo.');

// L'elenco completo (anche eventi passati e annullati) viene dagli indicatori per evento
async function load() {
  const events = await api.get('/dashboard/events');
  tbody.replaceChildren(...events.reverse().map(row));
}

function row(e) {
  const editable = e.status === 'scheduled' && !e.is_ended;
  const actions = [
    el('a', { class: 'btn btn-sm btn-outline-secondary', href: `/pages/staff/evento.html?id=${e.event_id}` }, 'Partecipanti'),
    editable ? el('button', { class: 'btn btn-sm btn-outline-primary', type: 'button', onclick: () => edit(e.event_id) }, 'Modifica') : null,
    editable ? el('button', { class: 'btn btn-sm btn-outline-warning', type: 'button', onclick: () => cancel(e) }, 'Annulla') : null,
    e.bookings_total === 0 ? el('button', { class: 'btn btn-sm btn-outline-danger', type: 'button', onclick: () => remove(e) }, 'Elimina') : null,
  ];
  let status = el('span', { class: 'badge text-bg-success' }, 'in programma');
  if (e.status === 'cancelled') status = el('span', { class: 'badge text-bg-danger' }, 'annullato');
  else if (e.is_ended) status = el('span', { class: 'badge text-bg-secondary' }, 'concluso');
  // Azioni sotto il titolo (non in una colonna a parte): restano visibili anche su mobile
  return el('tr', {},
    el('td', {}, el('div', { class: 'fw-semibold' }, e.title),
      el('div', { class: 'd-flex flex-wrap gap-1 mt-1' }, actions)),
    el('td', {}, `${formatShortDate(e.start_at)} ${formatTime(e.start_at)}`),
    el('td', {}, status),
    el('td', { class: 'text-end' }, `${e.confirmed_seats}/${e.capacity}`),
  );
}

async function edit(id) {
  const e = await api.get(`/events/${id}`);
  formTitle.textContent = `Modifica: ${e.title}`;
  for (const [name, value] of Object.entries({
    id: e.id, title: e.title, type: e.type, description: e.description ?? '', capacity: e.capacity, price: e.price,
    max_seats_per_booking: e.max_seats_per_booking, cancellation_deadline_hours: e.cancellation_deadline_hours,
    start_at: toLocalInput(e.start_at), end_at: toLocalInput(e.end_at),
  })) form.elements[name].value = value;
  form.scrollIntoView({ behavior: 'smooth' });
}

function payload() {
  const f = form.elements;
  const optionalInt = (input) => (input.value === '' ? null : Number(input.value));
  return {
    title: f.title.value, type: f.type.value, description: f.description.value || null,
    start_at: fromLocalInput(f.start_at.value), end_at: fromLocalInput(f.end_at.value),
    capacity: Number(f.capacity.value), price: f.price.value || '0',
    max_seats_per_booking: optionalInt(f.max_seats_per_booking),
    cancellation_deadline_hours: optionalInt(f.cancellation_deadline_hours),
  };
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (!form.reportValidity()) return;
  const id = form.elements.id.value;
  try {
    const saved = id ? await api.patch(`/events/${id}`, payload()) : await api.post('/events', payload());
    showMessage(message, `Evento "${saved.title}" salvato.`, 'success');
    form.reset();
    await load();
  } catch (error) {
    showMessage(message, error.message, 'error');
  }
});

form.addEventListener('reset', () => {
  form.elements.id.value = '';
  formTitle.textContent = 'Nuovo evento';
});

async function cancel(e) {
  if (!confirm(`Annullare "${e.title}"? Le ${e.bookings_total - e.bookings_cancelled} prenotazioni confermate verranno annullate.`)) return;
  await act(() => api.post(`/events/${e.event_id}/cancel`), 'Evento annullato.');
}

async function remove(e) {
  if (!confirm(`Eliminare definitivamente "${e.title}"?`)) return;
  await act(() => api.delete(`/events/${e.event_id}`), 'Evento eliminato.');
}

async function act(operation, done) {
  try {
    await operation();
    showMessage(message, done, 'success');
    await load();
  } catch (error) {
    showMessage(message, error.message, 'error');
  }
}

if (user) await load().catch((error) => showMessage(message, error.message, 'error'));
