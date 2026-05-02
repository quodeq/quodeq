import { useState, useCallback } from 'react';
import { providerKey } from '../../../constants.js';

const SETTINGS = ['model', 'model-analysis', 'model-fast', 'model-balanced', 'model-thorough', 'subagents', 'time-limit', 'per-dimension', 'verify'];
const DEFAULTS = {
  'model': '',
  'model-analysis': '',
  'model-fast': '',
  'model-balanced': '',
  'model-thorough': '',
  'subagents': '1',
  'time-limit': '0',
  'per-dimension': 'true',
  'verify': 'true',
};

// Legacy storage key fallback, only consulted when the new key has no value.
const LEGACY_KEY_MAP = { 'time-limit': 'pool-budget' };

function loadProviderState(providerId, overrides, storage = localStorage) {
  const merged = { ...DEFAULTS, ...overrides };
  const state = {};
  for (const key of SETTINGS) {
    let value = storage.getItem(providerKey(providerId, key));
    if (value === null && LEGACY_KEY_MAP[key]) {
      // Back-compat: read old key, migrate to new key, drop the old one.
      const legacy = storage.getItem(providerKey(providerId, LEGACY_KEY_MAP[key]));
      if (legacy !== null) {
        value = legacy;
        try {
          storage.setItem(providerKey(providerId, key), legacy);
          storage.removeItem(providerKey(providerId, LEGACY_KEY_MAP[key]));
        } catch { /* storage write may fail in tests with restricted mocks */ }
      }
    }
    state[key] = value ?? merged[key];
  }
  return state;
}

function saveProviderSetting(providerId, key, value, storage = localStorage) {
  storage.setItem(providerKey(providerId, key), String(value));
}

export default function useProviderSettings(providerId, defaults, { storage = localStorage } = {}) {
  const [state, setState] = useState(() => loadProviderState(providerId, defaults, storage));

  const update = useCallback((key, value) => {
    setState(prev => ({ ...prev, [key]: String(value) }));
    saveProviderSetting(providerId, key, value, storage);
  }, [providerId, storage]);

  return { state, update };
}
