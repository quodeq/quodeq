import { useState, useCallback } from 'react';
import { providerKey, notifyProviderSettingsChanged } from '../../../constants.js';
import { useSidePane } from '../../side-pane/SidePaneContext.jsx';
import { saveProviderKey } from '../../../api/providers.js';
import { t } from '../../../strings/index.js';

// Written to storage instead of the raw key once the backend confirms it
// stored one, so the "configured" state survives a reload without ever
// putting the credential itself back into localStorage.
export const API_KEY_CONFIGURED_SENTINEL = '•configured•';

const SETTINGS = ['model', 'model-analysis', 'model-fast', 'model-balanced', 'model-thorough', 'subagents', 'time-limit', 'per-dimension', 'verify', 'api-key', 'api-base', 'cmd-path'];
const DEFAULTS = {
  'model': '',
  'model-analysis': '',
  'model-fast': '',
  'model-balanced': '',
  'model-thorough': '',
  'subagents': '1',
  'time-limit': '0',
  // Grouped is the engine's actual default; the pill must not claim
  // per-dimension for an untouched toggle.
  'per-dimension': 'false',
  'verify': 'true',
  'api-key': '',
  'api-base': '',
  'cmd-path': '',
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

export function saveProviderSetting(providerId, key, value, storage = localStorage, { onPersistError } = {}) {
  try {
    storage.setItem(providerKey(providerId, key), String(value));
  } catch (err) {
    console.warn('[useProviderSettings] Could not persist setting to storage:', err);
    onPersistError?.(err);
  }
}

// The key itself never touches localStorage: it goes straight to the
// backend's secure store, and only the "configured" sentinel is cached
// locally afterward.
export async function saveProviderApiKey(providerId, apiKey, storage = localStorage, { onPersistError } = {}) {
  try {
    const { stored } = await saveProviderKey(providerId, apiKey);
    if (!stored) throw new Error('Provider key was not stored');
    storage.setItem(providerKey(providerId, 'api-key'), API_KEY_CONFIGURED_SENTINEL);
    return true;
  } catch (err) {
    console.warn('[useProviderSettings] Could not save provider API key:', err);
    onPersistError?.(err);
    return false;
  }
}

export default function useProviderSettings(providerId, defaults, { storage = localStorage } = {}) {
  const { showToast } = useSidePane();
  const [state, setState] = useState(() => loadProviderState(providerId, defaults, storage));

  const update = useCallback((key, value) => {
    setState(prev => ({ ...prev, [key]: String(value) }));
    const onPersistError = () => showToast(t('settings.persistError'));
    if (key === 'api-key') {
      saveProviderApiKey(providerId, String(value), storage, { onPersistError }).then((ok) => {
        if (ok) setState(prev => ({ ...prev, [key]: API_KEY_CONFIGURED_SENTINEL }));
      });
    } else {
      saveProviderSetting(providerId, key, value, storage, { onPersistError });
    }
    // Let the assistant gate re-read: in Default mode it mirrors the analysis
    // model, so a model change here must update its display live.
    notifyProviderSettingsChanged();
  }, [providerId, storage, showToast]);

  return { state, update };
}
