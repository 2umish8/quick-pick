// Classifier module: universal AI configuration & suggestions (OpenAI, Ollama, Groq, Custom)
import { authFetch } from "./api.js";

const STORAGE_KEY = "quickpick_classifier_cfg";

// Default config: session-only. The API key never leaves the browser storage
// unless the user opts in to device memory, which writes it to localStorage.
const DEFAULT_CONFIG = {
  provider: "openai",
  endpoint: "",
  apiKey: "",
  model: "gpt-4o-mini",
  enabled: false,
  directMode: false,
  remember: false,
};

const KEY_HINT_SESSION = "Clé conservée dans cette session (sessionStorage) : effacée à la fermeture de l'onglet.";
const KEY_HINT_DEVICE = "Clé mémorisée sur cet appareil (localStorage) : elle survit à la fermeture, tant que vous ne l'oubliez pas.";
const DIRECT_HINT_PROXY = "Désactivé, l'app passe par le serveur quick-pick (par défaut). Activé, la clé reste dans le navigateur : le fournisseur doit autoriser les appels CORS et l'origine du serveur doit être autorisée par QUICK_PICK_CSP_CONNECT_SRC.";
const DIRECT_HINT_CUSTOM = "Le mode direct ne s'applique qu'aux API compatibles OpenAI : ce webhook passe par le serveur quick-pick.";

function normalizeConfig(parsed) {
  return {
    provider: parsed.provider || DEFAULT_CONFIG.provider,
    endpoint: parsed.endpoint || "",
    apiKey: parsed.apiKey || "",
    model: parsed.model || DEFAULT_CONFIG.model,
    enabled: Boolean(parsed.enabled),
    directMode: Boolean(parsed.directMode),
    // Configs saved before the session default have no flag and were always persistent.
    remember: "remember" in parsed ? Boolean(parsed.remember) : true,
  };
}

export function getClassifierConfig() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY) || localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...DEFAULT_CONFIG };
    return normalizeConfig(JSON.parse(raw));
  } catch {
    return { ...DEFAULT_CONFIG };
  }
}

export function saveClassifierConfig(cfg) {
  const blob = JSON.stringify(normalizeConfig({
    provider: cfg.provider,
    endpoint: (cfg.endpoint || "").trim(),
    apiKey: (cfg.apiKey || "").trim(),
    model: cfg.model,
    enabled: cfg.enabled,
    directMode: cfg.directMode,
    remember: cfg.remember,
  }));
  // Single source of truth: the other store is cleared so a forgotten key
  // cannot come back on the next read.
  if (cfg.remember) {
    localStorage.setItem(STORAGE_KEY, blob);
    sessionStorage.removeItem(STORAGE_KEY);
  } else {
    sessionStorage.setItem(STORAGE_KEY, blob);
    localStorage.removeItem(STORAGE_KEY);
  }
}

export async function testClassifierConnection(endpoint, apiKey, provider, model) {
  const resp = await authFetch("/api/classifier/test", {
    method: "POST",
    headers: { "Content-Type": "application/json" }, // authFetch adds the token
    body: JSON.stringify({
      endpoint: (endpoint || "").trim(),
      api_key: (apiKey || "").trim(),
      provider: provider || "openai",
      model: model || "gpt-4o-mini",
    }),
  });
  return await resp.json();
}

function buildDirectHeaders(apiKey) {
  const headers = { "Content-Type": "application/json" };
  const key = (apiKey || "").trim();
  if (key) headers.Authorization = key.toLowerCase().startsWith("bearer ") ? key : `Bearer ${key}`;
  return headers;
}

function buildDirectUrl(endpoint) {
  const base = (endpoint || "").trim().replace(/\/+$/, "");
  return base.endsWith("/chat/completions") ? base : `${base}/chat/completions`;
}

// Mirrors the OpenAI branch of classifier_proxy.py so both transports ask the model the same way.
function buildDirectBody(payload, model) {
  const candidateActions = payload.candidate_actions || [];
  const systemPrompt = (
    "You are a card decision classifier. Analyze the item and pick the single best action "
    + `from candidate_actions: ${candidateActions}. `
    + 'Return strictly a JSON object: {"action": "<action_id>", "confidence": 0.9, "reasoning": "brief reason"}'
  );
  return {
    model: model || DEFAULT_CONFIG.model,
    messages: [
      { role: "system", content: systemPrompt },
      {
        role: "user",
        content: JSON.stringify({
          title: payload.title || "",
          description: payload.description || "",
          bullets: payload.bullets || [],
          candidate_actions: candidateActions,
        }),
      },
    ],
    temperature: 0.2,
  };
}

// Unwraps the OpenAI envelope; a non-JSON answer is an explicit failure, never a fake decision.
function extractDirectDecision(rawBody) {
  const content = rawBody?.choices?.[0]?.message?.content;
  if (!content) return null;
  const match = /\{[\s\S]*\}/.exec(content);
  if (!match) throw new Error("Réponse du fournisseur sans objet JSON exploitable");
  return JSON.parse(match[0]);
}

async function postDirect(cfg, payload) {
  const resp = await fetch(buildDirectUrl(cfg.endpoint), {
    method: "POST",
    headers: buildDirectHeaders(cfg.apiKey),
    body: JSON.stringify(buildDirectBody(payload, cfg.model)),
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status} ${resp.statusText} — ${buildDirectUrl(cfg.endpoint)}`);
  return await resp.json();
}

export async function testDirectConnection(endpoint, apiKey, model) {
  const decision = await postDirect(
    { endpoint, apiKey, model },
    { title: "test", description: "", bullets: [], candidate_actions: ["approve", "reject"] },
  );
  if (!decision?.choices?.[0]?.message) throw new Error("Réponse inattendue du fournisseur (enveloppe OpenAI absente)");
  return { ok: true, message: "Connexion directe réussie (le fournisseur accepte les appels navigateur)" };
}

export function useDirectMode(cfg) {
  return Boolean(cfg.directMode) && cfg.provider !== "custom";
}

function normalizeDecision(decision, actions) {
  // Support universel : { action: "approve", confidence: 0.9 } ou { prediction: "approve" } ou Jev/Custom raw
  const chosen = decision?.action || decision?.prediction || decision?.label || decision?.decision;
  if (!chosen) return null;

  const matched = (actions || []).find(a => a.id.toLowerCase() === String(chosen).toLowerCase());
  return {
    actionId: matched ? matched.id : chosen,
    label: matched ? matched.label : chosen,
    confidence: typeof decision.confidence === "number" ? Math.round(decision.confidence * 100) : null,
    reasoning: decision.reasoning || null,
  };
}

async function queryViaProxy(cfg, payload) {
  const resp = await authFetch("/api/classifier/predict", {
    method: "POST",
    headers: { "Content-Type": "application/json" }, // authFetch adds the token
    body: JSON.stringify({
      endpoint: cfg.endpoint,
      api_key: cfg.apiKey,
      payload: { ...payload, provider: cfg.provider, model: cfg.model },
    }),
  });
  const result = await resp.json();
  if (!result.ok || !result.data) return null;
  return result.data;
}

export async function fetchItemPrediction(item, actions) {
  const cfg = getClassifierConfig();
  if (!cfg.enabled || !cfg.endpoint) return null;

  try {
    const payload = {
      id: item.id,
      title: item.title,
      description: item.description || "",
      bullets: item.bullets || [],
      candidate_actions: (actions || []).map(a => a.id),
    };

    const isDirect = useDirectMode(cfg);
    const decision = isDirect ? extractDirectDecision(await postDirect(cfg, payload)) : await queryViaProxy(cfg, payload);
    if (!decision) return null;
    return normalizeDecision(decision, actions);
  } catch (err) {
    console.debug("[classifier] prediction query error", err);
    return null;
  }
}

export function initSettingsModal() {
  const modal = document.getElementById("settings-modal");
  const openBtn = document.getElementById("header-settings-btn");
  const closeBtn = document.getElementById("settings-close-btn");
  const saveBtn = document.getElementById("settings-save-btn");
  const testBtn = document.getElementById("settings-test-btn");
  const providerSelect = document.getElementById("cfg-provider");
  const endpointInput = document.getElementById("cfg-endpoint");
  const modelInput = document.getElementById("cfg-model");
  const modelContainer = document.getElementById("field-model-container");
  const apiKeyInput = document.getElementById("cfg-api-key");
  const rememberInput = document.getElementById("cfg-remember");
  const forgetBtn = document.getElementById("forget-key-btn");
  const keyStorageNote = document.getElementById("key-storage-note");
  const directInput = document.getElementById("cfg-direct");
  const directNote = document.getElementById("direct-mode-note");
  const enabledInput = document.getElementById("cfg-enabled");
  const feedbackEl = document.getElementById("settings-feedback");

  if (!modal || !openBtn) return;

  function syncProviderUI() {
    const isCustom = providerSelect?.value === "custom";
    if (modelContainer) {
      modelContainer.hidden = isCustom;
    }
    if (endpointInput) {
      endpointInput.placeholder = isCustom
        ? "https://scoring.example.com/classify"
        : "https://api.openai.com/v1";
    }
    if (directInput) {
      directInput.disabled = isCustom;
    }
    if (directNote) {
      directNote.textContent = isCustom
        ? DIRECT_HINT_CUSTOM
        : DIRECT_HINT_PROXY;
    }
  }

  providerSelect?.addEventListener("change", syncProviderUI);

  function syncKeyStorageUI() {
    const cfg = getClassifierConfig();
    if (rememberInput) rememberInput.checked = cfg.remember;
    const isDeviceStored = Boolean(cfg.remember && cfg.apiKey);
    if (forgetBtn) forgetBtn.hidden = !isDeviceStored;
    if (keyStorageNote) keyStorageNote.textContent = isDeviceStored ? KEY_HINT_DEVICE : KEY_HINT_SESSION;
  }

  forgetBtn?.addEventListener("click", () => {
    const cfg = getClassifierConfig();
    saveClassifierConfig({ ...cfg, apiKey: "", remember: false });
    if (apiKeyInput) apiKeyInput.value = "";
    syncKeyStorageUI();
    showFeedback("Clé oubliée : elle n'est plus stockée dans ce navigateur.", true);
  });

  function showFeedback(msg, isSuccess) {
    if (!feedbackEl) return;
    feedbackEl.textContent = msg;
    feedbackEl.className = `settings-feedback ${isSuccess ? 'success' : 'error'}`;
    feedbackEl.hidden = false;
  }

  function clearFeedback() {
    if (!feedbackEl) return;
    feedbackEl.hidden = true;
    feedbackEl.textContent = "";
  }

  function openModal() {
    const cfg = getClassifierConfig();
    if (providerSelect) providerSelect.value = cfg.provider;
    if (endpointInput) endpointInput.value = cfg.endpoint;
    if (modelInput) modelInput.value = cfg.model;
    if (apiKeyInput) apiKeyInput.value = cfg.apiKey;
    if (enabledInput) enabledInput.checked = cfg.enabled;
    if (directInput) directInput.checked = useDirectMode(cfg);
    syncProviderUI();
    syncKeyStorageUI();
    clearFeedback();
    modal.hidden = false;
    modal.setAttribute("aria-hidden", "false");
  }

  function closeModal() {
    modal.hidden = true;
    modal.setAttribute("aria-hidden", "true");
  }

  openBtn.addEventListener("click", openModal);
  closeBtn?.addEventListener("click", closeModal);
  modal.addEventListener("click", (e) => {
    if (e.target === modal) closeModal();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !modal.hidden) {
      closeModal();
    }
  });

  testBtn?.addEventListener("click", async () => {
    clearFeedback();
    const endpoint = (endpointInput?.value || "").trim();
    const apiKey = (apiKeyInput?.value || "").trim();
    const provider = providerSelect?.value || "openai";
    const model = (modelInput?.value || "").trim();

    if (!endpoint) {
      showFeedback("Veuillez renseigner un endpoint API valide.", false);
      return;
    }
    testBtn.disabled = true;
    testBtn.textContent = "Test en cours...";
    try {
      const isDirect = provider !== "custom" && Boolean(directInput?.checked);
      const res = isDirect
        ? await testDirectConnection(endpoint, apiKey, model)
        : await testClassifierConnection(endpoint, apiKey, provider, model);
      if (res.ok) {
        showFeedback(res.message || "Connexion réussie !", true);
      } else {
        showFeedback(res.error || res.message || "Échec de connexion", false);
      }
    } catch (err) {
      showFeedback(`Erreur : ${err.message}`, false);
    } finally {
      testBtn.disabled = false;
      testBtn.textContent = "Tester la connexion";
    }
  });

  saveBtn?.addEventListener("click", () => {
    const provider = providerSelect?.value || "openai";
    const endpoint = (endpointInput?.value || "").trim();
    const model = (modelInput?.value || "").trim();
    const apiKey = (apiKeyInput?.value || "").trim();
    const enabled = Boolean(enabledInput?.checked);
    const remember = Boolean(rememberInput?.checked);
    const directMode = Boolean(directInput?.checked);
    saveClassifierConfig({ ...getClassifierConfig(), provider, endpoint, model, apiKey, enabled, remember, directMode });
    showFeedback("Configuration enregistrée avec succès !", true);
    setTimeout(closeModal, 500);
  });
}
