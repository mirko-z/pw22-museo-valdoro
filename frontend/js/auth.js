// Stato dell'utente corrente e area utente nell'intestazione.
// Il browser non può leggere il cookie HttpOnly: per sapere chi è collegato chiede /api/auth/me (401 = nessuna sessione valida).

import { api, ApiError } from './api.js';
import { el } from './ui.js';

let cached;

export async function currentUser() {
  if (cached !== undefined) return cached;
  try {
    cached = await api.get('/auth/me');
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 401) throw error;
    cached = null;
  }
  return cached;
}

export const isStaff = (user) => user?.role === 'staff' || user?.role === 'admin';

export async function logout() {
  await api.post('/auth/logout');
  cached = null;
  location.href = '/';
}

// Riempie <div data-user-area> con nome e link adatti al ruolo
export async function renderUserArea(root = document) {
  const area = root.querySelector('[data-user-area]');
  if (!area) return null;
  const user = await currentUser().catch(() => null);
  const links = [];
  if (!user) {
    links.push(el('a', { href: '/pages/accesso.html' }, 'Accedi'));
  } else {
    if (user.role === 'visitor') {
       const here = location.pathname === '/pages/prenotazioni.html' ? 'page' : null;
      links.push(el('a', { href: '/pages/prenotazioni.html', 'aria-current': here }, 'Le mie prenotazioni'));
    }
    if (isStaff(user) && !location.pathname.startsWith('/pages/staff/')) {
      links.push(el('a', { href: '/pages/staff/dashboard.html' }, 'Area staff'));
    }
    links.push(
      el('span', { class: 'user-area__name' }, user.full_name),
      el('button', { type: 'button', class: 'link-button', onclick: logout }, 'Esci'),
    );
  }
  area.replaceChildren(...links);
  // Elementi pensati solo per chi non ha un account (es. "Crea un account" in home)
  if (user) root.querySelectorAll('[data-guest-only]').forEach((node) => node.remove());
   return user;
}

// Protezione lato interfaccia delle pagine riservate. È solo una comodità: le autorizzazioni vere le verifica il back-end su ogni richiesta (401/403).
export async function requireRole(check, message) {
  let user;
  try {
    user = await currentUser();
  } catch (error) {
    // API non raggiungibile: messaggio invece di una pagina vuota
    document.querySelector('main').replaceChildren(el('p', { class: 'message message--error' }, error.message));
    return null;
  }
  if (!user) {
    location.href = `/pages/accesso.html?next=${encodeURIComponent(location.pathname)}`;
    return null;
  }
  if (!check(user)) {
    document.querySelector('main').replaceChildren(el('p', { class: 'message message--error' }, message));
    return null;
  }
  // Link riservati (es. Dashboard ed Eventi dell'area staff): nascosti nell'HTML,  mostrati solo dopo la verifica del ruolo, così chi non ha accesso non li vede  nemmeno per un istante. Resta una comodità d'interfaccia: i permessi li verifica il back-end.
  document.querySelectorAll('[data-staff-only]').forEach((node) => { node.hidden = false; });
  return user;
}
