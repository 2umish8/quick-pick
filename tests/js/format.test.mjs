// format.js helpers, api.js 401 handling, and source guards for the deck list UI (piste 1-5, 11)
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { formatDecisionSummary, parseCardLine, parseCardLines } from "../../public/format.js";

const PUBLIC_DIR = new URL("../../public/", import.meta.url);
const readPublic = name => readFileSync(new URL(name, PUBLIC_DIR), "utf8");

test("formatDecisionSummary: singular, plural, minutes rounded up, under a minute", () => {
  assert.equal(formatDecisionSummary(1, 0), "1 décision · moins d'une minute");
  assert.equal(formatDecisionSummary(4, 59), "4 décisions · moins d'une minute");
  assert.equal(formatDecisionSummary(4, 60), "4 décisions · ~1 min");
  assert.equal(formatDecisionSummary(4, 61), "4 décisions · ~2 min");
  assert.equal(formatDecisionSummary(12, 600), "12 décisions · ~10 min");
  assert.equal(formatDecisionSummary(0, undefined), "0 décisions · moins d'une minute");
});

test("parseCardLine: first ' :: ' splits, otherwise the whole line is the title", () => {
  assert.equal(parseCardLine("Migrer la base"), "Migrer la base");
  assert.deepEqual(parseCardLine("a :: b"), { title: "a", description: "b" });
  assert.deepEqual(parseCardLine("  a :: b :: c  "), { title: "a", description: "b :: c" });
  assert.equal(parseCardLine("a::b"), "a::b");
  assert.equal(parseCardLine(":: b"), ":: b");
  assert.equal(parseCardLine("a ::"), "a ::");
  assert.equal(parseCardLine("a ::   "), "a ::");
});

test("api.js: a non-JSON 401 (proxy) gives 'Accès expiré' and never prompts for a token", async () => {
  globalThis.sessionStorage = { getItem: () => null, setItem() {}, removeItem() {} };
  globalThis.localStorage = globalThis.sessionStorage;
  let prompted = 0;
  globalThis.window = { prompt: () => { prompted += 1; return "x"; } };
  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    return new Response("<html>Sign in</html>", { status: 401, headers: { "content-type": "text/html" } });
  };
  const { request } = await import("../../public/api.js");
  await assert.rejects(() => request("/api/decks"), /Accès expiré : rechargez la page/);
  assert.equal(prompted, 0);
  assert.equal(calls, 1);
});

test("api.js: a JSON error exposes its code on the thrown error", async () => {
  globalThis.fetch = async () => new Response(JSON.stringify({ error: "Maximum 200 cartes par deck", code: "too_many_items" }), {
    status: 400, headers: { "content-type": "application/json" },
  });
  const { postItems } = await import("../../public/api.js");
  await assert.rejects(() => postItems("d", ["a"]), err => err.code === "too_many_items");
});

test("deck list: a deck description is escaped and counters go through escapeHtml", () => {
  const app = readPublic("app.js");
  const item = app.slice(app.indexOf("function deckItemHtml"), app.indexOf("async function runDeckAction"));
  assert.match(item, /const desc = escapeHtml\(deck\.description \|\| ""\)/);
  assert.match(item, /escapeHtml\(String\(deck\.decided\)\)\}\/\$\{escapeHtml\(String\(deck\.total\)\)/);
  assert.ok(!/\$\{deck\.description\}/.test(item));
});

test("deck list: invalid deck shows only 'Supprimer' with the id from the list, and is not playable", () => {
  const app = readPublic("app.js");
  const item = app.slice(app.indexOf("function deckItemHtml"), app.indexOf("async function runDeckAction"));
  assert.match(item, /deck\.invalid\s*\?\s*`<button type="button" class="deck-act danger" data-act="delete"(?: title="Supprimer")?>Supprimer<\/button>`/);
  assert.match(item, /deck\.invalid\s*\n?\s*\?\s*`<button type="button" class="deck-item-card"[^`]*disabled>`/);
  // The delete handler sends the id read from the list entry (data-deck-id), never anything from the file body.
  assert.match(app, /const deckId = item\.dataset\.deckId/);
});

test("deck list: reset and delete need a second click, one armed button at a time, 4 s timeout", () => {
  const app = readPublic("app.js");
  assert.match(app, /CONFIRM_DELAY_MS = 4000/);
  assert.match(app, /button\.textContent = "Confirmer \?"/);
  const handler = app.slice(app.indexOf("function onDeckAction"), app.indexOf("dom.deckList.addEventListener"));
  // First click only arms; the API call is reached only after the armed check passes.
  assert.ok(handler.indexOf("arm(button") < handler.indexOf("postReset(deckId)"));
  assert.ok(handler.indexOf("arm(button") < handler.indexOf("postDelete(deckId)"));
  assert.match(handler, /armed\?\.button !== button/);
  assert.match(app, /async function loadDecks\(\) \{\s*disarm\(\);/);
  assert.match(handler, /Une copie reste récupérable par l'agent\./);
});

test("stack.js: touchcancel and pointercancel never validate a swipe", () => {
  const stack = readPublic("stack.js");
  assert.match(stack, /"touchcancel", \(\) => onEnd\(true\)/);
  assert.match(stack, /"pointercancel", e => finishMouse\(e, true\)/);
  assert.match(stack, /if \(cancelled\) dir = null;/);
});

test("parseCardLines: one card per non-empty trimmed line, shared by the create form and the add zone", () => {
  assert.deepEqual(parseCardLines("  a \n\n b :: c \n   \nd"), ["a", { title: "b", description: "c" }, "d"]);
  assert.deepEqual(parseCardLines(""), []);
  assert.deepEqual(parseCardLines(undefined), []);
  assert.match(readPublic("app.js"), /parseCardLines\(input\.value\)/);
  assert.match(readPublic("deck-form.js"), /parseCardLines\(/);
  assert.doesNotMatch(readPublic("deck-form.js") + readPublic("app.js"), /\.split\("\\n"\)/);
});
