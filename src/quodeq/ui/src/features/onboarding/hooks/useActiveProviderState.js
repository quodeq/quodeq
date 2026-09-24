import { useEffect, useState } from 'react';
import { getProviderConfigs } from '../../../api/index.js';
import { ACTIVE_PROVIDER_KEY, providerKey, SETTING_KEY_TIME_LIMIT } from '../../../constants.js';
import { readString } from '../../../adapters/storage.js';

// Poll interval for mirroring localStorage: ProviderTabs and its children
// write directly and the `storage` event only fires cross-tab. Short enough
// to feel live while the user picks; the picker is interactive and on screen.
const ACTIVE_PROVIDER_POLL_MS = 400;

// Nothing selected, or storage unavailable. Frozen so a caller cannot mutate
// the shared object under the next reader.
const NO_ACTIVE_PROVIDER = Object.freeze({ id: null, model: null, timeLimitS: null });

/**
 * The provider the user has selected, with its model and time limit (0 meaning
 * unlimited, null meaning unset so the caller's default applies). All-null when
 * nothing is selected or storage is unavailable.
 *
 * @returns {{id: string|null, model: string|null, timeLimitS: number|null}}
 */
export function readActiveProviderState() {
  try {
    const id = readString(ACTIVE_PROVIDER_KEY, null);
    if (!id) return NO_ACTIVE_PROVIDER;
    const model = readString(providerKey(id, 'model'), null);
    // ProviderTabs persists time-limit per provider as a stringified number of
    // seconds. Treat 0 as unlimited; missing key falls back to null so the
    // wizard's existing default applies.
    const tlRaw = readString(providerKey(id, SETTING_KEY_TIME_LIMIT), null);
    const timeLimitS = tlRaw === null ? null : Number.parseInt(tlRaw, 10);
    return { id, model, timeLimitS: Number.isFinite(timeLimitS) ? timeLimitS : null };
  } catch (err) {
    console.warn('[useActiveProviderState] could not read active provider state:', err);
    return NO_ACTIVE_PROVIDER;
  }
}

/**
 * ProviderStep.jsx's provider-config fetch and localStorage-polled active
 * provider/model mirror. Extracted verbatim.
 */
export function useActiveProviderState() {
  const [providerConfigs, setProviderConfigs] = useState({});
  // Mirror localStorage so Continue updates as the user picks a provider/model.
  const [activeProvider, setActiveProvider] = useState(readActiveProviderState);

  useEffect(() => {
    getProviderConfigs().then(setProviderConfigs).catch(() => setProviderConfigs({}));
  }, []);

  useEffect(() => {
    const tick = () => setActiveProvider(readActiveProviderState());
    const interval = setInterval(tick, ACTIVE_PROVIDER_POLL_MS);
    window.addEventListener('storage', tick);
    return () => { clearInterval(interval); window.removeEventListener('storage', tick); };
  }, []);

  return { providerConfigs, activeProvider };
}
