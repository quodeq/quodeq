import { useState, useCallback } from 'react';
import { readString, writeString } from '../../../adapters/storage.js';
import { broadcastSettingsChange, useSettingsChangeSync } from './settingsSync.js';

export const NEW_FINDINGS_ONLY_KEY = 'cc-eval-new-findings-only';
const CHANGE_EVENT = 'live-feed-settings-changed';
const SYNC_EVENTS = [CHANGE_EVENT];
// How the boolean is encoded in localStorage. Read and write must agree, so
// both go through these rather than spelling the strings out twice.
const STORED_ON = 'true';
const STORED_OFF = 'false';

function loadNewOnly(storage) {
  // On by default: only an explicit opt-out ('false') shows findings
  // carried forward from the incremental cache.
  return readString(NEW_FINDINGS_ONLY_KEY, null, storage) !== STORED_OFF;
}

/**
 * Whether the live findings feed hides findings carried forward from the
 * incremental cache. On unless explicitly turned off.
 *
 * Writes are broadcast so the Settings screen and the evaluation screen stay
 * in sync within one window. `storage` is injectable for tests.
 *
 * @returns {{newOnly: boolean, setNewOnly: (value: boolean) => void}}
 */
export default function useLiveFeedSettings({ storage = localStorage } = {}) {
  const [newOnly, setNewOnlyState] = useState(() => loadNewOnly(storage));

  const setNewOnly = useCallback((value) => {
    const ok = writeString(NEW_FINDINGS_ONLY_KEY, value ? STORED_ON : STORED_OFF, storage);
    if (!ok) console.warn('[useLiveFeedSettings] could not persist new-findings-only setting');
    setNewOnlyState(value);
    broadcastSettingsChange(CHANGE_EVENT);
  }, [storage]);

  useSettingsChangeSync(SYNC_EVENTS, { load: loadNewOnly, setState: setNewOnlyState, storage });

  return { newOnly, setNewOnly };
}
