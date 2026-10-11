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
