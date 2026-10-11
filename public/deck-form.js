// Module DeckForm : création d'un deck depuis l'interface d'accueil
import { createDeck } from "./api.js";

const CREATE_BUTTON_LABEL = "Créer et commencer à trier";

function showError(message) {
  document.getElementById("deck-create-error").textContent = message || "";
}

export function initDeckForm(callbacks = {}) {
  const onCreated = callbacks.onCreated || null;
  const toggle = document.getElementById("deck-create-toggle");
  const form = document.getElementById("deck-create-form");
  const submitBtn = document.getElementById("deck-create-submit");
  if (!toggle || !form || !submitBtn) return;

  const setOpen = (isOpen) => {
    form.hidden = !isOpen;
    toggle.setAttribute("aria-expanded", String(isOpen));
    if (isOpen) document.getElementById("deck-create-title-input")?.focus();
  };

  toggle.addEventListener("click", () => setOpen(form.hidden));

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    submitBtn.disabled = true;
    submitBtn.textContent = "Création…";
    showError("");
    try {
      const items = document.getElementById("deck-create-items-input").value
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean);
      const result = await createDeck({
        title: document.getElementById("deck-create-title-input").value.trim(),
        template: document.getElementById("deck-create-template-input").value,
        items,
      });
      form.reset();
      setOpen(false);
      onCreated?.(result.deck_id);
    } catch (err) {
      showError(err.message);
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = CREATE_BUTTON_LABEL;
    }
  });
}