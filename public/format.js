// Pure helpers (no DOM): importable by app.js, deck-form.js and the Node tests.

// "N décision(s) · ~X min" : X is rounded up; under a minute reads "moins d'une minute".
export function formatDecisionSummary(count, activeSeconds) {
  const n = Number.isFinite(count) ? Math.max(0, Math.trunc(count)) : 0;
  const secs = Number.isFinite(activeSeconds) ? Math.max(0, activeSeconds) : 0;
  const noun = n === 1 ? "décision" : "décisions";
  const duration = secs < 60 ? "moins d'une minute" : `~${Math.ceil(secs / 60)} min`;
  return `${n} ${noun} · ${duration}`;
}

// One card per line. "titre :: détail" (first " :: " with spaces around) gives {title, description};
// otherwise (no separator, or one side empty) the whole trimmed line is the title.
export function parseCardLine(line) {
  const text = String(line ?? "").trim();
  const match = /\s::\s/.exec(text);
  if (!match) return text;
  const title = text.slice(0, match.index).trim();
  const description = text.slice(match.index + match[0].length).trim();
  if (!title || !description) return text;
  return { title, description };
}
