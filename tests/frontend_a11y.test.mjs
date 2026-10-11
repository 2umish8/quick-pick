// MOW-188 — front-end mobile & accessibility regressions.
// Run: node --test tests/frontend_a11y.test.mjs  (Node >= 22, stdlib only)
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const PUBLIC_DIR = join(dirname(fileURLToPath(import.meta.url)), "..", "public");
const read = (name) => readFileSync(join(PUBLIC_DIR, name), "utf8");

/* ------------------------------------------------------------------ *
 * Minimal fake DOM: just enough for public/deck-drawer.js to run.
 * ------------------------------------------------------------------ */
class FakeEl {
  constructor(id = "") {
    this.id = id;
    this.attrs = {};
    this.isConnected = true;
    this.dataset = {};
    this.style = {};
    this.textContent = "";
    this.classes = new Set();
    this.listeners = new Map();
    this.classList = {
      add: (c) => this.classes.add(c),
      remove: (c) => this.classes.delete(c),
      contains: (c) => this.classes.has(c),
      toggle: (c, on) => (on ? this.classes.add(c) : this.classes.delete(c)),
    };
  }
  setAttribute(k, v) { this.attrs[k] = v; }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  addEventListener(type, fn) {
    if (!this.listeners.has(type)) this.listeners.set(type, []);
    this.listeners.get(type).push(fn);
  }
  focus() { globalThis.document.activeElement = this; }
  querySelector() { return null; }
  querySelectorAll() { return []; }
}

function makeDocument(ids) {
  const nodes = new Map(ids.map(id => [id, new FakeEl(id)]));
  return {
    nodes,
    activeElement: new FakeEl("body"),
    getElementById: (id) => nodes.get(id) || null,
    addEventListener() {},
  };
}

async function loadDrawerModule() {
  const ids = [
    "deck-drawer", "drawer-panel", "drawer-backdrop", "drawer-close-btn",
    "tab-btn-pending", "tab-btn-decided", "drawer-items-list", "header-progress-pill",
  ];
  const fakeDocument = makeDocument(ids);
  const drawer = fakeDocument.nodes.get("deck-drawer");
  const panel = fakeDocument.nodes.get("drawer-panel");
  drawer.querySelector = (sel) => (sel === ".drawer-panel" ? panel : null);
  globalThis.document = fakeDocument;
  return {
    drawer,
    panel,
    fakeDocument,
    mod: await import(`../public/deck-drawer.js?case=${Math.random()}`),
  };
}

test("openDrawer exposes the drawer to assistive tech and moves focus inside", async () => {
  const { drawer, panel, fakeDocument, mod } = await loadDrawerModule();
  const opener = new FakeEl("header-progress-pill");
  fakeDocument.activeElement = opener;

  mod.openDrawer();

  assert.equal(drawer.getAttribute("aria-hidden"), "false");
  assert.ok(drawer.classList.contains("open"));
  assert.equal(fakeDocument.activeElement, panel, "focus must land inside the dialog");
});

test("closeDrawer re-hides the drawer and restores the previously focused element", async () => {
  const { drawer, fakeDocument, mod } = await loadDrawerModule();
  const opener = new FakeEl("header-progress-pill");
  fakeDocument.activeElement = opener;

  mod.openDrawer();
  mod.closeDrawer();

  assert.equal(drawer.getAttribute("aria-hidden"), "true");
  assert.ok(!drawer.classList.contains("open"));
  assert.equal(fakeDocument.activeElement, opener, "focus must return to the trigger");
});

test("closeDrawer is a no-op when the drawer is already closed", async () => {
  const { drawer, fakeDocument, mod } = await loadDrawerModule();
  const body = new FakeEl("body");
  fakeDocument.activeElement = body;

  mod.closeDrawer(); // e.g. Escape pressed while the drawer is closed

  assert.equal(fakeDocument.activeElement, body, "must not steal focus");
  assert.equal(drawer.getAttribute("aria-hidden"), null);
});

test("drawer markup is a labelled modal dialog", () => {
  const html = read("index.html");
  assert.match(html, /id="deck-drawer"[^>]*aria-hidden="true"/);
  assert.match(
    html,
    /<div class="drawer-panel"[^>]*role="dialog"[^>]*aria-modal="true"[^>]*aria-label="[^"]+"[^>]*tabindex="-1"/,
  );
});

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

test("decision actions are announced as a labelled group with keyboard shortcuts", () => {
  assert.match(read("index.html"), /id="kinetic-dock" role="group" aria-label="Décider pour cette carte"/);
  const appJs = read("app.js");
  assert.match(appJs, /aria-keyshortcuts=/);
  assert.match(appJs, /DIRECTION_SHORTCUTS/);
  // The dock is rebuilt after every decision: focus must follow.
  assert.match(appJs, /buttons\[Math\.min\(focusedIndex, buttons\.length - 1\)\]\.focus\(\)/);
});
