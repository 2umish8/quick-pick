// Module Principal Quick-Pick (SOLID SRP)
import { fetchDecks, fetchDeckState, postDecision, postUndo, postSkip, fetchSummary } from "./api.js";
import { escapeHtml } from "./escape.js";
import { renderStack, attachClassifierSuggestion } from "./stack.js";
import { initDrawer, openDrawer, updateDrawerState } from "./deck-drawer.js";
import { initSettingsModal, fetchItemPrediction } from "./classifier.js";

const state = { activeDeckId: null, deckData: null, isProcessing: false, currentView: "decks" };

const dom = {
  headerPill: document.getElementById("header-deck-pill"),
  headerUndoBtn: document.getElementById("header-undo-btn"),
  progressPill: document.getElementById("header-progress-pill"),
  viewDecks: document.getElementById("view-decks"),
  viewGame: document.getElementById("view-game"),
  viewSummary: document.getElementById("view-summary"),
  deckList: document.getElementById("deck-list-container"),
  cardStack: document.getElementById("card-stack-container"),
  commentInput: document.getElementById("decision-comment-input"),
  kineticDock: document.getElementById("kinetic-dock"),
  summaryContent: document.getElementById("summary-content"),
  errorBanner: document.getElementById("error-banner"),
  errorBannerText: document.getElementById("error-banner-text"),
  errorBannerRetry: document.getElementById("error-banner-retry"),
};

function showErrorBanner(message, onRetry) {
  if (!dom.errorBanner) return;
  dom.errorBannerText.textContent = message;
  dom.errorBannerRetry.onclick = () => {
    hideErrorBanner();
    onRetry?.();
  };
  dom.errorBanner.hidden = false;
}

function hideErrorBanner() {
  if (!dom.errorBanner) return;
  dom.errorBanner.hidden = true;
}

function switchView(view) {
  state.currentView = view;
  dom.viewDecks.style.display = view === "decks" ? "block" : "none";
  dom.viewGame.style.display = view === "game" ? "flex" : "none";
  dom.viewSummary.style.display = view === "summary" ? "block" : "none";
  dom.headerPill.style.display = view === "decks" ? "none" : "inline-block";
  dom.progressPill.style.display = view === "game" ? "inline-flex" : "none";
  syncUndoVisibility();
}

function syncUndoVisibility() {
  const canUndo = Boolean(state.deckData?.can_undo);
  dom.headerUndoBtn.style.display = (state.currentView === "game" && canUndo) ? "inline-flex" : "none";
}

async function loadDecks() {
  if (window.location.hash) {
    history.replaceState(null, "", window.location.pathname + window.location.search);
  }
  state.activeDeckId = null;
  state.deckData = null;
  let data;
  try {
    data = await fetchDecks();
  } catch (err) {
    dom.deckList.innerHTML = "";
    showErrorBanner(`Impossible de charger les sujets : ${err.message}`, loadDecks);
    switchView("decks");
    return;
  }
  hideErrorBanner();
  dom.deckList.innerHTML = (data.decks || []).map(deck => `
    <div class="deck-item-card" data-deck-id="${escapeHtml(deck.id)}">
      <div class="deck-item-category">${escapeHtml(deck.category || "PROJET")}</div>
      <div class="deck-item-title">${escapeHtml(deck.title)}</div>
      <div class="deck-item-desc">${escapeHtml(deck.description || "")}</div>
    </div>
  `).join("");
  dom.deckList.querySelectorAll(".deck-item-card").forEach(el => {
    el.addEventListener("click", () => startDeck(el.dataset.deckId));
  });
  switchView("decks");
}

async function startDeck(deckId) {
  if (!deckId) return;
  state.activeDeckId = deckId;
  window.location.hash = encodeURIComponent(deckId);
  const deckData = await fetchDeckState(deckId);
  dom.headerPill.textContent = deckData.title || deckId;
  handleDeckState(deckData);
}

function handleDeckState(deckData) {
  state.deckData = deckData;
  updateDrawerState(deckData);
  syncUndoVisibility();
  if (deckData.is_completed) {
    showSummary();
  } else {
    switchView("game");
    dom.commentInput.value = "";
    renderStack(dom.cardStack, deckData, onCardDecide);
    renderDock(deckData.current_item?.actions || []);
    loadClassifierSuggestion(deckData.current_item);
  }
}

async function loadClassifierSuggestion(item) {
  if (!item) return;
  const pred = await fetchItemPrediction(item, item.actions || []);
  if (pred && state.deckData?.current_item?.id === item.id) {
    attachClassifierSuggestion(dom.cardStack, item.id, pred);
  }
}

async function onCardDecide(actionId) {
  if (state.isProcessing || !state.deckData?.current_item) return;
  state.isProcessing = true;
  const comment = dom.commentInput.value.trim() || null;
  try {
    const nextState = await postDecision(state.activeDeckId, state.deckData.current_item.id, actionId, comment);
    handleDeckState(nextState);
  } finally {
    state.isProcessing = false;
  }
}

async function onCardSkip() {
  if (state.isProcessing || !state.deckData?.current_item) return;
  state.isProcessing = true;
  try {
    const nextState = await postSkip(state.activeDeckId, state.deckData.current_item.id);
    handleDeckState(nextState);
  } finally {
    state.isProcessing = false;
  }
}

async function triggerUndo(itemId = null) {
  if (state.isProcessing || !state.activeDeckId) return;
  state.isProcessing = true;
  try {
    const nextState = await postUndo(state.activeDeckId, itemId);
    handleDeckState(nextState);
  } finally {
    state.isProcessing = false;
  }
}

function renderDock(actions) {
  dom.kineticDock.innerHTML = actions.map(act => `
    <button class="action-key-button ${escapeHtml(act.color || 'neutral')}" data-action-id="${escapeHtml(act.id)}">
      <span>${escapeHtml(act.label)}</span>
      ${act.key ? `<kbd class="keycap-badge">${escapeHtml(String(act.key).toUpperCase())}</kbd>` : ""}
    </button>
  `).join("");
  dom.kineticDock.querySelectorAll(".action-key-button").forEach(btn => {
    btn.addEventListener("click", () => onCardDecide(btn.dataset.actionId));
  });
}

async function showSummary() {
  switchView("summary");
  const summary = await fetchSummary(state.activeDeckId);
  const breakdownHtml = Object.entries(summary.actions_breakdown || {}).map(([actId, count]) => `
    <div class="summary-stat-card">
      <span class="summary-stat-val">${escapeHtml(String(count))}</span>
      <span class="summary-stat-label">${escapeHtml(actId)}</span>
    </div>
  `).join("");

  const entriesHtml = (summary.entries || []).map(entry => {
    const label = entry.action_label || entry.chosen_action;
    const commentHtml = entry.comment ? `<div class="summary-row-comment">“${escapeHtml(entry.comment)}”</div>` : "";
    return `
      <div class="summary-row">
        <div class="summary-row-top">
          <span class="summary-row-title">${escapeHtml(entry.title)}</span>
          <span class="decision-pill">${escapeHtml(label)}</span>
        </div>
        ${commentHtml}
      </div>
    `;
  }).join("");

  dom.summaryContent.innerHTML = `
    <div class="victory-hero">
      <div class="trophy-badge">✨</div>
      <h2>Toutes les cartes sont décidées</h2>
      <p>${summary.total_decided} décisions prises en ${summary.elapsed_seconds}s</p>
    </div>
    ${breakdownHtml ? `<div class="summary-stats-grid">${breakdownHtml}</div>` : ""}
    ${entriesHtml ? `<div class="summary-list">${entriesHtml}</div>` : ""}
    <div class="recap-actions-row">
      <button class="recap-btn primary" id="btn-back-decks">Retour aux sujets</button>
    </div>
  `;
  document.getElementById("btn-back-decks")?.addEventListener("click", loadDecks);
}

function initKeyboard() {
  window.addEventListener("keydown", async (e) => {
    const isInputActive = (document.activeElement === dom.commentInput);
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z" && state.deckData?.can_undo) {
      e.preventDefault();
      triggerUndo();
      return;
    }
    if (isInputActive) {
      return;
    }
    if (e.key.toLowerCase() === "c") {
      e.preventDefault();
      dom.commentInput.focus();
      return;
    }
    if (e.key.toLowerCase() === "x" || e.key === "Escape") {
      if (state.deckData?.has_next) {
        e.preventDefault();
        onCardSkip();
        return;
      }
    }

    const currentActions = state.deckData?.current_item?.actions || [];
    // Support des flèches directionnelles
    const arrowDirMap = {
      ArrowRight: "east",
      ArrowLeft: "west",
      ArrowUp: "north",
      ArrowDown: "south",
    };
    if (arrowDirMap[e.key]) {
      const dir = arrowDirMap[e.key];
      const matchedByDir = currentActions.find(a => a.direction === dir);
      if (matchedByDir) {
        e.preventDefault();
        onCardDecide(matchedByDir.id);
        return;
      }
      if (dir === "south" && state.deckData?.has_next) {
        e.preventDefault();
        onCardSkip();
        return;
      }
    }

    // Support des touches de raccourci par lettre
    const matchedByKey = currentActions.find(a => a.key && a.key.toLowerCase() === e.key.toLowerCase());
    if (matchedByKey) {
      e.preventDefault();
      onCardDecide(matchedByKey.id);
    }
  });
}

function getInitialDeckId() {
  const hash = window.location.hash.replace(/^#/, "").trim();
  if (hash) {
    // api.js strips token=/remember= parts at load; filter defensively here too.
    const kept = hash.split("&").filter(p => p && !p.startsWith("token=") && p !== "remember=1");
    if (kept.length) return decodeURIComponent(kept[0]);
  }
  const params = new URLSearchParams(window.location.search);
  const deckParam = params.get("deck");
  if (deckParam) return deckParam.trim();
  return null;
}

// Initialisation
initDrawer({ onUndoItem: (itemId) => triggerUndo(itemId) });
initSettingsModal();
initKeyboard();
dom.headerUndoBtn?.addEventListener("click", () => triggerUndo());
dom.progressPill?.addEventListener("click", openDrawer);
dom.headerPill?.addEventListener("click", loadDecks);
document.getElementById("logo-zone")?.addEventListener("click", loadDecks);

window.addEventListener("hashchange", () => {
  const targetId = getInitialDeckId();
  if (targetId && targetId !== state.activeDeckId) {
    startDeck(targetId);
  } else if (!targetId && state.currentView !== "decks") {
    loadDecks();
  }
});

const initialDeck = getInitialDeckId();
if (initialDeck) {
  startDeck(initialDeck).catch(() => loadDecks());
} else {
  loadDecks();
}
