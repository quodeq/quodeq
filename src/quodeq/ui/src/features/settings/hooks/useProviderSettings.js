import { useState, useCallback } from 'react';
import { providerKey } from '../../../constants.js';

const SETTINGS = ['model', 'model-analysis', 'model-fast', 'model-balanced', 'model-thorough', 'subagents', 'pool-budget', 'per-dimension', 'verify', 'context-size'];
const DEFAULTS = {
  'model': '',
  'model-analysis': '',
  'model-fast': '',
  'model-balanced': '',
  'model-thorough': '',
  'subagents': '1',
  'pool-budget': '0',
  'per-dimension': 'true',
  'verify': 'true',
  'context-size': '0',
};

function loadProviderState(providerId, overrides) {
  const merged = { ...DEFAULTS, ...overrides };
  const state = {};
  for (const key of SETTINGS) {
    state[key] = localStorage.getItem(providerKey(providerId, key)) ?? merged[key];
  }
  return state;
}

function saveProviderSetting(providerId, key, value) {
  localStorage.setItem(providerKey(providerId, key), String(value));
}

export default function useProviderSettings(providerId, defaults) {
  const [state, setState] = useState(() => loadProviderState(providerId, defaults));

  const update = useCallback((key, value) => {
    setState(prev => ({ ...prev, [key]: String(value) }));
    saveProviderSetting(providerId, key, value);
  }, [providerId]);

  return { state, update };
}
