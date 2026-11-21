// Module Stack : Rendu de la pile réelle carrée & physique de drag/swipe
import { escapeHtml } from "./escape.js";

const SWIPE_THRESHOLD = 85;
// Below this distance the gesture is still a hesitation: no feedback yet.
const SWIPE_FEEDBACK_MIN = 30;
const DIRECTION_ARROWS = { east: "→", west: "←", north: "↑", south: "↓" };

function getCardOrganicTransform(index, id) {
  let hash = 0;
  for (let i = 0; i < (id || "").length; i++) hash = (hash * 31 + id.charCodeAt(i)) | 0;
  // Unsigned: a negative hash used to double the tilt and push the card off the left edge.
  const h = hash >>> 0;
  // On wide screens the card is large: a full tilt makes its text slant and blur.
  const tilt = (typeof matchMedia === "function" && matchMedia("(min-width: 1000px)").matches) ? 0.15 : 1;
  const rot = ((((h % 100) / 100) * 4.4 - 2.2) * tilt).toFixed(2);
  const dx = ((((h >>> 3) % 100) / 100) * 8 - 4).toFixed(1);
  const dy = (index * 8 + (((h >>> 5) % 100) / 100) * 4 - 2).toFixed(1);
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
    const bullets = (item.bullets || []).map(b => `<li class="bullet-item">${hasMarkdown(b) ? renderInlineMarkdown(b) : escapeHtml(b)}</li>`).join("");
    const descriptionHtml = item.description ? `<div class="card-description">${hasMarkdown(item.description) ? renderBlockMarkdown(item.description) : escapeHtml(item.description)}</div>` : "";

    cardEl.innerHTML = `
      <div class="card-inner">
        <div class="card-badges">${badges}</div>
        <h3 class="card-title">${escapeHtml(item.title)}</h3>
        ${descriptionHtml}
        ${bullets ? `<ul class="bullet-list">${bullets}</ul>` : ""}
      </div>
      ${isTop ? '<div class="swipe-hint" aria-hidden="true"></div>' : ""}
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
  let gestureMode = null;
  const innerEl = () => cardEl.querySelector(".card-inner");
  const edgeIndicators = {
    west: document.querySelector(".edge-indicator.west"),
    east: document.querySelector(".edge-indicator.east"),
    north: document.querySelector(".edge-indicator.north"),
    south: document.querySelector(".edge-indicator.south"),
  };

  const hintEl = () => cardEl.querySelector(".swipe-hint");
  const actionFor = (dir) => (item.actions || []).find(a => a.direction === dir);

  const clearEdges = () => Object.values(edgeIndicators).forEach(el => el?.classList.remove("active"));
  // A direction without an action shows nothing: no edge band, no label.
  const setEdge = (dir) => {
    clearEdges();
    if (dir && actionFor(dir) && edgeIndicators[dir]) edgeIndicators[dir].classList.add("active");
  };
  const clearHint = () => {
    const el = hintEl();
    if (el) { el.className = "swipe-hint"; el.textContent = ""; }
    delete cardEl.dataset.swipe;
  };
  // Label and colour of the action that releasing now would apply; it gets stronger near the threshold.
  const showHint = (dir, distance) => {
    const action = actionFor(dir);
    const el = hintEl();
    if (!action || !el) { clearHint(); return; }
    const progress = Math.min(1, distance / SWIPE_THRESHOLD);
    el.textContent = DIRECTION_ARROWS[dir] + " " + action.label; // textContent: never parsed as HTML
    el.className = `swipe-hint on dir-${dir} tone-${action.color || "neutral"}${progress >= 1 ? " ready" : ""}`;
    el.style.setProperty("--swipe-progress", progress.toFixed(2));
    cardEl.dataset.swipe = dir;
  };

  const onStart = (clientX, clientY) => {
    isDown = true;
    gestureMode = null;
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
    // The label counter-shifts so it stays on screen while the card leaves.
    cardEl.style.setProperty("--swipe-dx", `${currentX}px`);
    cardEl.style.setProperty("--swipe-dy", `${currentY}px`);

    const absX = Math.abs(currentX), absY = Math.abs(currentY);
    if (absX < SWIPE_FEEDBACK_MIN && absY < SWIPE_FEEDBACK_MIN) { setEdge(null); clearHint(); return; }
    const dir = absX >= absY ? (currentX > 0 ? "east" : "west") : (currentY > 0 ? "south" : "north");
    setEdge(dir);
    showHint(dir, Math.max(absX, absY));
  };

  const onEnd = (cancelled = false) => {
    if (!isDown) return;
    isDown = false;
    clearEdges();
    clearHint();
    const absX = Math.abs(currentX), absY = Math.abs(currentY);
    let dir = null;
    // A cancelled gesture (touchcancel / pointercancel) never decides, whatever the distance.
    if (cancelled) dir = null;
    else if (absX >= SWIPE_THRESHOLD && absX >= absY) dir = currentX > 0 ? "east" : "west";
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

  // Tactile mobile : swipe horizontal = décision, scroll vertical natif = lecture
  cardEl.addEventListener("touchstart", e => {
    if (e.touches.length === 1) onStart(e.touches[0].clientX, e.touches[0].clientY);
  }, { passive: true });

  cardEl.addEventListener("touchmove", e => {
    if (e.touches.length !== 1) return;
    if (!isDown && gestureMode !== "swipe") return;
    const dx = e.touches[0].clientX - startX;
    const dy = e.touches[0].clientY - startY;
    // Tant que le geste n'est pas un swipe, ne pas bouger la carte et ne pas
    // annuler le scroll natif. Le faire avant le classement laisse la carte
    // décalée après la première lecture, et iOS ne reprend plus le scroll.
    if (gestureMode === null) {
      if (Math.abs(dx) < 12 && Math.abs(dy) < 12) return;
      const inner = innerEl();
      const canScroll = inner && inner.scrollHeight > inner.clientHeight + 4;
      const vertical = Math.abs(dy) > Math.abs(dx);
      if (canScroll && vertical) {
        const atTop = inner.scrollTop <= 0;
        const atBottom = inner.scrollTop + inner.clientHeight >= inner.scrollHeight - 1;
        const pastEdge = (dy > 0 && atTop) || (dy < 0 && atBottom);
        if (!pastEdge) {
          gestureMode = "scroll";
          isDown = false;
          cardEl.style.transition = "none";
          cardEl.style.transform = cardEl.dataset.baseTransform;
          clearEdges();
          clearHint();
          return;
        }
      }
      gestureMode = "swipe";
      startX = e.touches[0].clientX;
      startY = e.touches[0].clientY;
    }
    if (gestureMode !== "swipe" || !isDown) return;
    if (e.cancelable) e.preventDefault();
    onMove(e.touches[0].clientX, e.touches[0].clientY);
  }, { passive: false });

  cardEl.addEventListener("touchend", () => onEnd(), { passive: true });
  cardEl.addEventListener("touchcancel", () => onEnd(true), { passive: true });

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
  const finishMouse = (e, cancelled = false) => {
    if (e.pointerType === "touch") return;
    onEnd(cancelled);
    try { cardEl.releasePointerCapture(e.pointerId); } catch {}
  };
  cardEl.addEventListener("pointerup", e => finishMouse(e));
  cardEl.addEventListener("pointercancel", e => finishMouse(e, true));
}

function hasMarkdown(str) {
  if (!str || typeof str !== "string") return false;
  return /(\*\*.+?\*\*|\*[^*]+?\*|`[^`]+?`|\[.+?\]\(https?:\/\/.+?\)|^#{1,3}\s|^&gt;\s|^&gt; |> [-*] |\n)/m.test(str)
    || /(^|\n)#{1,3}\s/.test(str) || /(^|\n)>\s/.test(str) || /(^|\n)[-*] /.test(str);
}

function inlineMarkdown(escaped) {
  let out = escaped;
  out = out.replace(/`([^`]+?)`/g, '<code class="md-code">$1</code>');
  out = out.replace(/\*\*([^*]+?)\*\*/g, "<strong>$1</strong>");
  out = out.replace(/(^|[^*])\*([^*]+?)\*(?![*])/g, "$1<em>$2</em>");
  out = out.replace(/\[([^\]]+?)\]\((https?:\/\/[^)]+?)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
  return out;
}

function renderInlineMarkdown(str) {
  return inlineMarkdown(escapeHtml(str));
}

function renderBlockMarkdown(str) {
  const paras = String(str).split(/\n{2,}/).map(par => {
    let h = escapeHtml(par);
    h = h.replace(/^(#{1,3})\s+(.+)$/m, '<span class="md-h">$2</span>');
    h = h.replace(/^&gt;\s?(.*)$/gm, '<span class="md-quote">$1</span>');
    h = inlineMarkdown(h);
    h = h.replace(/\n/g, "<br>");
    return h;
  });
  return paras.join("<br><br>");
}

