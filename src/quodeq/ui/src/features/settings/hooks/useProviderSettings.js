import { useState, useCallback, useEffect, useRef } from 'react';
import {
  providerKey, notifyProviderSettingsChanged, PROVIDER_CONFIGURED_MARKER,
  SETTING_KEY_TIME_LIMIT, SETTING_KEY_API_KEY,
} from '../../../constants.js';
import { useSidePane } from '../../side-pane/SidePaneContext.jsx';
import { saveProviderKey } from '../../../api/providers.js';
import { t } from '../../../strings/index.js';

export { PROVIDER_CONFIGURED_MARKER };

const SETTINGS = ['model', 'model-analysis', 'model-fast', 'model-balanced', 'model-thorough', 'subagents', SETTING_KEY_TIME_LIMIT, 'per-dimension', 'verify', SETTING_KEY_API_KEY, 'api-base', 'cmd-path'];
const DEFAULTS = {
  'model': '',
  'model-analysis': '',
  'model-fast': '',
  'model-balanced': '',
  'model-thorough': '',
  'subagents': '1',
  [SETTING_KEY_TIME_LIMIT]: '0',
  // Grouped is the engine's actual default; the pill must not claim
  // per-dimension for an untouched toggle.
  'per-dimension': 'false',
  'verify': 'true',
  [SETTING_KEY_API_KEY]: '',
  'api-base': '',
  'cmd-path': '',
};

// Legacy storage key fallback, only consulted when the new key has no value.
const LEGACY_KEY_MAP = { [SETTING_KEY_TIME_LIMIT]: 'pool-budget' };

/**
 * Reads one provider's settings, falling back to `overrides` and then the
 * shipped defaults for anything unset.
 *
 * The api-key slot comes back blank when the backend holds the key (the local
 * value is only a "configured" marker), so a caller can never send the marker
 * to a provider as a credential. Legacy key names are migrated on read;
 * `onPersistError` reports a migration that could not be written back.
 */
export function loadProviderState(providerId, overrides, storage = localStorage, { onPersistError } = {}) {
  const merged = { ...DEFAULTS, ...overrides };
  const state = {};
  for (const key of SETTINGS) {
    let value = storage.getItem(providerKey(providerId, key));
    if (key === SETTING_KEY_API_KEY && value === PROVIDER_CONFIGURED_MARKER) {
      // The sentinel means "the backend holds a key", not "here is a key".
      // Consumers of state['api-key'] (OmlxTab hands it straight to
      // getOmlxModels / testOmlxConcurrency as a real credential) would
      // otherwise send the literal '•configured•' to a provider. Blank it
      // out. A genuine legacy raw value is still returned as-is below, so
      // installs that saved one before the secure-storage change keep
      // working.
      state[key] = '';
      continue;
    }
    if (value === null && LEGACY_KEY_MAP[key]) {
      // Back-compat: read old key, migrate to new key, drop the old one.
      const legacy = storage.getItem(providerKey(providerId, LEGACY_KEY_MAP[key]));
      if (legacy !== null) {
        value = legacy;
        try {
          storage.setItem(providerKey(providerId, key), legacy);
          storage.removeItem(providerKey(providerId, LEGACY_KEY_MAP[key]));
        } catch (err) {
          console.warn('[useProviderSettings] Could not migrate legacy setting in storage:', err);
          onPersistError?.(err);
        }
      }
    }
    state[key] = value ?? merged[key];
  }
  return state;
}

/**
 * Persists one provider setting. Storage failures are reported through
 * `onPersistError` rather than thrown — a setting that cannot be cached must
 * not break the screen.
 */
export function saveProviderSetting(providerId, key, value, storage = localStorage, { onPersistError } = {}) {
  try {
    storage.setItem(providerKey(providerId, key), String(value));
  } catch (err) {
    console.warn('[useProviderSettings] Could not persist setting to storage:', err);
    onPersistError?.(err);
  }
}

/**
 * The key itself never touches localStorage: it goes straight to the
 * backend's secure store, and only the "configured" sentinel is cached
 * locally afterward.
 */
export async function saveProviderApiKey(providerId, apiKey, storage = localStorage, { onPersistError } = {}) {
  try {
    const { stored } = await saveProviderKey(providerId, apiKey);
    if (!stored) throw new Error('Provider key was not stored');
    storage.setItem(providerKey(providerId, SETTING_KEY_API_KEY), PROVIDER_CONFIGURED_MARKER);
    return true;
  } catch (err) {
    console.warn('[useProviderSettings] Could not save provider API key:', err);
    onPersistError?.(err);
    return false;
  }
}

/**
 * One provider's settings plus the updater the tabs write through.
 *
 * Reads apply the same defaults and legacy migration as loadProviderState; a
 * migration that fails to persist is toasted after mount rather than during
 * render. `storage` is injectable for tests.
 *
 * @returns {{state: object, update: Function}}
 */
export default function useProviderSettings(providerId, defaults, { storage = localStorage } = {}) {
  const { showToast } = useSidePane();
  // loadProviderState runs inside the useState initializer, i.e. during
  // render, and its legacy-key migration can fail to persist. showToast
  // updates SidePaneContext, and a state update from another component's
  // render is a React error ("Cannot update a component while rendering a
  // different component"). Record the failure here; toast it from the mount
  // effect below.
  const migrationFailedRef = useRef(false);
  const [state, setState] = useState(() => loadProviderState(providerId, defaults, storage, {
    onPersistError: () => { migrationFailedRef.current = true; },
  }));
  useEffect(() => {
    if (migrationFailedRef.current) {
      migrationFailedRef.current = false;
      showToast(t('settings.persistError'));
    }
  }, [showToast]);

  const update = useCallback((key, value) => {
    setState(prev => ({ ...prev, [key]: String(value) }));
    const onPersistError = () => showToast(t('settings.persistError'));
    if (key === SETTING_KEY_API_KEY) {
      // Fire and forget: saveProviderApiKey catches its own failures, reports
      // them through onPersistError and resolves false, so there is nothing
      // left here to reject.
      void saveProviderApiKey(providerId, String(value), storage, { onPersistError }).then((ok) => {
        // Clear the field rather than parking the sentinel in live state:
        // state['api-key'] is passed to providers as a real credential (see
        // OmlxTab), and the sentinel is not one. Storage still records it,
        // which is what survives a reload.
        if (ok) setState(prev => ({ ...prev, [key]: '' }));
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
