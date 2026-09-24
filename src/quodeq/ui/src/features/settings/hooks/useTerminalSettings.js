import { useState, useCallback } from 'react';
import { broadcastSettingsChange, useSettingsChangeSync } from './settingsSync.js';
import { STORED_TRUE, STORED_FALSE } from '../../../adapters/storage.js';

export const TERMINAL_ENABLED_KEY = 'cc-terminal-enabled';
const CHANGE_EVENT = 'terminal-settings-changed';
const SYNC_EVENTS = [CHANGE_EVENT];

function loadEnabled(storage) {
  // Enabled by default: only an explicit opt-out ('false') disables it.
  try {
    return storage.getItem(TERMINAL_ENABLED_KEY) !== STORED_FALSE;
  } catch (err) {
    console.warn('[useTerminalSettings] could not read:', err);
    return true;
  }
}

/**
 * Whether the embedded terminal is available. On unless explicitly turned
 * off, and unreadable storage falls back to on rather than hiding the feature.
 *
 * Writes are broadcast so every consumer in the window follows immediately.
 * `storage` is injectable for tests.
 *
 * @returns {{enabled: boolean, setEnabled: (value: boolean) => void}}
 */
export default function useTerminalSettings({ storage = localStorage } = {}) {
  const [enabled, setEnabledState] = useState(() => loadEnabled(storage));

  const setEnabled = useCallback((value) => {
    try {
      storage.setItem(TERMINAL_ENABLED_KEY, value ? STORED_TRUE : STORED_FALSE);
    } catch (err) {
      console.warn('[useTerminalSettings] could not persist:', err);
    }
    setEnabledState(value);
    broadcastSettingsChange(CHANGE_EVENT);
  }, [storage]);

  useSettingsChangeSync(SYNC_EVENTS, { load: loadEnabled, setState: setEnabledState, storage });

  return { enabled, setEnabled };
}
