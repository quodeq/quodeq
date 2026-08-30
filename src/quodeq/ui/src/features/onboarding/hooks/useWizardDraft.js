import { readJSON, readString, removeKey, writeJSON, writeString } from '../../../adapters/storage.js';

export const DRAFT_KEY = 'quodeq_onboarding_draft';
const DRAFT_TTL_MS = 24 * 60 * 60 * 1000;
export const SKIPPED_KEY = 'quodeq_onboarding_skipped';

/**
 * Save wizard state snapshot to localStorage with a savedAt timestamp.
 * Silently no-ops when localStorage is unavailable (private browsing / quota).
 */
export function saveDraft(snapshot) {
  writeJSON(DRAFT_KEY, { ...snapshot, savedAt: Date.now() });
}

/**
 * Load wizard state snapshot. Returns null if no draft exists, the draft
 * is unparseable, or the draft is older than 24h.
 */
export function loadDraft() {
  const parsed = readJSON(DRAFT_KEY);
  if (!parsed || typeof parsed !== 'object') return null;
  if (typeof parsed.savedAt !== 'number') return null;
  if (Date.now() - parsed.savedAt > DRAFT_TTL_MS) return null;
  return parsed;
}

export function clearDraft() {
  removeKey(DRAFT_KEY);
}

/** Mark that the user dismissed the welcome step ("Maybe later"). */
export function markWelcomeSkipped(storage) {
  writeString(SKIPPED_KEY, 'true', storage);
}

/** Whether the user previously dismissed the welcome step. */
export function wasWelcomeSkipped(storage) {
  return readString(SKIPPED_KEY, null, storage) === 'true';
}
