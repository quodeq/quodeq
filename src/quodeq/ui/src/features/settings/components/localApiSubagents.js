import { MIN_SUBAGENTS, MAX_SUBAGENTS } from '../../../constants.js';

// Every provider tab commits its max-parallel-agents entry to [MIN, MAX] so
// an empty or garbage entry can't persist to storage. Only the value an
// unparseable entry falls back to differs per tab.
export const LOCAL_DEFAULT_SUBAGENTS = '1';

/**
 * Clamp a subagent-count entry into [MIN_SUBAGENTS, MAX_SUBAGENTS].
 *
 * @param {string} raw The entry as typed.
 * @param {string} fallback Value to use when `raw` is not a number.
 * @returns {string} The clamped count, as a string ready to persist.
 */
export function clampSubagentsTo(raw, fallback) {
  const n = parseInt(raw, 10);
  if (Number.isNaN(n)) return fallback;
  return String(Math.max(MIN_SUBAGENTS, Math.min(MAX_SUBAGENTS, n)));
}

// The local-API tabs' clamp: a single subagent when the entry is unusable.
export function clampSubagents(raw) {
  return clampSubagentsTo(raw, LOCAL_DEFAULT_SUBAGENTS);
}
