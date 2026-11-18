// Client delle API: un unico punto per tutte le chiamate fetch. Il token JWT viaggia nel cookie HttpOnly: il JavaScript non lo legge né lo salva (niente localStorage), quindi un eventuale XSS non può rubarlo.
// credentials: 'same-origin' invia il cookie perché pagina e API hanno la stessa origine (nginx fa da reverse proxy), senza bisogno di CORS.

export class ApiError extends Error {
  constructor(status, code, message) {
    super(message);
    this.status = status; // codice HTTP (401, 409, ...)
    this.code = code;     // codice applicativo (SEATS_UNAVAILABLE, ...)
  }
}

async function request(method, path, { json, form } = {}) {
  const options = { method, credentials: 'same-origin', headers: { Accept: 'application/json' } };
  if (json !== undefined) {
    options.headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(json);
  } else if (form !== undefined) {
    options.body = new URLSearchParams(form); // application/x-www-form-urlencoded
  }

  let response;
  try {
    response = await fetch(`/api${path}`, options);
  } catch {
    throw new ApiError(0, 'NETWORK', 'Servizio non raggiungibile. Riprova tra poco.');
  }
  if (response.status === 204) return null;

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(response.status, body?.code ?? 'ERROR', errorMessage(response.status, body));
  }
  return body;
}

// Errori di dominio: {detail: "...", code: "..."}; errori di validazione (422)  di FastAPI: {detail: [{loc, msg}, ...]}.
function errorMessage(status, body) {
  if (typeof body?.detail === 'string') return body.detail;
  if (Array.isArray(body?.detail)) return 'Dati non validi: controlla i campi del modulo.';
  return `Errore imprevisto (${status}).`;
}

export const api = {
  get: (path) => request('GET', path),
  post: (path, json) => request('POST', path, { json }),
  patch: (path, json) => request('PATCH', path, { json }),
  delete: (path) => request('DELETE', path),
  login: (email, password) => request('POST', '/auth/login', { form: { username: email, password } }),
};
