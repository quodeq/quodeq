/**
 * Single source of truth for a provider's *effective* evaluation settings.
 *
 * Settings only persists a key once the user edits it, so every reader of an
 * unset key must resolve the same default — otherwise the Settings screen,
 * the Evaluate header, and the start payload each tell a different story
 * (e.g. Settings showed "1 subagent / Unlimited" for a cloud provider while
 * the run used 5 / 600s). Both the display and the payload resolve through
 * this module.
 */
import {
  DEFAULT_MAX_SUBAGENTS,
  DEFAULT_TIME_LIMIT_S,
  LOCAL_API_PROVIDERS,
  providerKey,
} from '../constants.js';

/**
 * Effective defaults for a provider when no key was ever written.
 * Local-API providers run one model on the user's own hardware: a single
 * subagent and no time limit. Everything else (CLI + cloud) gets the
 * concurrent default with the 10-minute cap.
 */
export function effectiveProviderDefaults(providerId) {
  const isLocalApi = LOCAL_API_PROVIDERS.has(providerId);
  return {
    subagents: isLocalApi ? 1 : DEFAULT_MAX_SUBAGENTS,
    timeLimitS: isLocalApi ? 0 : DEFAULT_TIME_LIMIT_S,
    // The scan engine defaults to one grouped (consolidated) pass; the
    // display must say so instead of claiming per-dimension.
    perDimension: false,
    verify: true,
  };
}

function readInt(storage, providerId, key) {
  const raw = storage.getItem(providerKey(providerId, key));
  if (raw === null || raw === undefined) return null;
  const parsed = parseInt(raw, 10);
  return Number.isFinite(parsed) ? parsed : null;
}

/**
 * Resolve the settings an evaluation for *providerId* would actually run
 * with: stored values (including an explicit 0 = unlimited) win, anything
 * unset or corrupt falls back to the effective defaults.
 */
export function resolveProviderSettings(providerId, storage = localStorage) {
  const defaults = effectiveProviderDefaults(providerId);
  const get = (key) => storage.getItem(providerKey(providerId, key));
  const subagents = readInt(storage, providerId, 'subagents');
  // Read the new key first; fall back to the legacy 'pool-budget' key.
  const timeLimitS = readInt(storage, providerId, 'time-limit')
    ?? readInt(storage, providerId, 'pool-budget');
  const perDimensionRaw = get('per-dimension');
  const verifyRaw = get('verify');
  return {
    subagents: subagents ?? defaults.subagents,
    timeLimitS: timeLimitS ?? defaults.timeLimitS,
    perDimension: perDimensionRaw === null || perDimensionRaw === undefined
      ? defaults.perDimension
      : perDimensionRaw === 'true',
    verify: verifyRaw === null || verifyRaw === undefined
      ? defaults.verify
      : verifyRaw !== 'false',
  };
}
