// REST API module for quick-pick
// Runs at module load, before app.js reads location.hash (app.js imports this module first).
const TOKEN_KEY = "quickPickToken";

export function getToken() {
  try {
    return sessionStorage.getItem(TOKEN_KEY) || localStorage.getItem(TOKEN_KEY) || "";
  } catch {
    return "";
  }
}

export function setToken(token, remember = false) {
  try {
    if (remember) {
      localStorage.setItem(TOKEN_KEY, token);
    } else {
      sessionStorage.setItem(TOKEN_KEY, token);
    }
  } catch {
    // Storage unavailable (private mode): stay unauthenticated.
  }
}

export function clearToken() {
  try {
    sessionStorage.removeItem(TOKEN_KEY);
  } catch {}
  try {
    localStorage.removeItem(TOKEN_KEY);
  } catch {}
}

// Capture #token=... / #<deckId>&token=...[&remember=1] once, persist it, strip it from the hash.
// The fragment is always rewritten (finally), even if the token is malformed.
function captureTokenFromFragment() {
  let raw = "";
  try {
    raw = (location.hash || "").replace(/^#/, "");
  } catch {
    return;
  }
  if (!raw || !raw.includes("token=")) return;
  const kept = [];
  try {
    let token = null;
    let remember = false;
    for (const part of raw.split("&")) {
      if (part.startsWith("token=")) {
        try {
          token = decodeURIComponent(part.slice("token=".length));
        } catch {
          token = null; // Malformed percent-encoding: drop the token.
        }
      } else if (part === "remember=1") {
        remember = true;
      } else if (part) {
        kept.push(part);
      }
    }
    if (token) setToken(token, remember);
  } finally {
    try {
      // Preserve path+query without ever parsing the query string for tokens.
      const base = location.href.split("#")[0];
      history.replaceState(null, "", kept.length ? `${base}#${kept.join("&")}` : base);
    } catch {
      // History unavailable: nothing more we can do.
    }
  }
}

captureTokenFromFragment();

async function readErrorBody(response) {
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    try {
      return await response.json();
    } catch {
      return { error: "Erreur de décodage JSON serveur" };
    }
  }
  const text = await response.text();
  return { error: text || `Erreur serveur (${response.status})` };
}

function promptForToken() {
  try {
    const token = window.prompt("Jeton d'accès quick-pick (QUICK_PICK_TOKEN) :");
    if (token) setToken(token, false);
    return token || null;
  } catch {
    return null;
  }
}

export function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function request(endpoint, options = {}) {
  const doFetch = (extraHeaders = {}) => fetch(endpoint, {
    ...options,
    // authHeaders() last so a token entered at the 401 prompt wins on retry.
    headers: { "Content-Type": "application/json", ...(options.headers || {}), ...extraHeaders, ...authHeaders() },
  });
  let response = await doFetch();
  let data = await readErrorBody(response);
  if (response.status === 401 && data && data.error === "unauthorized") {
    const token = promptForToken();
    if (!token) throw new Error(data.detail || data.error || `Erreur serveur (${response.status})`);
    response = await doFetch();
    data = await readErrorBody(response);
  }
  if (!response.ok) {
    throw new Error(data.detail || data.error || `Erreur serveur (${response.status})`);
  }
  return data;
}

// Same 401 -> prompt -> retry flow for raw fetch callers (classifier helpers).
export async function authFetch(url, options = {}) {
  let response = await fetch(url, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}), ...authHeaders() },
  });
  const contentType = response.headers.get("content-type") || "";
  if (response.status === 401) {
    let body = null;
    try {
      body = contentType.includes("application/json") ? await response.clone().json() : null;
    } catch {
      body = null;
    }
    if (body && body.error === "unauthorized") {
      const token = promptForToken();
      if (!token) return response;
      response = await fetch(url, {
        ...options,
        headers: { "Content-Type": "application/json", ...(options.headers || {}), ...authHeaders() },
      });
    }
  }
  return response;
}

export function fetchDecks() {
  return request("/api/decks");
}

export function fetchDeckState(deckId) {
  return request(`/api/decks/${encodeURIComponent(deckId)}`);
}

export function postDecision(deckId, itemId, actionId, comment = null) {
  return request(`/api/decks/${encodeURIComponent(deckId)}/decide`, {
    method: "POST",
    body: JSON.stringify({ item_id: itemId, action: actionId, comment: comment || undefined }),
  });
}

export function postUndo(deckId, itemId = null) {
  return request(`/api/decks/${encodeURIComponent(deckId)}/undo`, {
    method: "POST",
    body: JSON.stringify(itemId ? { item_id: itemId } : {}),
  });
}

export function postSkip(deckId, itemId) {
  return request(`/api/decks/${encodeURIComponent(deckId)}/skip`, {
    method: "POST",
    body: JSON.stringify({ item_id: itemId }),
  });
}

export function fetchSummary(deckId) {
  return request(`/api/decks/${encodeURIComponent(deckId)}/summary`);
}
