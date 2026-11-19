// Retour sur l'onglet (piste 7) : gardes du rafraîchissement silencieux et mode silent de request().
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { request } from "../../public/api.js";

const app = readFileSync(new URL("../../public/app.js", import.meta.url), "utf8");
const jsonResponse = (status, body) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

test("request silent: 401 ne déclenche aucun prompt et lève avec le statut", async () => {
  const original = globalThis.fetch;
  let calls = 0;
  let prompted = false;
  globalThis.window = { prompt: () => { prompted = true; return "x"; } };
  globalThis.fetch = () => { calls += 1; return Promise.resolve(jsonResponse(401, { error: "unauthorized", detail: "non" })); };
  try {
    await assert.rejects(() => request("/api/decks", { silent: true }), err => err.status === 401);
    assert.equal(calls, 1, "pas de rejeu");
    assert.equal(prompted, false);
  } finally {
    globalThis.fetch = original;
    delete globalThis.window;
  }
});

test("request silent n'est pas transmis à fetch", async () => {
  const original = globalThis.fetch;
  let seen;
  globalThis.fetch = (_url, options) => { seen = options; return Promise.resolve(jsonResponse(200, {})); };
  try {
    await request("/api/decks", { silent: true });
    assert.equal("silent" in seen, false);
  } finally {
    globalThis.fetch = original;
  }
});

test("request: un 404 porte status 404", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = () => Promise.resolve(jsonResponse(404, { error: "Deck introuvable" }));
  try {
    await assert.rejects(() => request("/api/decks/x", { silent: true }), err => err.status === 404);
  } finally {
    globalThis.fetch = original;
  }
});

function body(start, end) {
  const i = app.indexOf(start);
  assert.ok(i >= 0, `${start} introuvable`);
  return app.slice(i, app.indexOf(end, i + start.length));
}

test("retour d'onglet: visibilitychange visible, focus rapproché ignoré, pas de minuterie", () => {
  assert.match(app, /addEventListener\("visibilitychange"[\s\S]*visibilityState === "visible"/);
  assert.match(app, /isFocus && now - lastReturnAt < 1000\) return/);
  const section = app.slice(app.indexOf("// Retour sur l'onglet"));
  assert.doesNotMatch(section, /setInterval/);
});

test("vue jeu: gardes (requête, panneaux, note) et comparaison id/decided/pending", () => {
  const guard = body("function gameRefreshAllowed", "\n}\n");
  for (const needle of ["!state.isProcessing", "panelsClosed()", "!dom.commentInput.value.trim()"]) assert.ok(guard.includes(needle), needle);
  const panels = body("function panelsClosed", "\n}\n");
  assert.match(panels, /deck-drawer"\)\?\.classList\.contains\("open"\)/);
  assert.match(panels, /settings-modal"\)\?\.hidden !== false/);
  const refresh = body("async function refreshOnReturn", "\nlet lastReturnAt");
  assert.match(refresh, /fetchDeckState\(deckId, \{ silent: true \}\)/);
  for (const f of ["current_item?.id", "decided_count", "pending_count"]) assert.ok(refresh.includes(f), f);
  assert.match(refresh, /seq !== refreshSeq/);
  assert.match(refresh, /err\.status === 404[\s\S]*loadDecks\(\)/);
  // is_completed passe par handleDeckState (même chemin), jamais de bandeau.
  assert.match(refresh, /handleDeckState\(fresh\)/);
  assert.doesNotMatch(refresh, /showErrorBanner/);
});

test("vue liste: remplacement du DOM seulement sans zone d'ajout ouverte ni bouton armé", () => {
  const guard = body("function listRefreshAllowed", "\n}\n");
  assert.match(guard, /!armed/);
  assert.match(guard, /\.deck-item-add:not\(\[hidden\]\)/);
  const refresh = body("async function refreshOnReturn", "\nlet lastReturnAt");
  assert.match(refresh, /fetchDecks\(\{ silent: true \}\)[\s\S]*renderDeckList/);
});
