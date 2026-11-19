// La lecture d'une carte longue ne doit pas devenir un swipe.
// Run: node --test tests/js/card_scroll.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const PUBLIC_DIR = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "public");
const stack = readFileSync(join(PUBLIC_DIR, "stack.js"), "utf8");
const css = readFileSync(join(PUBLIC_DIR, "cards.css"), "utf8");

test("un mouvement encore non classé ne déplace pas la carte", () => {
  const move = stack.slice(stack.indexOf('cardEl.addEventListener("touchmove"'));
  const handler = move.slice(0, move.indexOf("}, { passive: false }"));
  const classify = handler.indexOf("gestureMode === null");
  const drag = handler.indexOf("onMove(");
  assert.ok(classify > 0 && drag > classify, "le swipe ne commence qu'après le classement du geste");
  assert.match(handler, /gestureMode !== "swipe"/);
});

test("le texte long défile dans la carte, pas dans un vide flex", () => {
  assert.match(css, /\.bullet-list \{[^}]*margin-top: 12px/);
  assert.doesNotMatch(css, /\.bullet-list \{[^}]*margin-top: auto/);
  assert.match(css, /body:has\(#view-game:not\(\[hidden\]\)\)[\s\S]*overflow: hidden/);
});
