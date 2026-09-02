import { useEffect, useState } from 'react';
import { getProviderConfigs } from '../../../api/index.js';
import { ACTIVE_PROVIDER_KEY, providerKey } from '../../../constants.js';

export function readActiveProviderState() {
  try {
    const id = localStorage.getItem(ACTIVE_PROVIDER_KEY) || null;
    if (!id) return { id: null, model: null, timeLimitS: null };
    const model = localStorage.getItem(providerKey(id, 'model')) || null;
    // ProviderTabs persists time-limit per provider as a stringified number of
    // seconds. Treat 0 as unlimited; missing key falls back to null so the
    // wizard's existing default applies.
    const tlRaw = localStorage.getItem(providerKey(id, 'time-limit'));
    const timeLimitS = tlRaw === null ? null : Number.parseInt(tlRaw, 10);
    return { id, model, timeLimitS: Number.isFinite(timeLimitS) ? timeLimitS : null };
  } catch {
    return { id: null, model: null, timeLimitS: null };
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

  // Poll localStorage for changes — ProviderTabs / its children write directly,
  // and the `storage` event only fires for cross-tab writes. A short interval
  // is enough; the picker is interactive and the user is on the screen.
  useEffect(() => {
    const tick = () => setActiveProvider(readActiveProviderState());
    const interval = setInterval(tick, 400);
    window.addEventListener('storage', tick);
    return () => { clearInterval(interval); window.removeEventListener('storage', tick); };
  }, []);

  return { providerConfigs, activeProvider };
}
