// Garde-fous de public/app.js : raccourcis, échecs réseau, adresse mal encodée.
// Run: node --test tests/js/app_guards.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const PUBLIC_DIR = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "public");
const app = readFileSync(join(PUBLIC_DIR, "app.js"), "utf8");

function body(startMarker, endMarker) {
  const start = app.indexOf(startMarker);
  assert.ok(start >= 0, `${startMarker} introuvable`);
  const end = app.indexOf(endMarker, start + startMarker.length);
  return app.slice(start, end > 0 ? end : undefined);
}

test("les raccourcis de jeu ne fonctionnent pas derrière un panneau ouvert", () => {
  const handler = body('window.addEventListener("keydown"', "const currentActions");
  assert.match(handler, /deck-drawer"\)\?\.classList\.contains\("open"\)\) return/);
  assert.match(handler, /settings-modal"\)\?\.hidden === false\) return/);
  // Le garde précède toute action (annuler, passer, décider).
  assert.ok(handler.indexOf("deck-drawer") < handler.indexOf("triggerUndo"));
  assert.ok(handler.indexOf("settings-modal") < handler.indexOf("onCardSkip"));
});

test("une décision qui échoue remet la carte à l'écran et affiche une erreur", () => {
  const decide = body("async function onCardDecide", "async function onCardSkip");
  assert.match(decide, /catch \(err\)[\s\S]*restoreCurrentCard\(\)[\s\S]*showErrorBanner/);
  assert.match(decide, /if \(state\.isProcessing\) \{\s*restoreCurrentCard\(\)/);
});

test("passer, annuler et la synthèse signalent leurs échecs", () => {
  for (const name of ["onCardSkip", "triggerUndo"]) {
    const fn = body(`async function ${name}`, "\n}\n");
    assert.match(fn, /catch \(err\)[\s\S]*showErrorBanner/, `${name} sans bandeau d'erreur`);
  }
  assert.match(body("async function showSummary", "const breakdownHtml"), /catch \(err\)[\s\S]*showErrorBanner/);
});

test("une adresse mal encodée ne fait pas planter le chargement", () => {
  const fn = body("function getInitialDeckId", "\n}\n");
  assert.match(fn, /try \{ return decodeURIComponent\(kept\[0\]\); \} catch \{ return null; \}/);
});

test("ouvrir un deck depuis un clic ou l'adresse ne laisse pas de promesse rejetée", () => {
  assert.match(app, /function openDeck\(deckId\)[\s\S]*startDeck\(deckId\)\.catch/);
  assert.doesNotMatch(app, /addEventListener\("click", \(\) => startDeck/);
  assert.doesNotMatch(app, /onCreated: \(deckId\) => startDeck/);
});
