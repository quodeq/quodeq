import { readJSON, readString, removeKey, writeJSON, writeString } from '../../../adapters/storage.js';
import { SKIPPED_KEY, SKIPPED_VALUE } from '../wizardSteps.js';
import { MS_PER_DAY } from '../../../utils/time.js';

// Re-exported for useWizardDraft.test.jsx; production code imports the leaf.
export { SKIPPED_KEY };
export const DRAFT_KEY = 'quodeq_onboarding_draft';
const DRAFT_TTL_MS = MS_PER_DAY;

/**
 * Save wizard state snapshot to localStorage with a savedAt timestamp.
 * Silently no-ops when localStorage is unavailable (private browsing / quota).
 * @param {Object} snapshot
 * @param {Storage} [storage] - injectable storage backend; defaults to localStorage
 */
export function saveDraft(snapshot, storage) {
  writeJSON(DRAFT_KEY, { ...snapshot, savedAt: Date.now() }, storage);
}

/**
 * Load wizard state snapshot. Returns null if no draft exists, the draft
 * is unparseable, or the draft is older than 24h.
 * @param {Storage} [storage] - injectable storage backend; defaults to localStorage
 */
export function loadDraft(storage) {
  const parsed = readJSON(DRAFT_KEY, null, storage);
  if (!parsed || typeof parsed !== 'object') return null;
  if (typeof parsed.savedAt !== 'number') return null;
  if (Date.now() - parsed.savedAt > DRAFT_TTL_MS) return null;
  return parsed;
}

/** @param {Storage} [storage] - injectable storage backend; defaults to localStorage */
export function clearDraft(storage) {
  removeKey(DRAFT_KEY, storage);
}

/** Mark that the user dismissed the welcome step ("Maybe later"). */
export function markWelcomeSkipped(storage) {
  writeString(SKIPPED_KEY, SKIPPED_VALUE, storage);
}

/** Whether the user previously dismissed the welcome step. */
export function wasWelcomeSkipped(storage) {
  return readString(SKIPPED_KEY, null, storage) === SKIPPED_VALUE;
}
