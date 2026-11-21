// Home page grouping (public/deck-groups.js, pure module). Run: node --test tests/js/deck_groups.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { groupDecks, deckGroupKey, deckStateKey, relativeDate } from "../../public/deck-groups.js";

const NOW = Date.parse("2026-11-21T12:00:00Z");
const deck = (id, extra = {}) => ({
  id, title: id, total: 4, decided: 0, is_completed: false, invalid: false,
  ack_state: "none", ack: null, last_activity: "2026-11-20T10:00:00Z", ...extra,
});
const ids = group => group.decks.map(d => d.id);

test("three groups in fixed order: to decide, waiting for the agent, acknowledged", () => {
  const groups = groupDecks([
    deck("acked", { decided: 4, is_completed: true, ack_state: "valid", ack: { agent: "claude", at: "2026-11-21T09:00:00Z" } }),
    deck("waiting", { decided: 4, is_completed: true }),
    deck("todo", { decided: 1 }),
  ]);
  assert.deepEqual(groups.map(g => g.key), ["todo", "waiting", "acked"]);
  assert.deepEqual(groups.map(g => g.title), ["À trancher", "Tranché, en attente de l'agent", "Pris en compte"]);
  assert.deepEqual(groups.map(ids), [["todo"], ["waiting"], ["acked"]]);
});

test("empty groups are omitted, empty input gives no group", () => {
  assert.deepEqual(groupDecks([]), []);
  assert.deepEqual(groupDecks(undefined), []);
  assert.deepEqual(groupDecks([deck("a")]).map(g => g.key), ["todo"]);
});

test("a deck without any card goes to 'to decide', never to waiting or acknowledged", () => {
  const empty = deck("empty", { total: 0, decided: 0, is_completed: true, ack_state: "valid" });
  assert.equal(deckGroupKey(empty), "todo");
  assert.equal(deckStateKey(empty), "empty");
});

test("an unreadable deck is listed in its own group", () => {
  const groups = groupDecks([deck("broken", { invalid: true, total: 0, error: "JSON" }), deck("ok")]);
  assert.deepEqual(groups.map(g => g.key), ["todo", "invalid"]);
  assert.equal(deckStateKey(groups[1].decks[0]), "invalid");
});

test("a stale acknowledgement puts the finished deck back in waiting", () => {
  const stale = deck("stale", { decided: 4, is_completed: true, ack_state: "stale", ack: { agent: "claude", at: "2026-11-19T09:00:00Z" } });
  assert.equal(deckGroupKey(stale), "waiting");
  assert.equal(deckStateKey(stale), "waiting");
});

test("state keys for progress", () => {
  assert.equal(deckStateKey(deck("a")), "not-started");
  assert.equal(deckStateKey(deck("b", { decided: 2 })), "in-progress");
  assert.equal(deckStateKey(deck("c", { decided: 4, is_completed: true })), "waiting");
  assert.equal(deckStateKey(deck("d", { decided: 4, is_completed: true, ack_state: "valid" })), "acked");
});

test("sort by last activity, most recent first; no date goes last; title breaks ties", () => {
  const [group] = groupDecks([
    deck("old", { last_activity: "2026-11-01T00:00:00Z" }),
    deck("none", { last_activity: null }),
    deck("new", { last_activity: "2026-11-21T08:00:00Z" }),
    deck("b-tie", { last_activity: "2026-11-10T00:00:00Z" }),
    deck("a-tie", { last_activity: "2026-11-10T00:00:00Z" }),
  ]);
  assert.deepEqual(ids(group), ["new", "a-tie", "b-tie", "old", "none"]);
});

test("acknowledged decks are sorted by acknowledgement date", () => {
  const mk = (id, at, last) => deck(id, { decided: 4, is_completed: true, ack_state: "valid", ack: { agent: "x", at }, last_activity: last });
  const groups = groupDecks([
    mk("first", "2026-11-18T00:00:00Z", "2026-11-21T00:00:00Z"),
    mk("second", "2026-11-20T00:00:00Z", "2026-11-01T00:00:00Z"),
  ]);
  assert.deepEqual(ids(groups[0]), ["second", "first"]);
});

test("relativeDate", () => {
  assert.equal(relativeDate("2026-11-21T11:59:40Z", NOW), "à l'instant");
  assert.equal(relativeDate("2026-11-21T11:55:00Z", NOW), "il y a 5 min");
  assert.equal(relativeDate("2026-11-21T09:00:00Z", NOW), "il y a 3 h");
  assert.equal(relativeDate("2026-11-20T09:00:00Z", NOW), "hier");
  assert.equal(relativeDate("2026-11-17T09:00:00Z", NOW), "il y a 4 j");
  assert.match(relativeDate("2026-10-12T09:00:00Z", NOW), /^12 oct\.$/);
  assert.match(relativeDate("2025-10-12T09:00:00Z", NOW), /^12 oct\. 2025$/);
  assert.equal(relativeDate("not a date", NOW), "");
  assert.equal(relativeDate(null, NOW), "");
  assert.equal(relativeDate("2026-11-21T13:00:00Z", NOW), "à l'instant");
});

// No emoji or decorative glyph left in the shipped front-end sources (icons are inline SVG).
test("no emoji or decorative glyph in public/ sources", () => {
  const dir = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "public");
  const bad = /[\u{1F000}-\u{1FAFF}☀-➿⬀-⯿←-⇿⏩-⏿️•✓✕×]/u;
  for (const file of readdirSync(dir).filter(f => /\.(js|css|html)$/.test(f))) {
    const lines = readFileSync(join(dir, file), "utf8").split("\n");
    lines.forEach((line, i) => assert.ok(!bad.test(line), `${file}:${i + 1} contains a glyph: ${line.trim().slice(0, 80)}`));
  }
});
