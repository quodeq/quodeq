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

/**
 * Mark that the user dismissed the welcome step ("skip for now"). The flag
 * records the server's instance id (the state folder's identity), so a
 * wiped state folder, which gets a new id, shows the welcome again even
 * though the browser storage outlived the folder. Without an id (an older
 * server) it falls back to the plain flag.
 * @param {Storage} [storage]
 * @param {string|null} [instanceId]
 */
export function markWelcomeSkipped(storage, instanceId = null) {
  writeString(SKIPPED_KEY, instanceId || SKIPPED_VALUE, storage);
}

/**
 * Whether the user dismissed the welcome for THIS state folder. With an
 * instance id known, only a flag written for that id counts; a flag from
 * another folder (or the plain legacy value) does not.
 * @param {Storage} [storage]
 * @param {string|null} [instanceId]
 */
export function wasWelcomeSkipped(storage, instanceId = null) {
  const flag = readString(SKIPPED_KEY, null, storage);
  if (!flag) return false;
  return instanceId ? flag === instanceId : flag === SKIPPED_VALUE;
}
