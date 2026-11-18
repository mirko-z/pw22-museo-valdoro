// Dashboard della direzione (UC11): KPI K5–K8 e andamento settimanale.
import { api } from '../api.js';
import { isStaff, renderUserArea, requireRole } from '../auth.js';
import { EVENT_TYPES, el, formatPercent, formatRating, formatShortDate, showMessage } from '../ui.js';

renderUserArea();
const user = await requireRole(isStaff, 'Questa pagina è riservata allo staff del museo.');

function kpi(label, value, note) {
  return el('div', { class: 'col-6 col-md-4 col-xl-2' },
    el('div', { class: 'card h-100' }, el('div', { class: 'card-body' },
      el('div', { class: 'text-body-secondary small' }, label),
      el('div', { class: 'kpi-value' }, value),
      note ? el('div', { class: 'text-body-secondary small' }, note) : null)));
}

async function load() {
  const [overview, events, types, weekly] = await Promise.all([
    api.get('/dashboard/overview'), api.get('/dashboard/events'),
    api.get('/dashboard/types'), api.get('/dashboard/weekly?weeks=12'),
  ]);

  document.querySelector('[data-kpis]').replaceChildren(
    kpi('Prenotazioni', overview.bookings_total, `${overview.events_upcoming} eventi in programma`),
    kpi('Tasso di annullamento', formatPercent(overview.cancellation_rate), `${overview.bookings_cancelled} annullate`),
    kpi('Riempimento medio', formatPercent(overview.average_fill_rate), `${overview.events_concluded} eventi conclusi`),
    kpi('Voto medio', formatRating(overview.average_rating), `${overview.feedback_count} feedback`),
    kpi('Copertura feedback', formatPercent(overview.feedback_coverage), 'feedback / partecipanti'),
  );

  document.querySelector('[data-events]').replaceChildren(...events.map((e) => el('tr', {},
    el('td', {}, el('a', { href: `/pages/staff/evento.html?id=${e.event_id}` }, e.title), ' ',
      e.status === 'cancelled' ? el('span', { class: 'badge text-bg-danger' }, 'annullato') : null),
    el('td', {}, formatShortDate(e.start_at)),
    el('td', { class: 'text-end' }, `${e.confirmed_seats}/${e.capacity}`),
    el('td', { class: 'text-end' }, formatPercent(e.fill_rate)),
    el('td', { class: 'text-end' }, formatPercent(e.cancellation_rate)),
    el('td', { class: 'text-end' }, formatRating(e.average_rating)),
    el('td', { class: 'text-end' }, formatPercent(e.feedback_coverage)),
  )));

  document.querySelector('[data-types]').replaceChildren(...types.map((t) => el('tr', {},
    el('td', {}, EVENT_TYPES[t.type]),
    el('td', { class: 'text-end' }, formatPercent(t.average_fill_rate)),
    el('td', { class: 'text-end' }, formatRating(t.average_rating)),
  )));

  const max = Math.max(1, ...weekly.map((w) => w.bookings));
  document.querySelector('[data-weekly]').replaceChildren(...weekly.map((w) => {
    const fill = el('div', { class: 'week-bar__fill' });
    fill.style.width = `${(w.bookings / max) * 100}%`;
    return el('div', { class: 'week-bar', title: `${w.bookings} prenotazioni, ${w.seats} posti` },
      el('span', {}, formatShortDate(w.week_start)),
      el('div', { class: 'week-bar__track' }, fill),
      el('span', { class: 'week-bar__value' }, w.bookings));
  }));
}

if (user) {
  try {
    await load();
  } catch (error) {
    showMessage(document.querySelector('[data-message]'), error.message, 'error');
  }
}
