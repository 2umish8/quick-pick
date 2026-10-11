// Front-end checks that need a JS runtime but no DOM (MOW-188)
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { escapeHtml } from "../../public/escape.js";

const PUBLIC_DIR = new URL("../../public/", import.meta.url);
const readPublic = name => readFileSync(new URL(name, PUBLIC_DIR), "utf8");

// A bare deck field interpolated straight into an HTML template, e.g. ${act.id}.
// Guarded usages such as ${act.key ? ... : ""} are fine as long as the value itself is escaped.
const RAW_DECK_FIELD = /\$\{\s*(?:act|action|deck|item|entry|card|badge|b|it)\.[\w$]+\s*\}/g;

test("escapeHtml neutralises markup and attribute delimiters", () => {
  assert.equal(escapeHtml('<img src=x onerror="alert(1)">'), "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;");
  assert.equal(escapeHtml("a & b"), "a &amp; b");
  // Never decodes an already escaped payload.
  assert.equal(escapeHtml("l&#39;été&#39;"), "l&amp;#39;été&amp;#39;");
  assert.equal(escapeHtml(null), "");
  assert.equal(escapeHtml(undefined), "");
  assert.equal(escapeHtml(0), "0");
});

test("no deck field reaches an HTML template unescaped", () => {
  for (const file of ["app.js", "stack.js", "deck-drawer.js"]) {
    const found = readPublic(file).match(RAW_DECK_FIELD);
    assert.equal(found, null, `${file} injects raw deck fields: ${found}`);
  }
});

test("the action dock escapes every action field", () => {
  const app = readPublic("app.js");
  const dock = app.slice(app.indexOf("function renderDock"), app.indexOf("async function showSummary"));
  for (const escaped of ["escapeHtml(act.id)", "escapeHtml(act.color", "escapeHtml(act.label)", "escapeHtml(String(act.key).toUpperCase())"]) {
    assert.ok(dock.includes(escaped), `renderDock must escape with ${escaped}`);
  }
});
