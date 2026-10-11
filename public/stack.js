// Module Stack : Rendu de la pile réelle carrée & physique de drag/swipe
import { escapeHtml } from "./escape.js";

const SWIPE_THRESHOLD = 85;

function getCardOrganicTransform(index, id) {
  let hash = 0;
  for (let i = 0; i < (id || "").length; i++) hash = (hash * 31 + id.charCodeAt(i)) | 0;
  const rot = (((hash % 100) / 100) * 4.4 - 2.2).toFixed(2);
  const dx = ((((hash >> 3) % 100) / 100) * 8 - 4).toFixed(1);
  const dy = (index * 8 + (((hash >> 5) % 100) / 100) * 4 - 2).toFixed(1);
  const scale = (1 - index * 0.025).toFixed(3);
  return { rot, dx, dy, scale };
}

export function renderStack(container, state, onDecide) {
  container.innerHTML = "";
  const current = state.current_item;
  if (!current) return;

  const stackItems = [current, ...(state.upcoming_items || []).slice(0, 2)];

  for (let i = stackItems.length - 1; i >= 0; i--) {
    const item = stackItems[i];
    const isTop = (i === 0);
    const { rot, dx, dy, scale } = getCardOrganicTransform(i, item.id);
    const cardEl = document.createElement("div");
    cardEl.className = isTop ? "square-card active-card" : `square-card under-card layer-${i}`;
    cardEl.dataset.itemId = item.id;
    cardEl.dataset.baseTransform = `translate3d(${dx}px, ${dy}px, 0) rotate(${rot}deg) scale(${scale})`;
    cardEl.style.transform = cardEl.dataset.baseTransform;
    cardEl.style.zIndex = `${10 - i}`;

    const badges = (item.badges || []).map(b => `<span class="badge-tag ${escapeHtml(b.variant || 'neutral')}">${escapeHtml(b.label)}</span>`).join("");
    const bullets = (item.bullets || []).map(b => `<li class="bullet-item">${escapeHtml(b)}</li>`).join("");
    const descriptionHtml = item.description ? `<p class="card-description">${escapeHtml(item.description)}</p>` : "";

    cardEl.innerHTML = `
      <div class="card-inner">
        <div class="card-badges">${badges}</div>
        <h3 class="card-title">${escapeHtml(item.title)}</h3>
        ${descriptionHtml}
        ${bullets ? `<ul class="bullet-list">${bullets}</ul>` : ""}
      </div>
    `;

    if (isTop) bindDragAndSwipe(cardEl, item, onDecide);
    container.appendChild(cardEl);
  }
}

export function attachClassifierSuggestion(container, itemId, prediction) {
  if (!container || !prediction) return;
  const cardEl = container.querySelector(`.square-card[data-item-id="${CSS.escape(itemId)}"]`);
  if (!cardEl) return;
  const badgesEl = cardEl.querySelector(".card-badges");
  if (!badgesEl) return;
  let pill = badgesEl.querySelector(".badge-tag.classifier-pill");
  if (!pill) {
    pill = document.createElement("span");
    pill.className = "badge-tag classifier-pill";
    badgesEl.appendChild(pill);
  }
  const confText = prediction.confidence ? ` (${prediction.confidence}%)` : "";
  pill.textContent = `Suggestion : ${prediction.label}${confText}`;
}

function bindDragAndSwipe(cardEl, item, onDecide) {
  let isDown = false, startX = 0, startY = 0, currentX = 0, currentY = 0;
  const edgeIndicators = {
    west: document.querySelector(".edge-indicator.west"),
    east: document.querySelector(".edge-indicator.east"),
    north: document.querySelector(".edge-indicator.north"),
    south: document.querySelector(".edge-indicator.south"),
  };

  const clearEdges = () => Object.values(edgeIndicators).forEach(el => el?.classList.remove("active"));
  const setEdge = (dir) => {
    clearEdges();
    if (dir && edgeIndicators[dir]) edgeIndicators[dir].classList.add("active");
  };

  const onStart = (clientX, clientY) => {
    isDown = true;
    startX = clientX;
    startY = clientY;
    currentX = 0;
    currentY = 0;
    cardEl.style.transition = "none";
  };

  const onMove = (clientX, clientY) => {
    if (!isDown) return;
    currentX = clientX - startX;
    currentY = clientY - startY;
    const rotate = currentX * 0.05;
    cardEl.style.transform = `translate3d(${currentX}px, ${currentY}px, 0) rotate(${rotate}deg)`;

    const absX = Math.abs(currentX), absY = Math.abs(currentY);
    if (absX < 30 && absY < 30) { setEdge(null); return; }
    if (absX >= absY) setEdge(currentX > 0 ? "east" : "west");
    else setEdge(currentY > 0 ? "south" : "north");
  };

  const onEnd = () => {
    if (!isDown) return;
    isDown = false;
    clearEdges();
    const absX = Math.abs(currentX), absY = Math.abs(currentY);
    let dir = null;
    if (absX >= SWIPE_THRESHOLD && absX >= absY) dir = currentX > 0 ? "east" : "west";
    else if (absY >= SWIPE_THRESHOLD) dir = currentY > 0 ? "south" : "north";

    const action = (item.actions || []).find(a => a.direction === dir);
    if (dir && action) {
      cardEl.style.transition = "transform 0.28s cubic-bezier(0.2, 0.8, 0.2, 1), opacity 0.28s ease";
      cardEl.style.transform = `translate3d(${currentX * 3.5}px, ${currentY * 3.5}px, 0) rotate(${currentX * 0.15}deg)`;
      cardEl.style.opacity = "0";
      setTimeout(() => onDecide(action.id), 260);
    } else {
      cardEl.style.transition = "transform 0.25s cubic-bezier(0.34, 1.56, 0.64, 1)";
      cardEl.style.transform = cardEl.dataset.baseTransform;
    }
  };

  // Tactile mobile : passive=false + preventDefault garantit que la carte suit le doigt
  cardEl.addEventListener("touchstart", e => {
    if (e.touches.length === 1) onStart(e.touches[0].clientX, e.touches[0].clientY);
  }, { passive: true });

  cardEl.addEventListener("touchmove", e => {
    if (!isDown || e.touches.length !== 1) return;
    if (e.cancelable) e.preventDefault();
    onMove(e.touches[0].clientX, e.touches[0].clientY);
  }, { passive: false });

  cardEl.addEventListener("touchend", onEnd, { passive: true });
  cardEl.addEventListener("touchcancel", onEnd, { passive: true });

  // Souris desktop (PointerEvents sans conflit touch)
  cardEl.addEventListener("pointerdown", e => {
    if (e.pointerType === "touch") return;
    onStart(e.clientX, e.clientY);
    cardEl.setPointerCapture(e.pointerId);
  });
  cardEl.addEventListener("pointermove", e => {
    if (e.pointerType === "touch") return;
    onMove(e.clientX, e.clientY);
  });
  const finishMouse = e => {
    if (e.pointerType === "touch") return;
    onEnd();
    try { cardEl.releasePointerCapture(e.pointerId); } catch {}
  };
  cardEl.addEventListener("pointerup", finishMouse);
  cardEl.addEventListener("pointercancel", finishMouse);
}
