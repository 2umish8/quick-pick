// Module Drawer : consultation des cartes décidées et à décider
import { escapeHtml } from "./escape.js";

let currentTab = "pending"; // "pending" | "decided"
let activeState = null;
let undoCallback = null;

export function initDrawer(callbacks = {}) {
  undoCallback = callbacks.onUndoItem || null;
  const backdrop = document.getElementById("drawer-backdrop");
  const closeBtn = document.getElementById("drawer-close-btn");
  const tabPending = document.getElementById("tab-btn-pending");
  const tabDecided = document.getElementById("tab-btn-decided");

  backdrop?.addEventListener("click", (e) => {
    if (e.target === backdrop) closeDrawer();
  });
  closeBtn?.addEventListener("click", closeDrawer);
  tabPending?.addEventListener("click", () => switchTab("pending"));
  tabDecided?.addEventListener("click", () => switchTab("decided"));

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeDrawer();
  });
}

export function openDrawer() {
  const drawer = document.getElementById("deck-drawer");
  drawer?.classList.add("open");
  renderDrawerContent();
}

export function closeDrawer() {
  const drawer = document.getElementById("deck-drawer");
  drawer?.classList.remove("open");
}

export function updateDrawerState(state) {
  activeState = state;
  const countBadge = document.getElementById("header-progress-pill");
  if (countBadge && state) {
    const decided = state.decided_count ?? (state.decided_items?.length || 0);
    const pending = state.pending_count ?? (state.pending_items?.length || 0);
    countBadge.textContent = `${decided} tranché${decided > 1 ? "s" : ""} · ${pending} restant${pending > 1 ? "s" : ""}`;
  }
  const drawer = document.getElementById("deck-drawer");
  if (drawer?.classList.contains("open")) {
    renderDrawerContent();
  }
}

function switchTab(tab) {
  currentTab = tab;
  document.getElementById("tab-btn-pending")?.classList.toggle("active", tab === "pending");
  document.getElementById("tab-btn-decided")?.classList.toggle("active", tab === "decided");
  renderDrawerContent();
}

function renderDrawerContent() {
  const list = document.getElementById("drawer-items-list");
  if (!list || !activeState) return;
  const items = currentTab === "pending" ? (activeState.pending_items || []) : (activeState.decided_items || []);

  if (items.length === 0) {
    list.innerHTML = `<div class="drawer-empty">${currentTab === "pending" ? "Toutes les cartes ont été tranchées !" : "Aucune décision prise pour le moment."}</div>`;
    return;
  }

  list.innerHTML = items.map((item, idx) => {
    const badges = (item.badges || []).map(b => `<span class="badge-tag ${escapeHtml(b.variant || 'neutral')}">${escapeHtml(b.label)}</span>`).join("");
    const decisionBadge = item.action_label ? `<span class="decision-pill">${escapeHtml(item.action_label)}</span>` : "";
    const isCurrent = currentTab === "pending" && idx === 0 ? `<span class="current-pill">En cours</span>` : "";
    const commentBlock = item.comment ? `<div class="drawer-row-comment">“${escapeHtml(item.comment)}”</div>` : "";
    const undoAction = currentTab === "decided" ? `<button class="drawer-row-undo-btn" data-item-id="${escapeHtml(item.id)}" title="Remettre cette carte en jeu">↩ Réviser</button>` : "";
    return `
      <div class="drawer-row ${isCurrent ? 'is-active' : ''}">
        <div class="drawer-row-main">
          <div class="drawer-row-meta">${isCurrent} ${decisionBadge} ${badges}</div>
          <div class="drawer-row-title">${escapeHtml(item.title)}</div>
          ${commentBlock}
        </div>
        ${undoAction}
      </div>
    `;
  }).join("");

  if (currentTab === "decided" && undoCallback) {
    list.querySelectorAll(".drawer-row-undo-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        const itemId = btn.dataset.itemId;
        if (itemId) {
          closeDrawer();
          undoCallback(itemId);
        }
      });
    });
  }
}
