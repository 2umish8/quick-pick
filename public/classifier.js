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
      provider: cfg.provider,
      model: cfg.model,
    };

    const resp = await authFetch("/api/classifier/predict", {
      method: "POST",
      headers: { "Content-Type": "application/json" }, // authFetch adds the token
      body: JSON.stringify({
        endpoint: cfg.endpoint,
        api_key: cfg.apiKey,
        payload,
      }),
    });
    const result = await resp.json();
    if (!result.ok || !result.data) return null;

    const d = result.data;
    // Support universel : { action: "approve", confidence: 0.9 } ou { prediction: "approve" } ou Jev/Custom raw
    const chosen = d.action || d.prediction || d.label || d.decision;
    if (!chosen) return null;

    const matched = (actions || []).find(a => a.id.toLowerCase() === String(chosen).toLowerCase());
    return {
      actionId: matched ? matched.id : chosen,
      label: matched ? matched.label : chosen,
      confidence: typeof d.confidence === "number" ? Math.round(d.confidence * 100) : null,
      reasoning: d.reasoning || null,
    };
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
      const res = await testClassifierConnection(endpoint, apiKey, provider, model);
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
    saveClassifierConfig({ ...getClassifierConfig(), provider, endpoint, model, apiKey, enabled, remember });
    showFeedback("Configuration enregistrée avec succès !", true);
    setTimeout(closeModal, 500);
  });
}
