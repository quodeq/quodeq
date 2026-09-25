import { useState, useCallback, useMemo } from 'react';
import { ACTIVE_PROVIDER_KEY, providerKey, PROVIDER_SETTINGS_CHANGED_EVENT, PROVIDER_SETTING_KEY } from '../../../constants.js';
import { broadcastSettingsChange, useSettingsChangeSync } from './settingsSync.js';
import { STORED_TRUE, STORED_FALSE } from '../../../adapters/storage.js';
import { ASSISTANT_MODE } from '../settingsVocab.js';

export const ASSISTANT_ACTIVE_PROVIDER_KEY = 'cc-assistant-active-provider';
export const ASSISTANT_MODE_KEY = 'cc-assistant-mode';
// The assistant is ON by default: the toolbar launcher shows until the user
// explicitly disables it in Settings.
export const ASSISTANT_ENABLED_KEY = 'cc-assistant-enabled';

// Broadcast so every useAssistantProvider() instance (Settings tab, drawer, ...)
// re-reads storage and stays in sync when one instance changes the selection.
const CHANGE_EVENT = 'assistant-provider-changed';

// Resolve the whole assistant gate from storage, fresh, every time.
// - default mode: mirror the Analysis gate LIVE (read cc-active-provider +
//   its model on every read, never snapshotted).
// - custom mode: use the assistant-scoped provider/model, falling back to the
//   analysis selection when the assistant keys are unset.
function loadState(storage) {
  const mode = storage.getItem(ASSISTANT_MODE_KEY) === ASSISTANT_MODE.CUSTOM ? ASSISTANT_MODE.CUSTOM : ASSISTANT_MODE.DEFAULT;
  const analysisActive = storage.getItem(ACTIVE_PROVIDER_KEY) || '';
  // Default ON: only an explicit opt-out ('false') disables it.
  const enabled = storage.getItem(ASSISTANT_ENABLED_KEY) !== STORED_FALSE;

  if (mode === ASSISTANT_MODE.DEFAULT) {
    const model = analysisActive
      ? (storage.getItem(providerKey(analysisActive, PROVIDER_SETTING_KEY.MODEL)) || '')
      : '';
    return { enabled, mode, activeProvider: analysisActive, model, followsAnalysis: true };
  }

  const explicitProvider = storage.getItem(ASSISTANT_ACTIVE_PROVIDER_KEY);
  const activeProvider = explicitProvider !== null ? explicitProvider : analysisActive;
  const explicitModel = activeProvider
    ? storage.getItem(providerKey(activeProvider, 'model-assistant'))
    : null;
  const model = explicitModel !== null
    ? explicitModel
    : (activeProvider ? (storage.getItem(providerKey(activeProvider, PROVIDER_SETTING_KEY.MODEL)) || '') : '');
  return { enabled, mode, activeProvider, model, followsAnalysis: false };
}

// A setter that writes one storage key, then re-reads the whole state and
// broadcasts it. A refused write (quota, private mode) goes to `onRefused` and
// the re-read still runs. `keyFor` runs before the write is attempted.
function makePersistingSetter({ storage, setState, broadcast }, { keyFor, stored = (value) => value, onRefused }) {
  return (value) => {
    const key = keyFor();
    try {
      storage.setItem(key, stored(value));
    } catch (err) {
      onRefused(err);
    }
    setState(loadState(storage));
    broadcast();
  };
}

const SETTERS = {
  setEnabled: {
    onRefused: (err) => console.warn('[useAssistantProvider] Could not persist assistant enabled:', err),
    keyFor: () => ASSISTANT_ENABLED_KEY,
    stored: (value) => (value ? STORED_TRUE : STORED_FALSE),
  },
  setMode: {
    onRefused: (err) => console.warn('[useAssistantProvider] Could not persist assistant mode:', err),
    keyFor: () => ASSISTANT_MODE_KEY,
    stored: (mode) => (mode === ASSISTANT_MODE.CUSTOM ? ASSISTANT_MODE.CUSTOM : ASSISTANT_MODE.DEFAULT),
  },
  setActiveProvider: {
    onRefused: (err) => console.warn('[useAssistantProvider] Could not persist active provider:', err),
    keyFor: () => ASSISTANT_ACTIVE_PROVIDER_KEY,
  },
};

function makeSetModel(ctx) {
  return makePersistingSetter(ctx, {
    onRefused: (err) => console.warn('[useAssistantProvider] Could not persist assistant model:', err),
    keyFor: () => providerKey(loadState(ctx.storage).activeProvider, 'model-assistant'),
  });
}

// Analysis-gate changes (provider/model) fire PROVIDER_SETTINGS_CHANGED_EVENT
// so Default mode, which mirrors the analysis selection, updates its display live.
// The analysis provider settings feed the default mode, so their change
// event re-reads this hook's state too.
const SYNC_EVENTS = [CHANGE_EVENT, PROVIDER_SETTINGS_CHANGED_EVENT];

function buildAssistantProviderResult(state, setEnabled, setMode, setActiveProvider, setModel) {
  return {
    enabled: state.enabled,
    setEnabled,
    mode: state.mode,
    setMode,
    activeProvider: state.activeProvider,
    setActiveProvider,
    model: state.model,
    setModel,
    followsAnalysis: state.followsAnalysis,
  };
}

/**
 * The assistant's provider selection: whether it is enabled, the mode, the
 * active provider and its model.
 *
 * Every setter persists and broadcasts, so a change made on the Settings
 * screen reaches the drawer in the same window (a `storage` event only fires
 * cross-tab). In follow-analysis mode the selection tracks the analysis
 * provider instead of being set directly. `storage` is injectable for tests.
 */
export function useAssistantProvider({ storage = localStorage } = {}) {
  const [state, setState] = useState(() => loadState(storage));

  const broadcast = useCallback(() => broadcastSettingsChange(CHANGE_EVENT), []);

  // useMemo, not useCallback: the factories must run only when their inputs
  // change, where useCallback(factory(...), deps) rebuilds the closure every
  // render and then throws it away.
  const { setEnabled, setMode, setActiveProvider, setModel } = useMemo(() => {
    const ctx = { storage, setState, broadcast };
    return {
      setEnabled: makePersistingSetter(ctx, SETTERS.setEnabled),
      setMode: makePersistingSetter(ctx, SETTERS.setMode),
      setActiveProvider: makePersistingSetter(ctx, SETTERS.setActiveProvider),
      setModel: makeSetModel(ctx),
    };
  }, [storage, broadcast]);

  useSettingsChangeSync(SYNC_EVENTS, { load: loadState, setState, storage });

  return buildAssistantProviderResult(state, setEnabled, setMode, setActiveProvider, setModel);
}

export default useAssistantProvider;
