import { useEffect } from 'react';

// Fired by the browser when another window writes localStorage.
const STORAGE_EVENT = 'storage';

/**
 * Tell every consumer in this window that a setting changed. A 'storage'
 * event does not fire in the window that wrote the value, so without this
 * the Settings page and the screens reading the setting drift apart.
 */
export function broadcastSettingsChange(eventName) {
  if (typeof window !== 'undefined') window.dispatchEvent(new Event(eventName));
}

/**
 * Reload a setting from `storage` whenever one of `eventNames` fires in this
 * window or another window writes localStorage. `eventNames`, `load` and
 * `setState` must be stable (module constants and a state setter).
 */
export function useSettingsChangeSync(eventNames, { load, setState, storage }) {
  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const onChange = () => setState(load(storage));
    const names = [...eventNames, STORAGE_EVENT];
    names.forEach((name) => window.addEventListener(name, onChange));
    return () => names.forEach((name) => window.removeEventListener(name, onChange));
  }, [eventNames, load, setState, storage]);
}
