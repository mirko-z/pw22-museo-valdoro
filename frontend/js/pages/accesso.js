// Accesso e registrazione (UC01, UC02).
import { api } from '../api.js';
import { renderUserArea } from '../auth.js';
import { showMessage } from '../ui.js';

renderUserArea();

const loginForm = document.querySelector('[data-login-form]');
const registerForm = document.querySelector('[data-register-form]');

// Dopo l'accesso: la pagina richiesta (solo percorsi interni, per evitare
// redirect verso siti esterni) oppure la pagina adatta al ruolo
function destination(user) {
  const next = new URLSearchParams(location.search).get('next');
  if (next && next.startsWith('/') && !next.startsWith('//')) return next;
  return user.role === 'visitor' ? '/pages/prenotazioni.html' : '/pages/staff/dashboard.html';
}

async function loginAndRedirect(email, password) {
  await api.login(email, password); // il server imposta il cookie HttpOnly
  const user = await api.get('/auth/me');
  location.href = destination(user);
}

loginForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const data = new FormData(loginForm);
  const message = document.querySelector('[data-login-message]');
  try {
    await loginAndRedirect(data.get('email'), data.get('password'));
  } catch (error) {
    showMessage(message, error.message, 'error');
  }
});

registerForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(registerForm));
  const message = document.querySelector('[data-register-message]');
  try {
    await api.post('/auth/register', data);
    await loginAndRedirect(data.email, data.password);
  } catch (error) {
    showMessage(message, error.message, 'error');
  }
});
