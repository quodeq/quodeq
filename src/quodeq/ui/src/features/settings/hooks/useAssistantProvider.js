import { useState, useCallback, useEffect } from 'react';
import { ACTIVE_PROVIDER_KEY, providerKey } from '../../../constants.js';

export const ASSISTANT_ACTIVE_PROVIDER_KEY = 'cc-assistant-active-provider';

// Broadcast so every useAssistantProvider() instance (Settings tab, drawer, ...)
// re-reads storage and stays in sync when one instance changes the selection.
const CHANGE_EVENT = 'assistant-provider-changed';

function loadActiveProvider(storage) {
  const explicit = storage.getItem(ASSISTANT_ACTIVE_PROVIDER_KEY);
  if (explicit !== null) {
    return { activeProvider: explicit, followsAnalysis: false };
  }
  return { activeProvider: storage.getItem(ACTIVE_PROVIDER_KEY) || '', followsAnalysis: true };
}

function loadModel(providerId, storage) {
  const explicit = storage.getItem(providerKey(providerId, 'model-assistant'));
  if (explicit !== null) return explicit;
  return storage.getItem(providerKey(providerId, 'model')) || '';
}

export function useAssistantProvider({ storage = localStorage } = {}) {
  const [{ activeProvider, followsAnalysis }, setProviderState] = useState(() => loadActiveProvider(storage));
  const [model, setModelState] = useState(() => loadModel(activeProvider, storage));

  const setActiveProvider = useCallback((id) => {
    try {
      storage.setItem(ASSISTANT_ACTIVE_PROVIDER_KEY, id);
    } catch (err) {
      console.warn('[useAssistantProvider] Could not persist active provider:', err);
    }
    setProviderState({ activeProvider: id, followsAnalysis: false });
    setModelState(loadModel(id, storage));
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new Event(CHANGE_EVENT));
    }
  }, [storage]);

  const setModel = useCallback((value) => {
    try {
      storage.setItem(providerKey(activeProvider, 'model-assistant'), value);
    } catch (err) {
      console.warn('[useAssistantProvider] Could not persist assistant model:', err);
    }
    setModelState(value);
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new Event(CHANGE_EVENT));
    }
  }, [activeProvider, storage]);

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const handleChange = () => {
      const st = loadActiveProvider(storage);
      setProviderState(st);
      setModelState(loadModel(st.activeProvider, storage));
    };
    window.addEventListener(CHANGE_EVENT, handleChange);
    window.addEventListener('storage', handleChange);
    return () => {
      window.removeEventListener(CHANGE_EVENT, handleChange);
      window.removeEventListener('storage', handleChange);
    };
  }, [storage]);

  return { activeProvider, setActiveProvider, model, setModel, followsAnalysis };
}

export default useAssistantProvider;
