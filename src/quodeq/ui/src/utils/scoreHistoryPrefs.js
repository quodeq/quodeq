import {
  SCORE_HISTORY_GRANULARITY_STORAGE_KEY,
  SCORE_HISTORY_GRANULARITIES,
  DEFAULT_SCORE_HISTORY_GRANULARITY,
} from '../constants.js';

/**
 * Read the persisted score-history grouping granularity.
 * Returns 'day' when unset or invalid. Mirrors visibleStandards.js.
 */
export function readScoreHistoryGranularity(storage = localStorage) {
  try {
    const raw = storage.getItem(SCORE_HISTORY_GRANULARITY_STORAGE_KEY);
    return SCORE_HISTORY_GRANULARITIES.includes(raw) ? raw : DEFAULT_SCORE_HISTORY_GRANULARITY;
  } catch {
    return DEFAULT_SCORE_HISTORY_GRANULARITY;
  }
}

/** Persist the granularity. Silently ignores invalid values and storage errors. */
export function writeScoreHistoryGranularity(value, storage = localStorage) {
  if (!SCORE_HISTORY_GRANULARITIES.includes(value)) return;
  try {
    storage.setItem(SCORE_HISTORY_GRANULARITY_STORAGE_KEY, value);
  } catch {
    /* storage unavailable (private mode, quota) — non-fatal */
  }
}
