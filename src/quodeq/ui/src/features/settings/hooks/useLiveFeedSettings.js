import { useState, useCallback, useEffect } from 'react';

export const NEW_FINDINGS_ONLY_KEY = 'cc-eval-new-findings-only';
const CHANGE_EVENT = 'live-feed-settings-changed';

function loadNewOnly(storage) {
  // On by default: only an explicit opt-out ('false') shows findings
  // carried forward from the incremental cache.
  return storage.getItem(NEW_FINDINGS_ONLY_KEY) !== 'false';
}

export default function useLiveFeedSettings({ storage = localStorage } = {}) {
  const [newOnly, setNewOnlyState] = useState(() => loadNewOnly(storage));

  const setNewOnly = useCallback((value) => {
    try {
      storage.setItem(NEW_FINDINGS_ONLY_KEY, value ? 'true' : 'false');
    } catch (err) {
      console.warn('[useLiveFeedSettings] could not persist:', err);
    }
    setNewOnlyState(value);
    // A 'storage' event does not fire in the tab that wrote the value, so
    // the Settings page and the evaluation screen need this to stay in
    // sync within one window.
    if (typeof window !== 'undefined') window.dispatchEvent(new Event(CHANGE_EVENT));
  }, [storage]);

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const onChange = () => setNewOnlyState(loadNewOnly(storage));
    window.addEventListener(CHANGE_EVENT, onChange);
    window.addEventListener('storage', onChange);
    return () => {
      window.removeEventListener(CHANGE_EVENT, onChange);
      window.removeEventListener('storage', onChange);
    };
  }, [storage]);

  return { newOnly, setNewOnly };
}
