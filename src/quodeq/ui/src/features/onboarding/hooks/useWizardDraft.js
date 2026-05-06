export const DRAFT_KEY = 'quodeq_onboarding_draft';
const DRAFT_TTL_MS = 24 * 60 * 60 * 1000;

/**
 * Save wizard state snapshot to localStorage with a savedAt timestamp.
 * Silently no-ops when localStorage is unavailable (private browsing / quota).
 */
export function saveDraft(snapshot) {
  try {
    localStorage.setItem(DRAFT_KEY, JSON.stringify({ ...snapshot, savedAt: Date.now() }));
  } catch {
    /* private browsing or quota — wizard still works without persistence */
  }
}

/**
 * Load wizard state snapshot. Returns null if no draft exists, the draft
 * is unparseable, or the draft is older than 24h.
 */
export function loadDraft() {
  let raw = null;
  try {
    raw = localStorage.getItem(DRAFT_KEY);
  } catch {
    return null;
  }
  if (!raw) return null;
  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!parsed || typeof parsed !== 'object') return null;
  if (typeof parsed.savedAt !== 'number') return null;
  if (Date.now() - parsed.savedAt > DRAFT_TTL_MS) return null;
  return parsed;
}

export function clearDraft() {
  try {
    localStorage.removeItem(DRAFT_KEY);
  } catch {
    /* see above */
  }
}
