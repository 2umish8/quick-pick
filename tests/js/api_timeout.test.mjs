// Front-end checks that need a JS runtime but no DOM (MOW-188)
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { request } from "../../public/api.js";

const PUBLIC_DIR = new URL("../../public/", import.meta.url);
const readPublic = name => readFileSync(new URL(name, PUBLIC_DIR), "utf8");

function stubFetch(handler) {
  const original = globalThis.fetch;
  globalThis.fetch = handler;
  return () => { globalThis.fetch = original; };
}

test("request always hands an AbortSignal to fetch", async () => {
  let seenSignal = null;
  const restore = stubFetch((_url, options) => {
    seenSignal = options.signal;
    return Promise.resolve(new Response('{"decks": []}', { status: 200, headers: { "content-type": "application/json" } }));
  });
  try {
    assert.deepEqual(await request("/api/decks"), { decks: [] });
    assert.ok(seenSignal instanceof AbortSignal, "fetch must receive an AbortSignal");
  } finally {
    restore();
  }
});

test("a hanging request rejects instead of pending forever", async () => {
  const restore = stubFetch((_url, options) => new Promise((_resolve, reject) => {
    options.signal.addEventListener("abort", () => reject(options.signal.reason));
  }));
  // AbortSignal.timeout() timers are unref'd and would not keep the event loop alive here.
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(new DOMException("Timeout", "TimeoutError")), 20);
  try {
    await assert.rejects(() => request("/api/decks", { signal: controller.signal }), /timeout/i);
  } finally {
    clearTimeout(timer);
    restore();
  }
});

test("the error banner is announced and offers a retry button", () => {
  const html = readPublic("index.html");
  assert.match(html, /id="error-banner"[^>]*role="alert"|role="alert"[^>]*id="error-banner"/);
  assert.match(html, /id="error-banner-retry"[^>]*>Réessayer</);
});

test("loadDecks catches request failures and shows the banner", () => {
  const app = readPublic("app.js");
  const body = app.slice(app.indexOf("async function loadDecks"), app.indexOf("async function startDeck"));
  assert.match(body, /try \{[\s\S]*await fetchDecks\(\)[\s\S]*\} catch \(err\) \{[\s\S]*showErrorBanner\(/);
});
