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
const source = await readFile(new URL("../public/classifier.js", import.meta.url), "utf8");

async function loadClassifier(localStorage, sessionStorage) {
  globalThis.localStorage = localStorage;
  globalThis.sessionStorage = sessionStorage;
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

// --- Direct browser mode (key never reaches the server) ---

function loadClassifierWithFetch(local = makeStorage(), session = makeStorage(), fetchImpl = () => { throw new Error("no fetch"); }) {
  globalThis.localStorage = local;
  globalThis.sessionStorage = session;
  globalThis.fetch = fetchImpl;
  return import(`data:text/javascript,${encodeURIComponent(source)}`);
}

test("direct mode stays off unless the user opts in", async () => {
  const local = makeStorage();
  const session = makeStorage();
  const { getClassifierConfig, useDirectMode } = await loadClassifierWithFetch(local, session);

  assert.equal(useDirectMode(getClassifierConfig()), false);

  session.setItem(STORAGE_KEY, JSON.stringify({ provider: "openai", directMode: false }));
  assert.equal(useDirectMode(getClassifierConfig()), false);

  session.setItem(STORAGE_KEY, JSON.stringify({ provider: "openai", directMode: true }));
  assert.equal(useDirectMode(getClassifierConfig()), true);

  session.setItem(STORAGE_KEY, JSON.stringify({ provider: "custom", directMode: true }));
  assert.equal(useDirectMode(getClassifierConfig()), false, "custom webhooks have no CORS contract");
});

test("direct prediction posts to the provider without touching the server", async () => {
  const session = makeStorage({
    [STORAGE_KEY]: JSON.stringify({
      provider: "openai",
      endpoint: "https://api.openai.com/v1",
      apiKey: "sk-direct",
      model: "gpt-4o-mini",
      enabled: true,
      directMode: true,
      remember: false,
    }),
  });
  const calls = [];
  const fetchImpl = async (url, options) => {
    calls.push({ url, options });
    return {
      ok: true,
      status: 200,
      statusText: "OK",
      json: async () => ({ choices: [{ message: { content: '{"action": "approve", "confidence": 0.87, "reasoning": "clair"}' } }] }),
    };
  };
  const { fetchItemPrediction } = await loadClassifierWithFetch(makeStorage(), session, fetchImpl);

  const prediction = await fetchItemPrediction(
    { id: "item-1", title: "Titre", bullets: ["a"] },
    [{ id: "approve", label: "Conserver" }, { id: "reject", label: "Élaguer" }],
  );

  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "https://api.openai.com/v1/chat/completions");
  assert.equal(calls[0].options.headers.Authorization, "Bearer sk-direct");
  const sentBody = JSON.parse(calls[0].options.body);
  assert.equal(sentBody.model, "gpt-4o-mini");
  assert.equal(sentBody.messages.length, 2);
  assert.match(sentBody.messages[1].content, /"candidate_actions":\["approve","reject"\]/);
  assert.deepEqual(prediction, { actionId: "approve", label: "Conserver", confidence: 87, reasoning: "clair" });
});

test("an endpoint already ending with /chat/completions is not doubled", async () => {
  const calls = [];
  const fetchImpl = async (url) => {
    calls.push(url);
    return { ok: true, status: 200, statusText: "OK", json: async () => ({ choices: [{ message: { content: '{"action": "approve"}' } }] }) };
  };
  const session = makeStorage({
    [STORAGE_KEY]: JSON.stringify({
      provider: "openai",
      endpoint: "http://localhost:11434/v1/chat/completions",
      apiKey: "Bearer prefixed-key",
      model: "llama3.2",
      enabled: true,
      directMode: true,
      remember: false,
    }),
  });
  const { fetchItemPrediction } = await loadClassifierWithFetch(makeStorage(), session, fetchImpl);

  await fetchItemPrediction({ id: "item-1", title: "T" }, [{ id: "approve", label: "OK" }]);

  assert.equal(calls[0], "http://localhost:11434/v1/chat/completions");
});

test("a provider answer without a JSON decision is a failure, not a fake suggestion", async () => {
  const fetchImpl = async () => ({
    ok: true,
    status: 200,
    statusText: "OK",
    json: async () => ({ choices: [{ message: { content: "I cannot decide" } }] }),
  });
  const session = makeStorage({
    [STORAGE_KEY]: JSON.stringify({
      provider: "openai", endpoint: "https://api.openai.com/v1", apiKey: "k",
      model: "gpt-4o-mini", enabled: true, directMode: true, remember: false,
    }),
  });
  const { fetchItemPrediction } = await loadClassifierWithFetch(makeStorage(), session, fetchImpl);

  assert.equal(await fetchItemPrediction({ id: "item-1", title: "T" }, [{ id: "approve", label: "OK" }]), null);
});

test("proxy mode stays the default transport", async () => {
  const calls = [];
  const fetchImpl = async (url, options) => {
    calls.push({ url, options });
    return { ok: true, status: 200, statusText: "OK", json: async () => ({ ok: true, data: { prediction: "reject", confidence: 0.4 } }) };
  };
  const session = makeStorage({
    [STORAGE_KEY]: JSON.stringify({
      provider: "openai", endpoint: "https://api.openai.com/v1", apiKey: "k",
      model: "gpt-4o-mini", enabled: true, directMode: false, remember: false,
    }),
  });
  const { fetchItemPrediction } = await loadClassifierWithFetch(makeStorage(), session, fetchImpl);

  const prediction = await fetchItemPrediction({ id: "item-1", title: "T" }, [{ id: "reject", label: "Élaguer" }]);

  assert.equal(calls[0].url, "/api/classifier/predict");
  const sentBody = JSON.parse(calls[0].options.body);
  assert.equal(sentBody.api_key, "k");
  assert.equal(sentBody.payload.provider, "openai");
  assert.equal(sentBody.payload.model, "gpt-4o-mini");
  assert.deepEqual(prediction, { actionId: "reject", label: "Élaguer", confidence: 40, reasoning: null });
});