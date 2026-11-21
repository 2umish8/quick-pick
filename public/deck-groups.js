// Pure module (no DOM): home page grouping of decks and relative dates. Tested by node --test.
//
// A deck is "to decide" until it is finished with at least one card; a finished deck is then
// "waiting" for its agent until the agent's acknowledgement (ack_state "valid") is recorded.
// Order of the groups is the order of this list.
export const GROUPS = [
  { key: "todo", title: "À trancher" },
  { key: "waiting", title: "Tranché, en attente de l'agent" },
  { key: "invalid", title: "Illisibles" },
  { key: "acked", title: "Pris en compte" },
];

// Group of one deck entry from GET /api/decks.
export function deckGroupKey(deck) {
  if (deck.invalid) return "invalid";
  const total = Number(deck.total);
  // An empty deck is "finished" for the server, but there is nothing to acknowledge: it stays to decide.
  if (!(total > 0)) return "todo";
  if (!deck.is_completed) return "todo";
  return deck.ack_state === "valid" ? "acked" : "waiting";
}

// Human state of a deck inside its group (also exposed as data-state for tests).
export function deckStateKey(deck) {
  if (deck.invalid) return "invalid";
  const total = Number(deck.total);
  if (!(total > 0)) return "empty";
  if (deck.is_completed) return deck.ack_state === "valid" ? "acked" : "waiting";
  return Number(deck.decided) > 0 ? "in-progress" : "not-started";
}

const stamp = value => {
  const ms = Date.parse(value || "");
  return Number.isNaN(ms) ? null : ms;
};

// Most recent first; a missing or unreadable date goes last; ties keep a stable title order.
function byRecency(getDate) {
  return (a, b) => {
    const da = stamp(getDate(a)), db = stamp(getDate(b));
    if (da !== db) {
      if (da === null) return 1;
      if (db === null) return -1;
      return db - da;
    }
    return String(a.title ?? a.id).localeCompare(String(b.title ?? b.id), "fr");
  };
}

// -> [{ key, title, decks }] in fixed order; groups without any deck are omitted (no empty space).
export function groupDecks(decks) {
  const buckets = Object.fromEntries(GROUPS.map(g => [g.key, []]));
  for (const deck of Array.isArray(decks) ? decks : []) buckets[deckGroupKey(deck)].push(deck);
  buckets.todo.sort(byRecency(d => d.last_activity));
  buckets.waiting.sort(byRecency(d => d.last_activity));
  buckets.invalid.sort(byRecency(d => d.last_activity));
  buckets.acked.sort(byRecency(d => d.ack?.at || d.last_activity));
  return GROUPS.filter(g => buckets[g.key].length).map(g => ({ key: g.key, title: g.title, decks: buckets[g.key] }));
}

const MONTHS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];

// "à l'instant", "il y a 5 min", "il y a 3 h", "hier", "il y a 4 j", then "12 nov." (and the year if not current).
export function relativeDate(iso, now = Date.now()) {
  const ms = stamp(iso);
  if (ms === null) return "";
  const diff = Math.max(0, now - ms);
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "à l'instant";
  if (minutes < 60) return `il y a ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `il y a ${hours} h`;
  const days = Math.floor(hours / 24);
  if (days === 1) return "hier";
  if (days < 7) return `il y a ${days} j`;
  const date = new Date(ms), current = new Date(now);
  const base = `${date.getDate()} ${MONTHS[date.getMonth()]}`;
  return date.getFullYear() === current.getFullYear() ? base : `${base} ${date.getFullYear()}`;
}
