export const DEFAULT_MODELS = {
  1: 'haiku',
  2: 'sonnet',
  3: 'opus',
};

export const MODEL_STORAGE_PREFIX = 'cc-model-level-';

export function getLevels(storage = typeof localStorage !== 'undefined' ? localStorage : null) {
  const overrides = {};
  try {
    if (storage) {
      for (const lvl of [1, 2, 3]) {
        const stored = storage.getItem(`${MODEL_STORAGE_PREFIX}${lvl}`);
        if (stored) overrides[lvl] = stored;
      }
    }
  } catch { /* storage unavailable (private browsing) */ }
  return [
    { level: 1, model: overrides[1] || DEFAULT_MODELS[1], label: 'Fast' },
    { level: 2, model: overrides[2] || DEFAULT_MODELS[2], label: 'Balanced' },
    { level: 3, model: overrides[3] || DEFAULT_MODELS[3], label: 'Thorough' },
  ];
}

// Static reference for components that don't need live overrides
export const LEVELS = getLevels();

export const STORAGE_KEY = 'quodeq-analysis-power';
