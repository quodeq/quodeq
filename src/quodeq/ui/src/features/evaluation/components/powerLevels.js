export const DEFAULT_MODELS = {
  1: 'haiku',
  2: 'sonnet',
  3: 'opus',
};

export const MODEL_STORAGE_PREFIX = 'cc-model-level-';

const MAX_POWER_LEVEL = 3;

export function getLevels(storage = typeof localStorage !== 'undefined' ? localStorage : null) {
  const overrides = {};
  try {
    if (storage) {
      for (const lvl of [1, 2, MAX_POWER_LEVEL]) {
        const stored = storage.getItem(`${MODEL_STORAGE_PREFIX}${lvl}`);
        if (stored) overrides[lvl] = stored;
      }
    }
  } catch (err) { console.debug('localStorage unavailable, using default models:', err?.message); }
  return [
    { level: 1, model: overrides[1] || DEFAULT_MODELS[1], label: 'Fast' },
    { level: 2, model: overrides[2] || DEFAULT_MODELS[2], label: 'Balanced' },
    { level: 3, model: overrides[3] || DEFAULT_MODELS[3], label: 'Thorough' },
  ];
}

// Static reference for components that don't need live overrides
export const LEVELS = getLevels();

export { ANALYSIS_POWER_STORAGE_KEY as STORAGE_KEY } from '../../../constants.js';
