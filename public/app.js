// Module Principal Quick-Pick (SOLID SRP)
import { fetchHealth, fetchDecks, fetchDeckState, postDecision, postUndo, postSkip, fetchSummary, postReset, postDelete, postItems } from "./api.js";
import { escapeHtml } from "./escape.js";
import { renderStack, attachClassifierSuggestion } from "./stack.js";
import { initDrawer, openDrawer, updateDrawerState } from "./deck-drawer.js";
import { initSettingsModal, fetchItemPrediction } from "./classifier.js";
import { initDeckForm } from "./deck-form.js";
import { formatDecisionSummary, parseCardLines } from "./format.js";

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
  dom.viewDecks.hidden = view !== "decks";
  dom.viewGame.hidden = view !== "game";
  dom.viewSummary.hidden = view !== "summary";
  dom.headerPill.hidden = view === "decks";
  dom.progressPill.hidden = view !== "game";
  syncUndoVisibility();
}

function syncUndoVisibility() {
  const canUndo = Boolean(state.deckData?.can_undo);
  dom.headerUndoBtn.hidden = !(state.currentView === "game" && canUndo);
}

// Two-step confirmation: one armed button at a time, back to normal after 4 s or on any list re-render.
const CONFIRM_DELAY_MS = 4000;
let armed = null;
// Sequence counter for silent refreshes: any newer render or refresh makes an older answer stale.
let refreshSeq = 0;

function disarm() {
  if (!armed) return;
  clearTimeout(armed.timer);
  armed.button.textContent = armed.label;
  armed.button.classList.remove("armed");
  armed.note.hidden = true;
  armed = null;
}

function arm(button, note, noteText) {
  disarm();
  armed = { button, note, label: button.textContent, timer: setTimeout(disarm, CONFIRM_DELAY_MS) };
  button.textContent = "Confirmer ?";
  button.classList.add("armed");
  note.textContent = noteText || "";
  note.hidden = !noteText;
}

function deckItemHtml(deck) {
  const category = escapeHtml(deck.category || "PROJET");
  const title = escapeHtml(deck.title);
  const desc = escapeHtml(deck.description || "");
  let status;
  if (deck.invalid) status = `<span class="deck-item-invalid"><span class="deck-ico" aria-hidden="true">⚠</span>Illisible</span>`;
  else if (deck.is_completed) status = `<span class="deck-item-done"><span class="deck-ico" aria-hidden="true">✓</span>Terminé</span>`;
  else {
    // Colour = meaning: nothing decided yet -> neutral grey, in progress -> amber.
    const stateClass = Number(deck.decided) > 0 ? "state-active" : "state-zero";
    status = `<span class="deck-item-progress ${stateClass}"><span class="deck-item-count">${escapeHtml(String(deck.decided))}/${escapeHtml(String(deck.total))}</span> <span class="deck-item-unit">décidés</span></span>`;
  }
  const cardOpen = deck.invalid
    ? `<button type="button" class="deck-item-card" data-deck-id="${escapeHtml(deck.id)}" disabled>`
    : `<button type="button" class="deck-item-card" data-deck-id="${escapeHtml(deck.id)}">`;
  const actions = deck.invalid
    ? `<button type="button" class="deck-act danger" data-act="delete" title="Supprimer">Supprimer</button>`
    : `<button type="button" class="deck-act" data-act="reset">Remettre à zéro</button>
       <button type="button" class="deck-act danger" data-act="delete" title="Supprimer">Supprimer</button>
       <button type="button" class="deck-act" data-act="add" aria-expanded="false">Ajouter des cartes</button>`;
  const addZone = deck.invalid ? "" : `
      <div class="deck-item-add" hidden>
        <textarea class="deck-create-input deck-create-textarea deck-add-input" rows="4" aria-label="Cartes à ajouter" placeholder="Une carte par ligne. Détail : titre :: détail"></textarea>
        <p class="deck-create-error deck-add-error" role="alert"></p>
        <div class="deck-add-buttons">
          <button type="button" class="deck-act" data-act="add-submit">Ajouter</button>
          <button type="button" class="deck-act" data-act="add-cancel">Annuler</button>
        </div>
      </div>`;
  return `
    <div class="deck-item" data-deck-id="${escapeHtml(deck.id)}">
      ${cardOpen}
        <div class="deck-item-top"><span class="deck-item-category">${category}</span>${status}</div>
        <div class="deck-item-title">${title}</div>
        <div class="deck-item-desc">${desc}</div>
      </button>
      <div class="deck-item-actions">${actions}</div>
      <p class="deck-item-note" hidden></p>${addZone}
    </div>`;
}

async function runDeckAction(task, failureLabel) {
  try {
    await task();
    await loadDecks();
  } catch (err) {
    showErrorBanner(`${failureLabel} : ${err.message}`);
    await loadDecks();
  }
}

async function submitAddCards(item, deckId) {
  const input = item.querySelector(".deck-add-input");
  const errorEl = item.querySelector(".deck-add-error");
  const items = parseCardLines(input.value);
  errorEl.textContent = "";
  if (!items.length) {
    errorEl.textContent = "Saisissez au moins une carte.";
    return;
  }
  const addBtn = item.querySelector('[data-act="add-submit"]');
  const setBusy = busy => {
    input.disabled = busy;
    if (addBtn) addBtn.disabled = busy;
  };
  setBusy(true);
  try {
    await postItems(deckId, items);
  } catch (err) {
    errorEl.textContent = err.code === "too_many_items" ? "Trop de cartes : 200 au maximum par deck." : err.message;
    setBusy(false);
    return;
  }
  await loadDecks();
}

function onDeckAction(event) {
  const button = event.target.closest("button[data-act]");
  const item = button?.closest(".deck-item");
  if (!button || !item) return;
  const deckId = item.dataset.deckId;
  const act = button.dataset.act;
  const note = item.querySelector(".deck-item-note");
  if (act === "reset" || act === "delete") {
    if (armed?.button !== button) {
      arm(button, note, act === "delete" ? "Une copie reste récupérable par l'agent." : "");
      return;
    }
    disarm();
    if (act === "reset") runDeckAction(() => postReset(deckId), "Remise à zéro impossible");
    else runDeckAction(() => postDelete(deckId), "Suppression impossible");
  } else if (act === "add") {
    disarm();
    const zone = item.querySelector(".deck-item-add");
    zone.hidden = !zone.hidden;
    button.setAttribute("aria-expanded", String(!zone.hidden));
    if (!zone.hidden) zone.querySelector(".deck-add-input").focus();
  } else if (act === "add-cancel") {
    const zone = item.querySelector(".deck-item-add");
    zone.hidden = true;
    item.querySelector('[data-act="add"]').setAttribute("aria-expanded", "false");
  } else if (act === "add-submit") {
    submitAddCards(item, deckId);
  }
}

dom.deckList.addEventListener("click", onDeckAction);

function renderDeckList(decks) {
  dom.deckList.innerHTML = decks.length
    ? decks.map(deckItemHtml).join("")
    : `<p class="deck-list-empty">Aucun deck pour l'instant. Créez le premier ci-dessous, ou posez une liste et commencez à trier.</p>`;
  dom.deckList.querySelectorAll(".deck-item-card:not([disabled])").forEach(el => {
    el.addEventListener("click", () => openDeck(el.dataset.deckId));
  });
}

async function loadDecks() {
  disarm();
  refreshSeq += 1;
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
  renderDeckList(data.decks || []);
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

// Ouvre un deck depuis un clic ou un changement d'adresse : un échec se voit (bandeau + réessai)
// au lieu d'une promesse rejetée sans bruit.
function openDeck(deckId) {
  return startDeck(deckId).catch(err => {
    state.activeDeckId = null;
    showErrorBanner(`Impossible d'ouvrir ce sujet : ${err.message}`, () => openDeck(deckId));
  });
}

// Après un échec (ou une action ignorée), la carte déjà envolée par le swipe revient à l'écran.
function restoreCurrentCard() {
  if (state.deckData?.current_item) renderStack(dom.cardStack, state.deckData, onCardDecide);
}

function handleDeckState(deckData) {
  refreshSeq += 1;
  hideErrorBanner();
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
  if (!state.deckData?.current_item) return;
  if (state.isProcessing) {
    restoreCurrentCard(); // swipe pendant une autre requête : la carte ne doit pas rester invisible
    return;
  }
  state.isProcessing = true;
  const comment = dom.commentInput.value.trim() || null;
  try {
    const nextState = await postDecision(state.activeDeckId, state.deckData.current_item.id, actionId, comment);
    handleDeckState(nextState);
  } catch (err) {
    if (err.message === "already_decided") {
      // Une autre fenêtre ou l'agent a déjà tranché cette carte : on se resynchronise, sans écraser.
      try {
        handleDeckState(await fetchDeckState(state.activeDeckId));
        return;
      } catch { /* on retombe sur le bandeau d'erreur */ }
    }
    restoreCurrentCard();
    showErrorBanner(`Décision non enregistrée : ${err.message}`, () => onCardDecide(actionId));
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
  } catch (err) {
    showErrorBanner(`Carte non passée : ${err.message}`, onCardSkip);
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
  } catch (err) {
    showErrorBanner(`Annulation impossible : ${err.message}`, () => triggerUndo(itemId));
  } finally {
    state.isProcessing = false;
  }
}

const DIRECTION_SHORTCUTS = { east: "ArrowRight", west: "ArrowLeft", north: "ArrowUp", south: "ArrowDown" };

const DOCK_ARROWS = { east: "→", west: "←", north: "↑", south: "↓" };
const DOCK_RANK = { north: 0, west: 1, east: 2, south: 3 };
const dockRank = (action) => DOCK_RANK[action.direction] ?? 4;

function renderDock(actions) {
  // Keep keyboard focus on an equivalent button after the dock is re-rendered.
  const focusedBtn = document.activeElement?.closest?.(".action-key-button");
  const focusedId = focusedBtn ? focusedBtn.dataset.actionId : null;
  // The dock mirrors the geography of the swipe: north above, west on the left, east on the right, south below.
  const ordered = [...actions].sort((a, b) => dockRank(a) - dockRank(b));
  dom.kineticDock.innerHTML = ordered.map(act => `
    <button class="action-key-button tone-${escapeHtml(act.color || 'neutral')} dir-${escapeHtml(act.direction || 'none')}" data-action-id="${escapeHtml(act.id)}" data-direction="${escapeHtml(act.direction || '')}"${ariaKeyShortcuts(act)}>
      ${DOCK_ARROWS[act.direction] ? `<span class="dock-arrow" aria-hidden="true">${DOCK_ARROWS[act.direction]}</span>` : ""}
      <span>${escapeHtml(act.label)}</span>
      ${act.key ? `<kbd class="keycap-badge">${escapeHtml(String(act.key).toUpperCase())}</kbd>` : ""}
    </button>
  `).join("");
  const buttons = dom.kineticDock.querySelectorAll(".action-key-button");
  buttons.forEach(btn => {
    btn.addEventListener("click", () => onCardDecide(btn.dataset.actionId));
  });
  if (focusedId !== null && buttons.length) {
    const same = [...buttons].find(btn => btn.dataset.actionId === focusedId);
    (same || buttons[0]).focus();
  }
}

// Screen readers get the shortcut keys attached to the button instead of losing the visible label.
function ariaKeyShortcuts(action) {
  const keys = [action.key && String(action.key).toUpperCase(), DIRECTION_SHORTCUTS[action.direction]].filter(Boolean);
  return keys.length ? ` aria-keyshortcuts="${escapeHtml(keys.join(" "))}"` : "";
}

async function showSummary() {
  switchView("summary");
  let summary;
  try {
    summary = await fetchSummary(state.activeDeckId);
  } catch (err) {
    showErrorBanner(`Impossible de charger la synthèse : ${err.message}`, showSummary);
    return;
  }
  // Libellés lisibles partout (jamais les ids d'actions bruts)
  const labelById = Object.fromEntries(
    (state.deckData?.decided_items || []).map(entry => [entry.chosen_action, entry.action_label])
  );
  const breakdownHtml = Object.entries(summary.actions_breakdown || {}).map(([actId, count]) => `
    <div class="summary-stat-card">
      <span class="summary-stat-val">${escapeHtml(String(count))}</span>
      <span class="summary-stat-label">${escapeHtml(labelById[actId] || actId)}</span>
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
      <p>${escapeHtml(formatDecisionSummary(summary.total_decided, summary.active_seconds))}</p>
    </div>
    ${breakdownHtml ? `<div class="summary-stats-grid">${breakdownHtml}</div>` : ""}
    ${entriesHtml ? `<div class="summary-list">${entriesHtml}</div>` : ""}
    <div class="recap-actions-row">
      ${state.deckData?.can_undo ? `<button class="recap-btn secondary" id="btn-back-to-card">Revenir à la dernière carte</button>` : ""}
      <button class="recap-btn secondary" id="btn-copy-markdown">Copier en Markdown</button>
      <button class="recap-btn primary" id="btn-back-decks">Retour aux sujets</button>
    </div>
  `;
  document.getElementById("btn-copy-markdown")?.addEventListener("click", async (event) => {
    const btn = event.currentTarget;
    try {
      await navigator.clipboard.writeText(buildMarkdownRecap(summary, labelById));
      btn.textContent = "Copié";
    } catch {
      btn.textContent = "Copie impossible";
    }
  });
  document.getElementById("btn-back-decks")?.addEventListener("click", loadDecks);
  document.getElementById("btn-back-to-card")?.addEventListener("click", () => triggerUndo());
}

function buildMarkdownRecap(summary, labelById) {
  const lines = [
    `# Synthèse Quick-Pick : ${summary.title || summary.deck_id}`,
    "",
    `- **Progression** : ${summary.total_decided}/${summary.total_items} décidés`,
    `- **Temps actif** : ${summary.active_seconds}s`,
    "",
    "## Détail des décisions",
  ];
  // Plain-text Markdown for the clipboard (never injected as HTML), so no HTML escaping here.
  for (const decision of summary.entries || []) {
    const label = labelById[decision.chosen_action] || decision.action_label || decision.chosen_action;
    const comment = decision.comment ? ` — *« ${decision.comment} »*` : "";
    lines.push(`- [${label}] **${decision.title}**${comment}`);
  }
  return lines.join("\n");
}

function initKeyboard() {
  window.addEventListener("keydown", async (e) => {
    // Les raccourcis de jeu ne doivent jamais voler la frappe des champs de saisie
    const isTyping = e.target instanceof HTMLElement
      && Boolean(e.target.closest("input, textarea, select, [contenteditable]"));
    if (isTyping || (state.currentView !== "game" && state.currentView !== "summary")) return;
    // Un panneau ouvert (historique, réglages) garde ses touches : Échap le ferme, il ne passe pas la carte,
    // et les lettres/flèches ne décident pas la carte cachée derrière.
    if (document.getElementById("deck-drawer")?.classList.contains("open")) return;
    if (document.getElementById("settings-modal")?.hidden === false) return;
    const isUndoCombo = (e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z" && state.deckData?.can_undo;
    // Summary: only the undo combo is live, so the last card can be reopened from the keyboard too.
    if (state.currentView === "summary") {
      if (isUndoCombo) {
        e.preventDefault();
        triggerUndo();
      }
      return;
    }
    const isInputActive = (document.activeElement === dom.commentInput);
    if (isUndoCombo) {
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
    if (kept.length) {
      // Une adresse mal encodée (#%E0%A4%A) ne doit pas faire planter tout le module au chargement.
      try { return decodeURIComponent(kept[0]); } catch { return null; }
    }
  }
  const params = new URLSearchParams(window.location.search);
  const deckParam = params.get("deck");
  if (deckParam) return deckParam.trim();
  return null;
}

// Initialisation
initDeckForm({ onCreated: (deckId) => openDeck(deckId) });
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
    openDeck(targetId);
  } else if (!targetId && state.currentView !== "decks") {
    loadDecks();
  }
});

// Retour sur l'onglet : mise à jour silencieuse (pas de bandeau, pas de prompt, un échec ne change rien).
function panelsClosed() {
  return !document.getElementById("deck-drawer")?.classList.contains("open")
    && document.getElementById("settings-modal")?.hidden !== false;
}

function gameRefreshAllowed() {
  return state.currentView === "game" && Boolean(state.activeDeckId)
    && !state.isProcessing && panelsClosed() && !dom.commentInput.value.trim();
}

function listRefreshAllowed() {
  return state.currentView === "decks" && !armed && !dom.deckList.querySelector(".deck-item-add:not([hidden])");
}

// Nouvelle version servie pendant que l'onglet dormait : recharger plutôt que garder l'ancien code.
// Jamais pendant une note en cours de saisie ni un panneau ouvert ; un échec réseau ne change rien.
const LOADED_VERSION = document.querySelector('meta[name="quick-pick-version"]')?.content || "";
function reloadAllowed() {
  const active = document.activeElement;
  const editing = active && (active.tagName === "INPUT" || active.tagName === "TEXTAREA");
  if (editing || state.isProcessing || !panelsClosed() || dom.commentInput?.value.trim()) return false;
  return state.currentView !== "decks" || listRefreshAllowed();
}

async function reloadIfNewVersion() {
  if (!LOADED_VERSION) return false;
  let health;
  try {
    health = await fetchHealth({ silent: true });
  } catch {
    return false;
  }
  if (!health?.version || health.version === LOADED_VERSION || !reloadAllowed()) return false;
  window.location.reload();
  return true;
}

async function refreshOnReturn() {
  if (await reloadIfNewVersion()) return;
  const view = state.currentView;
  if (view === "game") {
    if (!gameRefreshAllowed()) return;
    const deckId = state.activeDeckId;
    const seq = ++refreshSeq;
    let fresh;
    try {
      fresh = await fetchDeckState(deckId, { silent: true });
    } catch (err) {
      if (err.status === 404 && seq === refreshSeq && state.activeDeckId === deckId) loadDecks();
      return;
    }
    if (seq !== refreshSeq || state.activeDeckId !== deckId || !gameRefreshAllowed()) return;
    const cur = state.deckData;
    const same = cur && !fresh.is_completed
      && cur.current_item?.id === fresh.current_item?.id
      && cur.decided_count === fresh.decided_count
      && cur.pending_count === fresh.pending_count;
    if (same) return;
    handleDeckState(fresh);
  } else if (view === "decks") {
    if (!listRefreshAllowed()) return;
    const seq = ++refreshSeq;
    let data;
    try {
      data = await fetchDecks({ silent: true });
    } catch {
      return;
    }
    if (seq !== refreshSeq || !listRefreshAllowed()) return;
    renderDeckList(data.decks || []);
  }
  // Vue synthèse : ignorée, l'affichage peut rester périmé jusqu'à une action.
}

let lastReturnAt = 0;
function onReturn(isFocus) {
  const now = Date.now();
  if (isFocus && now - lastReturnAt < 1000) return;
  lastReturnAt = now;
  refreshOnReturn();
}
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") onReturn(false);
});
window.addEventListener("focus", () => onReturn(true));

const initialDeck = getInitialDeckId();
if (initialDeck) {
  startDeck(initialDeck).catch(() => loadDecks());
} else {
  loadDecks();
}
