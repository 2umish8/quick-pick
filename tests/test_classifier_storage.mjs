// Tests de stockage de la clé BYOK (public/classifier.js) — run: node --test tests/
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

function makeStorage(initial = {}) {
  const map = new Map(Object.entries(initial));
  return {
    getItem: (key) => (map.has(key) ? map.get(key) : null),
    setItem: (key, value) => map.set(key, String(value)),
    removeItem: (key) => map.delete(key),
    dump: () => Object.fromEntries(map),
  };
}

// classifier.js is plain ESM without import/export of any asset: loading it from a
// data URL keeps the repo dependency-free and lets us stub the storage globals.
async function loadClassifier(localStorage, sessionStorage) {
  globalThis.localStorage = localStorage;
  globalThis.sessionStorage = sessionStorage;
  const source = await readFile(new URL("../public/classifier.js", import.meta.url), "utf8");
  return import(`data:text/javascript,${encodeURIComponent(source)}`);
}

const STORAGE_KEY = "quickpick_classifier_cfg";

test("no stored config falls back to a session-only default", async () => {
  const local = makeStorage();
  const session = makeStorage();
  const { getClassifierConfig } = await loadClassifier(local, session);

  assert.deepEqual(getClassifierConfig(), {
    provider: "openai",
    endpoint: "",
    apiKey: "",
    model: "gpt-4o-mini",
    enabled: false,
    directMode: false,
    remember: false,
  });
});

test("a key saved before the session default stays usable and is flagged as remembered", async () => {
  const local = makeStorage({
    [STORAGE_KEY]: JSON.stringify({
      provider: "openai",
      endpoint: "https://api.openai.com/v1",
      apiKey: "sk-legacy",
      model: "gpt-4o-mini",
      enabled: true,
    }),
  });
  const session = makeStorage();
  const { getClassifierConfig } = await loadClassifier(local, session);

  const cfg = getClassifierConfig();
  assert.equal(cfg.apiKey, "sk-legacy");
  assert.equal(cfg.remember, true);
  assert.equal(cfg.enabled, true);
});

test("saving without opt-in keeps the key in sessionStorage and clears localStorage", async () => {
  const local = makeStorage({ [STORAGE_KEY]: JSON.stringify({ apiKey: "sk-old", remember: true }) });
  const session = makeStorage();
  const { saveClassifierConfig, getClassifierConfig } = await loadClassifier(local, session);

  saveClassifierConfig({ provider: "openai", endpoint: "https://api.openai.com/v1", apiKey: " sk-new ", model: "gpt-4o-mini", enabled: true, remember: false });

  assert.equal(JSON.parse(session.dump()[STORAGE_KEY]).apiKey, "sk-new");
  assert.equal(local.getItem(STORAGE_KEY), null);
  const cfg = getClassifierConfig();
  assert.equal(cfg.apiKey, "sk-new");
  assert.equal(cfg.remember, false);
});

test("opting in to device memory moves the key to localStorage and drops the session copy", async () => {
  const local = makeStorage();
  const session = makeStorage();
  const { saveClassifierConfig, getClassifierConfig } = await loadClassifier(local, session);

  saveClassifierConfig({ provider: "openai", endpoint: "https://api.openai.com/v1", apiKey: "sk-persist", model: "gpt-4o-mini", enabled: true, remember: true });

  assert.equal(JSON.parse(local.dump()[STORAGE_KEY]).apiKey, "sk-persist");
  assert.equal(session.getItem(STORAGE_KEY), null);
  assert.equal(getClassifierConfig().remember, true);
});

test("forgetting the key empties it in both stores", async () => {
  const local = makeStorage();
  const session = makeStorage();
  const { saveClassifierConfig, getClassifierConfig } = await loadClassifier(local, session);

  saveClassifierConfig({ provider: "openai", endpoint: "https://api.openai.com/v1", apiKey: "sk-persist", model: "gpt-4o-mini", enabled: true, remember: true });
  saveClassifierConfig({ ...getClassifierConfig(), apiKey: "", remember: false });

  const cfg = getClassifierConfig();
  assert.equal(cfg.apiKey, "");
  assert.equal(cfg.remember, false);
  assert.equal(JSON.parse(session.dump()[STORAGE_KEY]).apiKey, "");
  assert.equal(local.getItem(STORAGE_KEY), null);
});

test("a corrupted config falls back to the safe default instead of throwing", async () => {
  const local = makeStorage({ [STORAGE_KEY]: "{not json" });
  const session = makeStorage();
  const { getClassifierConfig } = await loadClassifier(local, session);

  assert.equal(getClassifierConfig().apiKey, "");
  assert.equal(getClassifierConfig().remember, false);
});