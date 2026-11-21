// Dock keyboard focus: after renderDock() rebuilds the buttons, focus must follow the action id.
// Runs the REAL renderDock source from public/app.js (sliced out, app.js itself touches the DOM at import time)
// against a tiny fake DOM. Run: node --test tests/js/dock_focus.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { escapeHtml } from "../../public/escape.js";

const PUBLIC_DIR = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "public");
const app = readFileSync(join(PUBLIC_DIR, "app.js"), "utf8");

// From the dock constants up to (excluding) showSummary: DIRECTION_SHORTCUTS, DOCK_*, renderDock, ariaKeyShortcuts.
const start = app.indexOf("const DIRECTION_SHORTCUTS");
const end = app.indexOf("async function showSummary");
assert.ok(start >= 0 && end > start, "renderDock source not found in app.js");
const dockSource = app.slice(start, end);

class FakeButton {
  constructor(actionId, doc) {
    this.dataset = { actionId };
    this.doc = doc;
  }
  addEventListener() {}
  closest(sel) { return sel === ".action-key-button" ? this : null; }
  focus() { this.doc.activeElement = this; }
}

// A dock whose innerHTML setter really parses the rendered markup (one FakeButton per data-action-id, in DOM order).
function makeDock(doc) {
  let buttons = [];
  return {
    set innerHTML(html) {
      buttons = [...html.matchAll(/data-action-id="([^"]*)"/g)].map(m => new FakeButton(m[1], doc));
    },
    querySelectorAll: () => buttons,
  };
}

function setup() {
  const doc = { activeElement: { closest: () => null } };
  const kineticDock = makeDock(doc);
  const dom = { kineticDock };
  const factory = new Function("document", "dom", "escapeHtml", "onCardDecide",
    `${dockSource}\nreturn renderDock;`);
  const renderDock = factory(doc, dom, escapeHtml, () => {});
  return { doc, kineticDock, renderDock };
}

// Action order (array) differs from the visual order (north, west, east, south).
const ACTIONS = [
  { id: "a-south", label: "Rejeter", direction: "south", color: "danger" },
  { id: "a-east", label: "Valider", direction: "east", color: "success" },
  { id: "a-north", label: "Plus tard", direction: "north" },
  { id: "a-west", label: "Passer", direction: "west" },
];
const visualIds = (dock) => [...dock.querySelectorAll()].map(b => b.dataset.actionId);

test("the dock is ordered north, west, east, south, not in action order", () => {
  const { kineticDock, renderDock } = setup();
  renderDock(ACTIONS);
  assert.deepEqual(visualIds(kineticDock), ["a-north", "a-west", "a-east", "a-south"]);
});

test("focus follows the action id even when visual order differs from action order", () => {
  const { doc, kineticDock, renderDock } = setup();
  renderDock(ACTIONS);
  // Focus "a-east": index 2 in the visual order, index 1 in the action array.
  const east = kineticDock.querySelectorAll().find(b => b.dataset.actionId === "a-east");
  east.focus();
  renderDock(ACTIONS); // new card, same actions: buttons are recreated
  const now = doc.activeElement;
  assert.equal(now.dataset.actionId, "a-east");
  assert.notEqual(now, east, "buttons must have been rebuilt");
  assert.ok(kineticDock.querySelectorAll().includes(now), "focus must be on a live button");
});

test("focus follows the id when the next card lists the actions in another order", () => {
  const { doc, kineticDock, renderDock } = setup();
  renderDock(ACTIONS);
  kineticDock.querySelectorAll().find(b => b.dataset.actionId === "a-west").focus();
  renderDock([...ACTIONS].reverse());
  assert.equal(doc.activeElement.dataset.actionId, "a-west");
});

test("falls back to an existing button when the focused action is gone", () => {
  const { doc, kineticDock, renderDock } = setup();
  renderDock(ACTIONS);
  kineticDock.querySelectorAll().find(b => b.dataset.actionId === "a-south").focus();
  renderDock(ACTIONS.filter(a => a.id !== "a-south"));
  assert.ok(kineticDock.querySelectorAll().includes(doc.activeElement), "fallback must be a live button");
});

test("no dock button focused: focus is not stolen", () => {
  const { doc, renderDock } = setup();
  const outside = { closest: () => null, focus() {} };
  doc.activeElement = outside;
  renderDock(ACTIONS);
  assert.equal(doc.activeElement, outside);
});
