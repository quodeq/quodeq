import { useState, useCallback } from 'react';
import { ACTIVE_PROVIDER_KEY, providerKey } from '../../../constants.js';

export const ASSISTANT_ACTIVE_PROVIDER_KEY = 'cc-assistant-active-provider';

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
  }, [storage]);

  const setModel = useCallback((value) => {
    try {
      storage.setItem(providerKey(activeProvider, 'model-assistant'), value);
    } catch (err) {
      console.warn('[useAssistantProvider] Could not persist assistant model:', err);
    }
    setModelState(value);
  }, [activeProvider, storage]);

  return { activeProvider, setActiveProvider, model, setModel, followsAnalysis };
}

export default useAssistantProvider;
