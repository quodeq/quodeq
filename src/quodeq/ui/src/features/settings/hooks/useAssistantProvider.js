import { useState, useCallback, useEffect } from 'react';
import { ACTIVE_PROVIDER_KEY, providerKey, PROVIDER_SETTINGS_CHANGED_EVENT } from '../../../constants.js';

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
  const mode = storage.getItem(ASSISTANT_MODE_KEY) === 'custom' ? 'custom' : 'default';
  const analysisActive = storage.getItem(ACTIVE_PROVIDER_KEY) || '';
  // Default ON: only an explicit opt-out ('false') disables it.
  const enabled = storage.getItem(ASSISTANT_ENABLED_KEY) !== 'false';

  if (mode === 'default') {
    const model = analysisActive
      ? (storage.getItem(providerKey(analysisActive, 'model')) || '')
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
    : (activeProvider ? (storage.getItem(providerKey(activeProvider, 'model')) || '') : '');
  return { enabled, mode, activeProvider, model, followsAnalysis: false };
}

export function useAssistantProvider({ storage = localStorage } = {}) {
  const [state, setState] = useState(() => loadState(storage));

  const broadcast = useCallback(() => {
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new Event(CHANGE_EVENT));
    }
  }, []);

  const setEnabled = useCallback((value) => {
    try {
      storage.setItem(ASSISTANT_ENABLED_KEY, value ? 'true' : 'false');
    } catch (err) {
      console.warn('[useAssistantProvider] Could not persist assistant enabled:', err);
    }
    setState(loadState(storage));
    broadcast();
  }, [storage, broadcast]);

  const setMode = useCallback((mode) => {
    try {
      storage.setItem(ASSISTANT_MODE_KEY, mode === 'custom' ? 'custom' : 'default');
    } catch (err) {
      console.warn('[useAssistantProvider] Could not persist assistant mode:', err);
    }
    setState(loadState(storage));
    broadcast();
  }, [storage, broadcast]);

  const setActiveProvider = useCallback((id) => {
    try {
      storage.setItem(ASSISTANT_ACTIVE_PROVIDER_KEY, id);
    } catch (err) {
      console.warn('[useAssistantProvider] Could not persist active provider:', err);
    }
    setState(loadState(storage));
    broadcast();
  }, [storage, broadcast]);

  const setModel = useCallback((value) => {
    const { activeProvider } = loadState(storage);
    try {
      storage.setItem(providerKey(activeProvider, 'model-assistant'), value);
    } catch (err) {
      console.warn('[useAssistantProvider] Could not persist assistant model:', err);
    }
    setState(loadState(storage));
    broadcast();
  }, [storage, broadcast]);

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const handleChange = () => setState(loadState(storage));
    window.addEventListener(CHANGE_EVENT, handleChange);
    // Analysis-gate changes (provider/model) fire this shared event so Default
    // mode, which mirrors the analysis selection, updates its display live.
    window.addEventListener(PROVIDER_SETTINGS_CHANGED_EVENT, handleChange);
    window.addEventListener('storage', handleChange);
    return () => {
      window.removeEventListener(CHANGE_EVENT, handleChange);
      window.removeEventListener(PROVIDER_SETTINGS_CHANGED_EVENT, handleChange);
      window.removeEventListener('storage', handleChange);
    };
  }, [storage]);

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

export default useAssistantProvider;
