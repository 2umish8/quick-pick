// MOW-188 — front-end mobile & accessibility regressions.
// Run: node --test tests/frontend_a11y.test.mjs  (Node >= 22, stdlib only)
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const PUBLIC_DIR = join(dirname(fileURLToPath(import.meta.url)), "..", "public");
const read = (name) => readFileSync(join(PUBLIC_DIR, name), "utf8");

test("the action dock stays usable by finger under 640px", () => {
  const css = read("cards.css");
  const mobile = css.match(/@media \(max-width: 640px\)[\s\S]*$/)?.[0] || "";
  assert.ok(!/display:\s*none\s*!important/.test(mobile),
    "the mobile media query must not hide the dock: decisions cannot be swipe-only");
  assert.match(mobile, /\.kinetic-dock\s*\{[^}]*flex-wrap:\s*wrap/);
  assert.match(mobile, /\.action-key-button\s*\{[^}]*min-height:\s*(4[4-9]|[5-9]\d|\d{3,})px/);
  assert.match(css, /\.comment-input\s*\{[^}]*height:\s*(4[4-9]|[5-9]\d|\d{3,})px/);
});

test("clickable deck and logo zones are real buttons", () => {
  const html = read("index.html");
  assert.match(html, /<button type="button" class="logo-zone" id="logo-zone"[^>]*aria-label="Retour aux decks">/);
  const appJs = read("app.js");
  assert.match(appJs, /<button type="button" class="deck-item-card"/);
  assert.ok(!/<div class="deck-item-card"/.test(appJs), "deck cards must not stay divs");
});

test("a global :focus-visible ring exists and no stylesheet resets outlines", () => {
  assert.match(read("style.css"), /:focus-visible\s*\{[^}]*outline:/);
  for (const file of ["style.css", "cards.css", "drawer.css"]) {
    assert.ok(!/outline:\s*none/.test(read(file)), `${file} still disables outlines`);
  }
});
