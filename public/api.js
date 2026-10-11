// REST API module for quick-pick
const TOKEN_KEY = "quickPickToken";

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY) || "";
  } catch {
    return "";
  }
}

// Capture ?token=... once, persist it, then strip it from the URL.
function captureTokenFromURL() {
  try {
    const params = new URLSearchParams(location.search);
    const token = params.get("token");
    if (token) {
      localStorage.setItem(TOKEN_KEY, token);
      params.delete("token");
      const query = params.toString();
      history.replaceState(null, "", location.pathname + (query ? `?${query}` : "") + location.hash);
    }
  } catch {
    // Storage or history unavailable (private mode): stay unauthenticated.
  }
}

captureTokenFromURL();

export function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function request(endpoint, options = {}) {
  const response = await fetch(endpoint, {
    ...options,
    headers: { "Content-Type": "application/json", ...authHeaders(), ...(options.headers || {}) },
  });
  let data;
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    try {
      data = await response.json();
    } catch {
      data = { error: "Erreur de décodage JSON serveur" };
    }
  } else {
    const text = await response.text();
    data = { error: text || `Erreur serveur (${response.status})` };
  }
  if (!response.ok) {
    throw new Error(data.detail || data.error || `Erreur serveur (${response.status})`);
  }
  return data;
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
