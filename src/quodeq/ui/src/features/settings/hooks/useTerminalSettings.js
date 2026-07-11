import { useState, useCallback, useEffect } from 'react';

export const TERMINAL_ENABLED_KEY = 'cc-terminal-enabled';
const CHANGE_EVENT = 'terminal-settings-changed';

function loadEnabled(storage) {
  // Enabled by default: only an explicit opt-out ('false') disables it.
  return storage.getItem(TERMINAL_ENABLED_KEY) !== 'false';
}

export default function useTerminalSettings({ storage = localStorage } = {}) {
  const [enabled, setEnabledState] = useState(() => loadEnabled(storage));

  const setEnabled = useCallback((value) => {
    try {
      storage.setItem(TERMINAL_ENABLED_KEY, value ? 'true' : 'false');
    } catch (err) {
      console.warn('[useTerminalSettings] could not persist:', err);
    }
    setEnabledState(value);
    if (typeof window !== 'undefined') window.dispatchEvent(new Event(CHANGE_EVENT));
  }, [storage]);

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const onChange = () => setEnabledState(loadEnabled(storage));
    window.addEventListener(CHANGE_EVENT, onChange);
    window.addEventListener('storage', onChange);
    return () => {
      window.removeEventListener(CHANGE_EVENT, onChange);
      window.removeEventListener('storage', onChange);
    };
  }, [storage]);

  return { enabled, setEnabled };
}
